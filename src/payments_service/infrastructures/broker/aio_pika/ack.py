"""Политика подтверждения сообщений.

Вырезано из faststream/middlewares/acknowledgement/{config,middleware}.py
и faststream/exceptions.py (v0.7.5).

Убрано: BaseMiddleware, ContextRepo, LoggerState — логика переписана
из middleware-обёртки в обычный async context manager.

Зачем этот кусок: разница между nack(requeue=True) и reject(requeue=False)
решает, уйдёт ли сообщение в DLQ или встанет в бесконечную петлю переобработки.
FastStream формализует это в четыре явных режима, плюс даёт хендлеру способ
перебить режим точечно, бросив AckMessage/NackMessage/RejectMessage.
"""

import asyncio
from enum import Enum
import logging
from types import TracebackType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .message import RabbitMessage

logger = logging.getLogger(__name__)


class AckPolicy(str, Enum):
    ACK_FIRST = "ack_first"
    """Подтвердить сразу при получении (consume с no_ack=True).
    Быстро, но сообщение теряется при падении обработчика."""

    ACK = "ack"
    """Подтверждать после обработки в любом случае, даже при исключении."""

    REJECT_ON_ERROR = "reject_on_error"
    """При необработанном исключении — reject(requeue=False).
    Сообщение уходит в DLX, если он настроен на очереди. Значение по умолчанию."""

    NACK_ON_ERROR = "nack_on_error"
    """При необработанном исключении — nack(requeue=True).
    Сообщение вернётся в ту же очередь — осторожно, это петля без задержки."""

    MANUAL = "manual"
    """Никаких автоматических действий, хендлер подтверждает сам."""


class HandlerException(Exception):  # noqa: N818
    """База для управляющих исключений — они не считаются ошибкой."""


class AckMessage(HandlerException):
    def __init__(self, multiple: bool = False) -> None:
        self.extra_options: dict[str, Any] = {"multiple": multiple}


class NackMessage(HandlerException):
    def __init__(self, multiple: bool = False, requeue: bool = True) -> None:
        self.extra_options: dict[str, Any] = {
            "multiple": multiple,
            "requeue": requeue,
        }


class RejectMessage(HandlerException):
    def __init__(self, requeue: bool = False) -> None:
        self.extra_options: dict[str, Any] = {"requeue": requeue}


class Acknowledgement:
    """Контекстный менеджер, подтверждающий сообщение по политике.

        async with Acknowledgement(message, AckPolicy.REJECT_ON_ERROR):
            await handler(message)

    Управляющие исключения гасятся (обработаны штатно), остальные
    пробрасываются наверх после того, как сообщение подтверждено.
    """

    __slots__ = ("ack_policy", "message")

    def __init__(self, message: "RabbitMessage", ack_policy: AckPolicy) -> None:
        self.message = message
        self.ack_policy = ack_policy

    async def __aenter__(self) -> "Acknowledgement":
        if self.ack_policy is AckPolicy.ACK_FIRST:
            await self.message.ack()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> bool:
        if self.ack_policy in (AckPolicy.ACK_FIRST, AckPolicy.MANUAL):
            return False

        if exc_type is None:
            await self.message.ack()

        elif isinstance(exc_val, HandlerException):
            if isinstance(exc_val, AckMessage):
                await self.message.ack(**exc_val.extra_options)
            elif isinstance(exc_val, NackMessage):
                await self.message.nack(**exc_val.extra_options)
            elif isinstance(exc_val, RejectMessage):
                await self.message.reject(**exc_val.extra_options)
            # исключение обработано — гасим
            return True

        elif isinstance(exc_val, asyncio.CancelledError):
            # отмена при шатдауне: ничего не подтверждаем, сообщение
            # вернётся брокером после разрыва соединения
            return False

        elif self.ack_policy is AckPolicy.REJECT_ON_ERROR:
            await self.message.reject()

        elif self.ack_policy is AckPolicy.NACK_ON_ERROR:
            await self.message.nack()

        elif self.ack_policy is AckPolicy.ACK:
            await self.message.ack()

        return False
