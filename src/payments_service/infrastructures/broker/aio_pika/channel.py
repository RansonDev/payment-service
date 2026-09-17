"""Пул каналов поверх одного robust-соединения.

Смысл, ради которого это стоит забирать: канал в AMQP — не потокобезопасный
мультиплекс, и каналы принято переиспользовать по назначению, а не открывать
на каждую операцию. Здесь канал кешируется по объекту Channel (хеш по
identity), и qos выставляется ровно один раз при создании.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from .schemas import Channel

if TYPE_CHECKING:
    import aio_pika
    from aio_pika import RobustConnection


class ConnectionState(Protocol):
    @property
    def connection(self) -> "RobustConnection": ...


class EmptyConnectionState:
    __slots__ = ()

    @property
    def connection(self) -> "RobustConnection":
        msg = "You should connect broker first."
        raise RuntimeError(msg)


@dataclass(slots=True)
class ConnectedState:
    connection: "RobustConnection"


class ChannelManager:
    __slots__ = ("_channels", "_connection", "_default_channel")

    def __init__(self, default_channel: Channel | None = None) -> None:
        self._connection: ConnectionState = EmptyConnectionState()
        self._default_channel = default_channel or Channel()
        self._channels: dict[Channel, aio_pika.RobustChannel] = {}

    def connect(self, connection: "aio_pika.RobustConnection") -> None:
        self._connection = ConnectedState(connection)

    def disconnect(self) -> None:
        self._connection = EmptyConnectionState()
        self._channels.clear()

    async def get_channel(
        self,
        channel: Channel | None = None,
    ) -> "aio_pika.RobustChannel":
        if channel is None:
            channel = self._default_channel

        if (ch := self._channels.get(channel)) is None:
            self._channels[channel] = ch = cast(
                "aio_pika.RobustChannel",
                await self._connection.connection.channel(
                    channel_number=channel.channel_number,
                    publisher_confirms=channel.publisher_confirms,
                    on_return_raises=channel.on_return_raises,
                ),
            )

            if channel.prefetch_count:
                await ch.set_qos(
                    prefetch_count=channel.prefetch_count,
                    global_=channel.global_qos,
                )

        return ch
