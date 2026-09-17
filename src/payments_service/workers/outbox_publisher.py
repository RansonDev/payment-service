"""Outbox publisher worker.

Публикует события из таблицы outbox в RabbitMQ.
Использует FOR UPDATE SKIP LOCKED для защиты от параллельной обработки.
"""

import asyncio
from datetime import UTC, datetime
import logging
import signal
import sys

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
import structlog

from payments_service.config.logging import setup_logging
from payments_service.config.settings import Settings
from payments_service.infrastructures.broker.aio_pika.connection import (
    RabbitConnection,
)
from payments_service.infrastructures.broker.aio_pika.schemas import RabbitExchange
from payments_service.infrastructures.broker.topology import declare_topology
from payments_service.infrastructures.db.models import outbox_table
from payments_service.infrastructures.db.session import (
    create_engine,
    get_session_factory,
)
from payments_service.infrastructures.outbox.client import OutboxClient
from payments_service.infrastructures.outbox.retry import ExponentialRetry

logger = structlog.get_logger(__name__)


class OutboxPublisher:
    """Воркер публикации событий из outbox в RabbitMQ.

    КРИТИЧНО: сначала publish с подтверждением брокера, потом mark_published.
    Обратный порядок даёт тихую потерю событий.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        rabbit_connection: RabbitConnection,
        outbox: OutboxClient,
        batch_size: int = 100,
        poll_interval: float = 0.5,
    ) -> None:
        """Инициализация outbox publisher.

        Args:
            engine: SQLAlchemy engine.
            session_factory: Фабрика сессий.
            rabbit_connection: RabbitMQ connection с producer.
            outbox: Клиент для работы с таблицей outbox.
            batch_size: Размер пачки событий.
            poll_interval: Интервал опроса outbox в секундах.
        """
        self.engine = engine
        self.session_factory = session_factory
        self.rabbit_connection = rabbit_connection
        self.outbox = outbox
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.running = False
        self.retry_strategy = ExponentialRetry(
            max_attempts=None,
            initial_delay_seconds=1.0,
            max_delay_seconds=300.0,
        )

    async def publish_batch(self) -> int:
        """Опубликовать одну пачку событий из outbox.

        Returns:
            Количество опубликованных событий.
        """
        async with self.session_factory() as session, session.begin():
            events = await self.outbox.fetch_pending(session, limit=self.batch_size)

            if not events:
                return 0

            published, now = [], datetime.now(UTC)
            for event in events:
                try:
                    await self.rabbit_connection.producer.publish(
                        event.payload,
                        exchange=(
                            RabbitExchange(event.exchange) if event.exchange else None
                        ),
                        routing_key=event.routing_key,
                        headers=event.headers,
                        content_type=event.content_type,
                        message_id=event.message_id,
                    )
                except Exception as exc:
                    attempts = event.attempts_count + 1
                    delay = self.retry_strategy.get_next_attempt_delay(
                        first_attempt_at=event.first_attempt_at or now,
                        last_attempt_at=now,
                        attempts_count=attempts,
                        exception=exc,
                    )
                    await self.outbox.reschedule(
                        session,
                        event.id,
                        delay_seconds=delay or 60.0,
                        attempts_count=attempts,
                        first_attempt_at=event.first_attempt_at or now,
                        last_attempt_at=now,
                        error=repr(exc),
                    )
                    logger.warning(
                        "failed to publish outbox event, rescheduled",
                        event_id=event.id,
                        attempts=attempts,
                        delay=delay,
                        error=str(exc),
                    )
                else:
                    published.append(event.id)

            if published:
                await self.outbox.mark_published(session, published)
                logger.info(
                    "published outbox batch",
                    count=len(published),
                    total_fetched=len(events),
                )

            return len(events)

    async def run(self) -> None:
        """Основной цикл публикации событий."""
        self.running = True
        logger.info("outbox publisher started")

        while self.running:
            try:
                processed = await self.publish_batch()
                if processed == 0:
                    await asyncio.sleep(self.poll_interval)
            except Exception as exc:
                logger.exception("error in publish batch", error=str(exc))
                await asyncio.sleep(self.poll_interval)

        logger.info("outbox publisher stopped")

    async def stop(self) -> None:
        """Остановить воркер (graceful shutdown)."""
        logger.info("stopping outbox publisher...")
        self.running = False


async def main() -> None:
    """Точка входа outbox publisher."""
    setup_logging(level="INFO")
    logger.info("starting outbox publisher worker")

    settings = Settings()

    engine = create_engine(str(settings.database_url), is_echo=settings.debug)
    session_factory = get_session_factory(engine)

    outbox = OutboxClient(table=outbox_table)

    rabbit_connection = RabbitConnection(url=settings.broker_url)
    await rabbit_connection.connect()

    await declare_topology(rabbit_connection, settings.broker)
    logger.info("rabbitmq topology declared")

    publisher = OutboxPublisher(
        engine=engine,
        session_factory=session_factory,
        rabbit_connection=rabbit_connection,
        outbox=outbox,
        batch_size=100,
        poll_interval=0.5,
    )

    loop = asyncio.get_running_loop()

    def shutdown_handler(signum: int, frame: object) -> None:  # noqa: ARG001
        """Обработчик сигналов завершения."""
        logger.info("received shutdown signal", signal=signum)
        asyncio.create_task(publisher.stop())

    # Windows не поддерживает loop.add_signal_handler
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
    else:
        loop.add_signal_handler(
            signal.SIGTERM, lambda: asyncio.create_task(publisher.stop())
        )
        loop.add_signal_handler(
            signal.SIGINT, lambda: asyncio.create_task(publisher.stop())
        )

    try:
        await publisher.run()
    finally:
        await rabbit_connection.stop()
        await engine.dispose()
        logger.info("outbox publisher shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
