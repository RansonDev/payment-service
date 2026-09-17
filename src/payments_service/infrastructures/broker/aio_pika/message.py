"""Обёртка над входящим сообщением.

Ради чего берётся — двойная защита от повторного подтверждения:
  1. `committed` фиксирует первое решение, второй ack/nack/reject молча
     игнорируется. Без этого легко словить двойной ack из хендлера и из
     обвязки, а RabbitMQ на такое закрывает канал с PRECONDITION_FAILED;
  2. `pika_message.locked` — проверка на стороне aio-pika: сообщение,
     доставленное с no_ack=True, подтверждать нельзя вообще.
"""

from enum import Enum
import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from aio_pika import IncomingMessage


_NOT_CACHED = object()


class AckStatus(str, Enum):
    ACKED = "ACKED"
    NACKED = "NACKED"
    REJECTED = "REJECTED"


class ContentTypes(str, Enum):
    TEXT = "text/plain"
    JSON = "application/json"


class RabbitMessage:
    """Входящее сообщение RabbitMQ с безопасным подтверждением."""

    __slots__ = (
        "_decoded",
        "body",
        "committed",
        "content_type",
        "correlation_id",
        "headers",
        "message_id",
        "raw_message",
        "reply_to",
    )

    def __init__(
        self,
        raw_message: "IncomingMessage",
        body: bytes,
        *,
        headers: dict[str, Any] | None = None,
        reply_to: str = "",
        content_type: str | None = None,
        correlation_id: str | None = None,
        message_id: str | None = None,
    ) -> None:
        self.raw_message = raw_message
        self.body = body
        self.headers = headers or {}
        self.reply_to = reply_to
        self.content_type = content_type
        self.correlation_id = correlation_id or str(uuid4())
        self.message_id = message_id or self.correlation_id

        self.committed: AckStatus | None = None
        self._decoded: Any = _NOT_CACHED

    @property
    def redelivered(self) -> bool:
        return bool(self.raw_message.redelivered)

    def decode(self) -> Any:
        """Разбор тела по content-type. Результат кешируется."""
        if self._decoded is not _NOT_CACHED:
            return self._decoded

        body: Any = self.body
        content_type = self.content_type

        if content_type:
            if content_type == ContentTypes.TEXT.value:
                body = self.body.decode()
            elif content_type.startswith(ContentTypes.JSON.value):
                body = json.loads(self.body)
        else:
            try:
                body = json.loads(self.body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        self._decoded = body
        return body

    async def ack(self, multiple: bool = False) -> None:
        if self.committed is not None:
            return
        self.committed = AckStatus.ACKED
        if self.raw_message.locked:
            return
        await self.raw_message.ack(multiple=multiple)

    async def nack(self, multiple: bool = False, requeue: bool = True) -> None:
        if self.committed is not None:
            return
        self.committed = AckStatus.NACKED
        if self.raw_message.locked:
            return
        await self.raw_message.nack(multiple=multiple, requeue=requeue)

    async def reject(self, requeue: bool = False) -> None:
        if self.committed is not None:
            return
        self.committed = AckStatus.REJECTED
        if self.raw_message.locked:
            return
        await self.raw_message.reject(requeue=requeue)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message_id={self.message_id}, "
            f"correlation_id={self.correlation_id}, headers={self.headers}, "
            f"committed={self.committed})"
        )
