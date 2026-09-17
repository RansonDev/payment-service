"""Преобразование aio-pika IncomingMessage <-> прикладное сообщение.

Что унесено осознанно:
  * correlation_id проставляется всегда, даже если публикующая сторона его не
    дала — иначе сквозная трассировка рвётся на первом же хопе;
  * persist -> DeliveryMode.PERSISTENT. Одного durable у очереди мало:
    неперсистентное сообщение в durable-очереди всё равно теряется при
    рестарте брокера;
  * timestamp проставляется автоматически в UTC.
"""

import datetime
import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from aio_pika import Message
from aio_pika.abc import DeliveryMode

from .message import ContentTypes, RabbitMessage

if TYPE_CHECKING:
    from aio_pika import IncomingMessage
    from aio_pika.abc import DateType, HeadersType


def gen_cor_id() -> str:
    return str(uuid4())


def parse_message(message: "IncomingMessage") -> RabbitMessage:
    return RabbitMessage(
        raw_message=message,
        body=message.body,
        headers=dict(message.headers or {}),
        reply_to=message.reply_to or "",
        content_type=message.content_type,
        message_id=message.message_id or gen_cor_id(),
        correlation_id=message.correlation_id or gen_cor_id(),
    )


def encode_body(message: Any) -> tuple[bytes, str | None]:
    """Тело -> (bytes, content_type)."""
    if message is None:
        return b"", None
    if isinstance(message, bytes):
        return message, None
    if isinstance(message, str):
        return message.encode(), ContentTypes.TEXT.value
    # default=str покрывает Decimal, UUID и datetime — для платёжных
    # payload'ов это ровно те три типа, которые ломают json.dumps
    return json.dumps(message, default=str).encode(), ContentTypes.JSON.value


def build_message(
    message: Any,
    *,
    persist: bool = True,
    reply_to: str | None = None,
    headers: "HeadersType | None" = None,
    content_type: str | None = None,
    content_encoding: str | None = None,
    priority: int | None = None,
    correlation_id: str | None = None,
    expiration: "DateType" = None,
    message_id: str | None = None,
    timestamp: "DateType" = None,
    message_type: str | None = None,
    user_id: str | None = None,
    app_id: str | None = None,
) -> Message:
    """Собрать aio_pika.Message. Готовый Message возвращается как есть."""
    if isinstance(message, Message):
        return message

    body, generated_content_type = encode_body(message)

    return Message(
        body,
        content_type=content_type or generated_content_type,
        delivery_mode=(
            DeliveryMode.PERSISTENT if persist else DeliveryMode.NOT_PERSISTENT
        ),
        reply_to=reply_to,
        correlation_id=correlation_id or gen_cor_id(),
        headers=headers,
        content_encoding=content_encoding,
        priority=priority,
        expiration=expiration,
        message_id=message_id,
        timestamp=timestamp or datetime.datetime.now(tz=datetime.UTC),
        type=message_type,
        user_id=user_id,
        app_id=app_id,
    )
