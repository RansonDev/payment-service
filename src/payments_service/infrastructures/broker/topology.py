"""Топология RabbitMQ для платёжного сервиса.

Обменники:
- payments: основной обменник для новых платежей
- payments.retry: обменник для retry-очередей
- payments.dlx: dead letter exchange для неудавшихся сообщений

Очереди:
- payments.new: основная очередь с консьюмером
- payments.retry.{1,2,3}: очереди с TTL для повторов (без консьюмеров)
- payments.dlq: dead letter queue для окончательно неудавшихся сообщений

TTL задаётся на очереди, а не на сообщении, для избежания head-of-line blocking.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from payments_service.infrastructures.broker.aio_pika.schemas import (
    ExchangeType,
    RabbitExchange,
    RabbitQueue,
)

if TYPE_CHECKING:
    from payments_service.config.broker import BrokerSettings
    from payments_service.infrastructures.broker.aio_pika.connection import (
        RabbitConnection,
    )


@dataclass(frozen=True, slots=True)
class PaymentsTopology:
    """Топология RabbitMQ для платёжного сервиса."""

    PAYMENTS = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
    RETRY = RabbitExchange("payments.retry", type=ExchangeType.DIRECT, durable=True)
    DLX = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

    NEW = RabbitQueue(
        "payments.new",
        routing_key="payments.new",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "payments.dlx",
            "x-dead-letter-routing-key": "payments.dead",
        },
    )

    DLQ = RabbitQueue(
        "payments.dlq",
        routing_key="payments.dead",
        durable=True,
    )

    @staticmethod
    def retry_queue(level: int, ttl_ms: int) -> RabbitQueue:
        """Создать retry-очередь с заданным TTL.

        Retry-очереди НЕ имеют консьюмеров. Сообщение отлёживает TTL и
        дедлеттерится обратно в payments.new.

        Args:
            level: Уровень повтора (1, 2, 3).
            ttl_ms: TTL в миллисекундах.

        Returns:
            RabbitQueue для retry-очереди.
        """
        return RabbitQueue(
            f"payments.retry.{level}",
            routing_key=f"retry.{level}",
            durable=True,
            arguments={
                "x-message-ttl": ttl_ms,
                "x-dead-letter-exchange": "payments",
                "x-dead-letter-routing-key": "payments.new",
            },
        )


async def declare_topology(
    connection: "RabbitConnection",
    broker_settings: "BrokerSettings",
) -> None:
    """Объявить всю топологию RabbitMQ.

    Декларация идемпотентна - повторный вызов с теми же аргументами безопасен.
    Вызывается при старте воркеров (consumer и outbox-publisher) до начала
    потребления или публикации.

    Args:
        connection: Подключение к RabbitMQ.
        broker_settings: Настройки брокера с TTL для retry-очередей.
    """
    payments_exchange = await connection.declare_exchange(PaymentsTopology.PAYMENTS)
    retry_exchange = await connection.declare_exchange(PaymentsTopology.RETRY)
    dlx_exchange = await connection.declare_exchange(PaymentsTopology.DLX)

    new_queue = await connection.declare_queue(PaymentsTopology.NEW)
    await new_queue.bind(payments_exchange, routing_key="payments.new")

    retry_ttls = [
        (1, broker_settings.retry_ttl_level_1_ms),
        (2, broker_settings.retry_ttl_level_2_ms),
        (3, broker_settings.retry_ttl_level_3_ms),
    ]
    for level, ttl_ms in retry_ttls:
        retry_q = await connection.declare_queue(
            PaymentsTopology.retry_queue(level, ttl_ms)
        )
        await retry_q.bind(retry_exchange, routing_key=f"retry.{level}")

    dlq = await connection.declare_queue(PaymentsTopology.DLQ)
    await dlq.bind(dlx_exchange, routing_key="payments.dead")
