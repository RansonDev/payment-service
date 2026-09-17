"""Payment consumer worker.

Обрабатывает события о новых платежах из RabbitMQ.
Вызывает ProcessPaymentUseCase для каждого сообщения.
"""

import asyncio
import json
import signal
import sys
from typing import Any
from uuid import UUID

from dishka import AsyncContainer, make_async_container
import structlog

from payments_service.application.exceptions import WebhookDeliveryError
from payments_service.application.use_cases.process_payment import ProcessPaymentUseCase
from payments_service.config.ioc.di import get_providers
from payments_service.config.logging import setup_logging
from payments_service.config.settings import Settings
from payments_service.infrastructures.broker.aio_pika.ack import NackMessage
from payments_service.infrastructures.broker.aio_pika.connection import (
    RabbitConnection,
)
from payments_service.infrastructures.broker.aio_pika.consumer import (
    AckPolicy,
    RabbitConsumer,
)
from payments_service.infrastructures.broker.aio_pika.message import RabbitMessage
from payments_service.infrastructures.broker.topology import (
    PaymentsTopology,
    declare_topology,
)
from payments_service.infrastructures.context import context

logger = structlog.get_logger(__name__)


class PaymentConsumer:
    """Консьюмер обработки платежей.

    При технической ошибке вебхука: инкремент x-attempt, публикация в retry-очередь.
    После исчерпания лимита — публикация в DLX.
    """

    def __init__(
        self,
        rabbit_connection: RabbitConnection,
        container: AsyncContainer,
        settings: Settings,
    ) -> None:
        """Инициализация consumer.

        Args:
            rabbit_connection: RabbitMQ connection.
            container: Dishka container для DI.
            settings: Настройки приложения.
        """
        self.rabbit_connection = rabbit_connection
        self.container = container
        self.settings = settings
        self.running = False
        self.consumer: RabbitConsumer | None = None

        self.retry_ttls = [
            settings.broker.retry_ttl_level_1_ms,
            settings.broker.retry_ttl_level_2_ms,
            settings.broker.retry_ttl_level_3_ms,
        ]
        self.max_attempts = len(self.retry_ttls)

    async def handle_message(self, message: RabbitMessage) -> None:
        """Обработать одно сообщение.

        КРИТИЧНО: сессия БД открывается на каждое сообщение через Scope.REQUEST.

        Args:
            message: Сообщение из RabbitMQ.

        Raises:
            WebhookDeliveryError: При технической ошибке доставки вебхука.
        """
        trace_id = message.headers.get("x-trace-id") or message.correlation_id or "-"
        attempt = int(message.headers.get("x-attempt", 0))

        with context.bind(trace_id=trace_id, message_id=message.message_id):
            payload = message.decode()
            payment_id_str = payload.get("payment_id")

            if not payment_id_str:
                logger.error("missing payment_id in message", payload=payload)
                return

            payment_id = UUID(payment_id_str)

            with context.bind(payment_id=str(payment_id)):
                logger.info(
                    "processing payment message",
                    payment_id=str(payment_id),
                    attempt=attempt,
                    headers=message.headers,
                )

                async with self.container() as request_container:
                    use_case = await request_container.get(ProcessPaymentUseCase)
                    await use_case(payment_id)

                logger.info(
                    "payment processed successfully",
                    payment_id=str(payment_id),
                    attempt=attempt,
                )

    async def handle_webhook_error(
        self, message: RabbitMessage, error: WebhookDeliveryError
    ) -> None:
        """Обработать ошибку доставки вебхука.

        Инкремент x-attempt, публикация в retry-очередь соответствующего уровня.
        После исчерпания попыток - публикация в DLX.

        Args:
            message: Исходное сообщение.
            error: Ошибка доставки вебхука.
        """
        attempt = int(message.headers.get("x-attempt", 0))
        next_attempt = attempt + 1

        try:
            payload = message.decode()
            payment_id = payload.get("payment_id")
        except Exception:
            payment_id = None

        logger.warning(
            "webhook delivery failed",
            payment_id=payment_id,
            attempt=attempt,
            next_attempt=next_attempt,
            error=str(error),
            url=error.url,
        )

        # attempt 0 -> retry.1, 1 -> retry.2, 2 -> retry.3, 3 -> DLX
        if next_attempt > self.max_attempts:
            logger.error(
                "max retry attempts exceeded, sending to DLX",
                payment_id=payment_id,
                attempt=attempt,
                max_attempts=self.max_attempts,
            )

            await self.rabbit_connection.producer.publish(
                message.body,
                exchange=PaymentsTopology.DLX,
                routing_key="payments.dead",
                headers={
                    **message.headers,
                    "x-original-routing-key": str(message.message_id),
                    "x-failure-reason": str(error),
                    "x-failure-url": error.url,
                },
                content_type=message.content_type,
                message_id=message.message_id,
            )
        else:
            retry_routing_key = f"retry.{next_attempt}"

            logger.info(
                "publishing to retry queue",
                payment_id=payment_id,
                next_attempt=next_attempt,
                retry_routing_key=retry_routing_key,
            )

            await self.rabbit_connection.producer.publish(
                message.body,
                exchange=PaymentsTopology.RETRY,
                routing_key=retry_routing_key,
                headers={
                    **message.headers,
                    "x-attempt": str(next_attempt),
                },
                content_type=message.content_type,
                message_id=message.message_id,
            )

    async def message_handler(self, message: RabbitMessage) -> None:
        """Обработчик сообщений для RabbitConsumer.

        Args:
            message: Сообщение из RabbitMQ.
        """
        try:
            await self.handle_message(message)
        except WebhookDeliveryError as e:
            await self.handle_webhook_error(message, e)
        except Exception as e:
            err_str = str(e)
            logger.exception("unexpected error processing message", error=err_str)
            raise

    async def run(self) -> None:
        """Запустить консьюмер."""
        self.running = True
        logger.info("payment consumer started")

        self.consumer = RabbitConsumer(
            declarer=self.rabbit_connection.declarer,
            queue=PaymentsTopology.NEW,
            exchange=PaymentsTopology.PAYMENTS,
            handler=self.message_handler,
            ack_policy=AckPolicy.REJECT_ON_ERROR,
        )

        await self.consumer.start()

        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("consumer task cancelled")

        logger.info("payment consumer stopped")

    async def stop(self) -> None:
        """Остановить консьюмер (graceful shutdown)."""
        logger.info("stopping payment consumer...")
        if self.consumer:
            await self.consumer.stop()
        self.running = False


async def main() -> None:
    """Точка входа consumer."""
    setup_logging(level="INFO")
    logger.info("starting payment consumer worker")

    settings = Settings()
    container = make_async_container(*get_providers())

    rabbit_connection = RabbitConnection(url=settings.broker_url)
    await rabbit_connection.connect()

    await declare_topology(rabbit_connection, settings.broker)
    logger.info("rabbitmq topology declared")

    payment_consumer = PaymentConsumer(
        rabbit_connection=rabbit_connection,
        container=container,
        settings=settings,
    )

    loop = asyncio.get_running_loop()

    def shutdown_handler(signum: int, frame: object) -> None:  # noqa: ARG001
        """Обработчик сигналов завершения."""
        logger.info("received shutdown signal", signal=signum)
        asyncio.create_task(payment_consumer.stop())

    # Windows не поддерживает loop.add_signal_handler
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
    else:
        loop.add_signal_handler(
            signal.SIGTERM, lambda: asyncio.create_task(payment_consumer.stop())
        )
        loop.add_signal_handler(
            signal.SIGINT, lambda: asyncio.create_task(payment_consumer.stop())
        )

    try:
        await payment_consumer.run()
    finally:
        await rabbit_connection.stop()
        await container.close()
        logger.info("payment consumer shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
