"""Декларативные описания топологии RabbitMQ.

Сохранено главное — __eq__/__hash__. Именно они позволяют декларатору
кешировать уже объявленные объекты: два RabbitQueue с одинаковыми
именем/durable/exclusive/auto_delete/arguments считаются одним и тем же
объектом, и повторная декларация не идёт в брокер.
"""

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum, unique
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from aio_pika.abc import TimeoutType


@unique
class ExchangeType(str, Enum):
    FANOUT = "fanout"
    DIRECT = "direct"
    TOPIC = "topic"
    HEADERS = "headers"
    X_DELAYED_MESSAGE = "x-delayed-message"
    X_CONSISTENT_HASH = "x-consistent-hash"
    X_MODULUS_HASH = "x-modulus-hash"


class QueueType(str, Enum):
    """Значения в нижнем регистре — так их ждёт RabbitMQ API."""

    CLASSIC = "classic"
    QUORUM = "quorum"
    STREAM = "stream"


@dataclass
class Channel:
    """Параметры AMQP-канала."""

    prefetch_count: int | None = None
    """Лимит неподтверждённых сообщений на канале.
    https://www.rabbitmq.com/docs/consumer-prefetch
    """

    global_qos: bool = False
    """Делить лимит между всеми подписчиками канала."""

    channel_number: int | None = None

    publisher_confirms: bool = True
    """При True publish() дожидается подтверждения брокера и возвращает bool."""

    on_return_raises: bool = True
    """Бросать DeliveryError, если mandatory-сообщение вернулось."""

    def __hash__(self) -> int:
        return id(self)


def _hash_dict(d: Any) -> Any:
    if isinstance(d, dict):
        return frozenset((k, _hash_dict(v)) for k, v in d.items())
    return d


class RabbitQueue:
    """Описание очереди RabbitMQ.

    https://www.rabbitmq.com/docs/queues
    """

    __slots__ = (
        "arguments",
        "auto_delete",
        "bind_arguments",
        "declare",
        "durable",
        "exclusive",
        "name",
        "robust",
        "routing_key",
        "timeout",
    )

    def __init__(
        self,
        name: str,
        queue_type: QueueType = QueueType.CLASSIC,
        durable: bool | None = None,
        exclusive: bool = False,
        declare: bool = True,
        auto_delete: bool = False,
        arguments: dict[str, Any] | None = None,
        timeout: "TimeoutType" = None,
        robust: bool = True,
        bind_arguments: dict[str, Any] | None = None,
        routing_key: str = "",
    ) -> None:
        """:param name: Имя очереди в RabbitMQ.
        :param durable: Переживает ли очередь рестарт брокера.
        :param exclusive: Очередь видна только текущему соединению и удаляется с ним.
        :param declare: False — не объявлять, а подключиться к существующей
                        (aio-pika `passive`). Упадёт, если очереди нет.
        :param auto_delete: Удалить очередь после закрытия соединения.
        :param arguments: Аргументы декларации, x-* опции.
                          https://www.rabbitmq.com/docs/queues#optional-arguments
        :param timeout: Таймаут подтверждения от RabbitMQ.
        :param robust: Пересоздавать объект при реконнекте.
        :param bind_arguments: Опции биндинга очередь-обменник.
        :param routing_key: Явный routing key биндинга. По умолчанию — имя очереди.
        """
        if queue_type in (QueueType.QUORUM, QueueType.STREAM):
            if durable is None:
                durable = True
            elif not durable:
                msg = "Quorum and Stream queues must be durable"
                raise ValueError(msg)
        elif durable is None:
            durable = True

        self.name = name
        self.durable = durable
        self.exclusive = exclusive
        self.declare = declare
        self.auto_delete = auto_delete
        self.arguments = {"x-queue-type": queue_type.value, **(arguments or {})}
        self.timeout = timeout
        self.robust = robust
        self.bind_arguments = bind_arguments
        self.routing_key = routing_key

    def routing(self) -> str:
        return self.routing_key or self.name

    def copy_with(self, **overrides: Any) -> "RabbitQueue":
        new = deepcopy(self)
        for key, value in overrides.items():
            setattr(new, key, value)
        return new

    def __repr__(self) -> str:
        body = ""
        if self.declare:
            body = (
                f", durable={self.durable}, exclusive={self.exclusive}"
                f", auto_delete={self.auto_delete}"
            )
        if (r := self.routing()) != self.name:
            body = f", routing_key='{r}'{body}"
        return f"{self.__class__.__name__}({self.name}{body})"

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, RabbitQueue):
            return NotImplemented
        return (
            self.name == value.name
            and self.durable == value.durable
            and self.exclusive == value.exclusive
            and self.auto_delete == value.auto_delete
            and (self.arguments or {}) == (value.arguments or {})
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.name,
                self.durable,
                self.exclusive,
                self.auto_delete,
                _hash_dict(self.arguments or {}),
            ),
        )


class RabbitExchange:
    """Описание обменника RabbitMQ."""

    __slots__ = (
        "arguments",
        "auto_delete",
        "bind_arguments",
        "bind_to",
        "declare",
        "durable",
        "name",
        "robust",
        "routing_key",
        "timeout",
        "type",
    )

    def __init__(
        self,
        name: str = "",
        type: ExchangeType = ExchangeType.DIRECT,  # noqa: A002
        durable: bool = True,
        auto_delete: bool = False,
        declare: bool = True,
        arguments: dict[str, Any] | None = None,
        timeout: "TimeoutType" = None,
        robust: bool = True,
        bind_to: "RabbitExchange | None" = None,
        bind_arguments: dict[str, Any] | None = None,
        routing_key: str = "",
    ) -> None:
        """:param name: Имя обменника. Пустое имя — default exchange.
        :param bind_to: Другой обменник, к которому привязать текущий (e2e binding).
        :param routing_key: Routing key биндинга, работает только вместе с bind_to.
        """
        if routing_key and bind_to is None:
            msg = "`routing_key` binds exchange to another one, pass `bind_to` too"
            raise ValueError(msg)

        self.name = name
        self.type = type
        self.durable = durable
        self.auto_delete = auto_delete
        self.declare = declare
        self.arguments = arguments
        self.timeout = timeout
        self.robust = robust
        self.bind_to = bind_to
        self.bind_arguments = bind_arguments
        self.routing_key = routing_key

    def routing(self) -> str:
        return self.routing_key or self.name

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.name}, type={self.type}"
            f", routing_key='{self.routing()}', durable={self.durable})"
        )

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, RabbitExchange):
            return NotImplemented
        return (
            self.name == value.name
            and self.type == value.type
            and self.durable == value.durable
            and self.auto_delete == value.auto_delete
            and (self.arguments or {}) == (value.arguments or {})
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.name,
                self.type,
                self.durable,
                self.auto_delete,
                _hash_dict(self.arguments or {}),
            ),
        )


# --- Типизированные аргументы деклараций -------------------------------------
# Оставлено как есть: избавляет от опечаток в x-* ключах.

CommonQueueArgs = TypedDict(
    "CommonQueueArgs",
    {
        "x-queue-leader-locator": Literal["client-local", "balanced"],
        "x-max-length-bytes": int,
    },
    total=False,
)

SharedClassicAndQuorumQueueArgs = TypedDict(
    "SharedClassicAndQuorumQueueArgs",
    {
        "x-expires": int,
        "x-message-ttl": int,
        "x-single-active-consumer": bool,
        "x-dead-letter-exchange": str,
        "x-dead-letter-routing-key": str,
        "x-max-length": int,
    },
    total=False,
)

ClassicQueueSpecificArgs = TypedDict(
    "ClassicQueueSpecificArgs",
    {
        "x-overflow": Literal["drop-head", "reject-publish", "reject-publish-dlx"],
        "x-queue-master-locator": Literal["client-local", "balanced"],
        "x-max-priority": int,
        "x-queue-mode": Literal["default", "lazy"],
        "x-queue-version": int,
    },
    total=False,
)

QuorumQueueSpecificArgs = TypedDict(
    "QuorumQueueSpecificArgs",
    {
        "x-overflow": Literal["drop-head", "reject-publish"],
        "x-delivery-limit": int,
        "x-quorum-initial-group-size": int,
        "x-quorum-target-group-size": int,
        "x-dead-letter-strategy": Literal["at-most-once", "at-least-once"],
        "x-max-in-memory-length": int,
        "x-max-in-memory-bytes": int,
    },
    total=False,
)


class ClassicQueueArgs(
    CommonQueueArgs,
    SharedClassicAndQuorumQueueArgs,
    ClassicQueueSpecificArgs,
):
    """rabbit_classic_queue.erl"""


class QuorumQueueArgs(
    CommonQueueArgs,
    SharedClassicAndQuorumQueueArgs,
    QuorumQueueSpecificArgs,
):
    """rabbit_quorum_queue.erl"""
