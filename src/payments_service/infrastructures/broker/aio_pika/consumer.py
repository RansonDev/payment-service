"""Подписка на очередь.

Вырезано из faststream/rabbit/subscriber/usecase.py (RabbitSubscriber), v0.7.5.

Убрано: SubscriberUsecase, CallsCollection и фильтры вызовов, middlewares,
process_msg, get_one/__aiter__, reply-to публикация ответов, AsyncAPI-логика,
prefix-поддержка роутера.

Оставлено дословно то, что определяет корректность подписки:

  * порядок «объявить очередь -> объявить обменник -> bind -> consume».
    bind делается только если очередь мы действительно объявляли
    (queue.declare) и обменник не default: к default exchange привязать
    нельзя, RabbitMQ ответит ACCESS_REFUSED;

  * no_ack=True ровно для ACK_FIRST и никогда иначе;

  * в stop(): basic.cancel по consumer_tag перед обнулением, с проверкой
    channel.is_closed. Это и есть graceful shutdown на уровне подписки —
    брокер перестаёт слать новые доставки, а уже выданные дорабатываются.
"""

from collections.abc import Awaitable, Callable
import logging
from typing import TYPE_CHECKING, Any, cast

from .ack import Acknowledgement, AckPolicy
from .parser import parse_message

__all__ = ["AckPolicy", "RabbitConsumer"]

if TYPE_CHECKING:
    from aio_pika import IncomingMessage, RobustQueue

    from .declarer import RabbitDeclarer
    from .message import RabbitMessage
    from .schemas import Channel, RabbitExchange, RabbitQueue

logger = logging.getLogger(__name__)

Handler = Callable[["RabbitMessage"], Awaitable[None]]


class RabbitConsumer:
    def __init__(
        self,
        declarer: "RabbitDeclarer",
        queue: "RabbitQueue",
        handler: Handler,
        *,
        exchange: "RabbitExchange | None" = None,
        ack_policy: AckPolicy = AckPolicy.REJECT_ON_ERROR,
        channel: "Channel | None" = None,
        consume_args: dict[str, Any] | None = None,
    ) -> None:
        self.declarer = declarer
        self.queue = queue
        self.exchange = exchange
        self.handler = handler
        self.ack_policy = ack_policy
        self.channel = channel
        self.consume_args = consume_args or {}

        self._queue_obj: RobustQueue | None = None
        self._consumer_tag: str | None = None

    async def start(self) -> None:
        self._queue_obj = queue = await self.declarer.declare_queue(
            self.queue,
            channel=self.channel,
        )

        if (
            self.exchange is not None
            and self.queue.declare
            and self.exchange.name  # не default exchange
        ):
            exchange = await self.declarer.declare_exchange(
                self.exchange,
                channel=self.channel,
            )
            await queue.bind(
                exchange,
                routing_key=self.queue.routing(),
                arguments=self.queue.bind_arguments,
                timeout=self.queue.timeout,
                robust=self.queue.robust,
            )

        self._consumer_tag = await queue.consume(
            self._on_message,
            no_ack=self.ack_policy is AckPolicy.ACK_FIRST,
            arguments=self.consume_args,
        )

        logger.info(
            "Consuming queue=%s exchange=%s",
            self.queue.name,
            getattr(self.exchange, "name", ""),
        )

    async def stop(self) -> None:
        if self._queue_obj is not None:
            if self._consumer_tag is not None:
                if not self._queue_obj.channel.is_closed:
                    await self._queue_obj.cancel(self._consumer_tag)
                self._consumer_tag = None
            self._queue_obj = None

        logger.info("Stopped consuming queue=%s", self.queue.name)

    async def _on_message(self, raw: Any) -> None:
        message = parse_message(cast("IncomingMessage", raw))

        try:
            async with Acknowledgement(message, self.ack_policy):
                await self.handler(message)
        except Exception:
            # сообщение уже подтверждено политикой в __aexit__;
            # здесь остаётся только не уронить callback aio-pika
            logger.exception(
                "Unhandled error in handler queue=%s message_id=%s",
                self.queue.name,
                message.message_id,
            )
