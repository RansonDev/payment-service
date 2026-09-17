"""Жизненный цикл соединения с RabbitMQ.

Собрано из faststream/rabbit/broker/broker.py (_connect / stop / ping), v0.7.5,
в тонкую замену RabbitBroker.

Убрано: BrokerUsecase, FastDependsConfig, ContextRepo, middlewares,
регистратор подписчиков через декораторы, AsyncAPI-спецификация,
build_url с разбором vhost и SSL-опций (достаточно готового AMQP URL),
parse_security.

Оставлено: connect_robust (переподключение и восстановление каналов, очередей,
обменников и подписок силами aio-pika), порядок закрытия «сначала каналы,
потом соединение», ping через connection.connected.
"""

import logging
from types import TracebackType
from typing import TYPE_CHECKING, Any, cast

from aio_pika import RobustConnection, connect_robust

from .channel import ChannelManager
from .declarer import RabbitDeclarer
from .producer import RabbitProducer
from .schemas import Channel

if TYPE_CHECKING:
    import aio_pika

logger = logging.getLogger(__name__)


class RabbitConnection:
    """Одно robust-соединение + пул каналов + декларатор + продюсер."""

    def __init__(
        self,
        url: str,
        *,
        app_id: str | None = None,
        default_channel: Channel | None = None,
        timeout: float = 10.0,
        **connect_kwargs: Any,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._connect_kwargs = connect_kwargs

        self._connection: RobustConnection | None = None

        self.channel_manager = ChannelManager(default_channel)
        self.declarer = RabbitDeclarer(self.channel_manager)
        self.producer = RabbitProducer(self.declarer, app_id=app_id)

    @property
    def connection(self) -> RobustConnection:
        if self._connection is None:
            msg = "You should connect broker first."
            raise RuntimeError(msg)
        return self._connection

    async def connect(self) -> RobustConnection:
        if self._connection is not None:
            return self._connection

        connection = cast(
            "RobustConnection",
            await connect_robust(
                self._url,
                timeout=self._timeout,
                **self._connect_kwargs,
            ),
        )

        self._connection = connection
        self.channel_manager.connect(connection)
        # прогреваем канал по умолчанию, чтобы qos выставился до первой операции
        await self.channel_manager.get_channel()

        logger.info("Connected to RabbitMQ")
        return connection

    async def stop(self) -> None:
        # Каналы закрываются раньше соединения: закрытие соединения
        # первым оставляет незавершённые доставки без basic.cancel.
        for ch in list(self.channel_manager._channels.values()):  # noqa: SLF001
            if not ch.is_closed:
                await ch.close()

        self.channel_manager.disconnect()
        self.declarer.disconnect()

        if self._connection is not None:
            await self._connection.close()
            self._connection = None

        logger.info("Disconnected from RabbitMQ")

    async def declare_queue(self, queue: Any, **kwargs: Any) -> "aio_pika.RobustQueue":
        return await self.declarer.declare_queue(queue, **kwargs)

    async def declare_exchange(
        self,
        exchange: Any,
        **kwargs: Any,
    ) -> "aio_pika.RobustExchange":
        return await self.declarer.declare_exchange(exchange, **kwargs)

    async def ping(self) -> bool:
        return self._connection is not None and self._connection.connected.is_set()

    async def __aenter__(self) -> "RabbitConnection":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        await self.stop()
