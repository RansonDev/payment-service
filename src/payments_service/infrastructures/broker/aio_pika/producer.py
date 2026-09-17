"""Публикация сообщений.

Ключевая деталь, ради которой это и переносится:

    declare_exchange(exchange, declare=False)

Обменник на публикации берётся в passive-режиме. То есть продюсер не пытается
переобъявить его своими параметрами на каждую отправку — он лишь получает
ссылку на уже существующий. Если объявить обменник с отличающимися
параметрами, RabbitMQ ответит PRECONDITION_FAILED и закроет канал; passive
снимает этот класс ошибок целиком.

publisher confirms включаются не здесь, а на канале (Channel.publisher_confirms,
по умолчанию True). При них exchange.publish() дожидается basic.ack от брокера
и возвращает подтверждение — то, что нужно outbox-публикатору, чтобы отмечать
событие отправленным только после реального приёма брокером.
"""

from typing import TYPE_CHECKING, Any

from .parser import build_message
from .schemas import RabbitExchange

if TYPE_CHECKING:
    from aio_pika.abc import TimeoutType
    import aiormq

    from .declarer import RabbitDeclarer
    from .schemas import Channel


class RabbitProducer:
    __slots__ = ("_channel", "_declarer", "app_id")

    def __init__(
        self,
        declarer: "RabbitDeclarer",
        *,
        app_id: str | None = None,
        channel: "Channel | None" = None,
    ) -> None:
        self._declarer = declarer
        self.app_id = app_id
        self._channel = channel

    async def publish(
        self,
        message: Any,
        *,
        routing_key: str,
        exchange: RabbitExchange | None = None,
        persist: bool = True,
        mandatory: bool = True,
        immediate: bool = False,
        timeout: "TimeoutType" = None,
        **message_options: Any,
    ) -> "aiormq.abc.ConfirmationFrameType | None":
        """Опубликовать сообщение.

        :param mandatory: брокер вернёт сообщение, если ни одна очередь его не
                          приняла. Вместе с publisher confirms это отличает
                          «принято в очередь» от «принято и выброшено».
        """
        msg = build_message(
            message,
            persist=persist,
            app_id=message_options.pop("app_id", self.app_id),
            **message_options,
        )

        exchange_obj = await self._declarer.declare_exchange(
            exchange=exchange or RabbitExchange(),
            declare=False,
            channel=self._channel,
        )

        return await exchange_obj.publish(
            message=msg,
            routing_key=routing_key,
            mandatory=mandatory,
            immediate=immediate,
            timeout=timeout,
        )
