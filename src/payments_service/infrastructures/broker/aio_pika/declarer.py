"""Идемпотентная декларация топологии с кешированием.

Вырезано из faststream/rabbit/helpers/declarer.py (v0.7.5).

Убрано: Protocol + FakeRabbitDeclarer, EMPTY-сентинел (заменён на None).

Что здесь ценного:
  * кеш по __hash__ схемы — повторный declare не идёт в брокер;
  * declare=False превращается в aio-pika `passive=True`, то есть «подключись
    к существующей, не создавай». Продюсер пользуется этим, чтобы не
    переобъявлять обменник на каждую публикацию;
  * рекурсивная привязка обменник-к-обменнику через bind_to.
"""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import aio_pika

    from .channel import ChannelManager
    from .schemas import Channel, RabbitExchange, RabbitQueue


class RabbitDeclarer:
    """Объявляет очереди и обменники, кешируя уже объявленные объекты."""

    __slots__ = ("_channel_manager", "_exchanges", "_queues")

    def __init__(self, channel_manager: "ChannelManager") -> None:
        self._channel_manager = channel_manager
        self._queues: dict[RabbitQueue, aio_pika.RobustQueue] = {}
        self._exchanges: dict[RabbitExchange, aio_pika.RobustExchange] = {}

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(queues={list(self._queues.keys())}, "
            f"exchanges={list(self._exchanges.keys())})"
        )

    def disconnect(self) -> None:
        self._queues.clear()
        self._exchanges.clear()

    async def declare_queue(
        self,
        queue: "RabbitQueue",
        declare: bool | None = None,
        *,
        channel: "Channel | None" = None,
    ) -> "aio_pika.RobustQueue":
        if (q := self._queues.get(queue)) is None:
            if declare is None:
                declare = queue.declare

            channel_obj = await self._channel_manager.get_channel(channel)

            self._queues[queue] = q = cast(
                "aio_pika.RobustQueue",
                await channel_obj.declare_queue(
                    name=queue.name,
                    durable=queue.durable,
                    exclusive=queue.exclusive,
                    passive=not declare,
                    auto_delete=queue.auto_delete,
                    arguments=queue.arguments,
                    timeout=queue.timeout,
                    robust=queue.robust,
                ),
            )

        return q

    async def declare_exchange(
        self,
        exchange: "RabbitExchange",
        declare: bool | None = None,
        *,
        channel: "Channel | None" = None,
    ) -> "aio_pika.RobustExchange":
        channel_obj = await self._channel_manager.get_channel(channel)

        if not exchange.name:
            return channel_obj.default_exchange

        if (exch := self._exchanges.get(exchange)) is None:
            if declare is None:
                declare = exchange.declare

            self._exchanges[exchange] = exch = cast(
                "aio_pika.RobustExchange",
                await channel_obj.declare_exchange(
                    name=exchange.name,
                    type=exchange.type.value,
                    durable=exchange.durable,
                    auto_delete=exchange.auto_delete,
                    passive=not declare,
                    arguments=exchange.arguments,
                    timeout=exchange.timeout,
                    robust=exchange.robust,
                    internal=False,  # deprecated RMQ option
                ),
            )

            if exchange.bind_to is not None:
                parent = await self.declare_exchange(exchange.bind_to)
                await exch.bind(
                    exchange=parent,
                    routing_key=exchange.routing(),
                    arguments=exchange.bind_arguments,
                    timeout=exchange.timeout,
                    robust=exchange.robust,
                )

        return exch
