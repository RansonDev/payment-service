"""Протоколы репозиториев.

Заменяет application/interfaces/repositories.py из шаблона.

Два репозитория вместо одного. Оба получают одну и ту же AsyncSession из
REQUEST-скоупа dishka, поэтому физически находятся в одной транзакции ещё до
того, как их увидит UnitOfWork.
"""

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from payments_service.domain.entities.payment import Payment as PaymentEntity
    from payments_service.domain.value_objects.payment_status import PaymentStatus


class PaymentRepositoryProtocol(Protocol):
    @abstractmethod
    async def add(self, payment: "PaymentEntity") -> None:
        """Сохранить платёж.

        Делает flush внутри, поэтому нарушение уникальности idempotency_key
        всплывает здесь, а не на коммите. Это важно: без flush ошибка
        возникала бы уже в __aexit__ UnitOfWork, где перехватить её адресно
        невозможно.

        Raises:
            PaymentAlreadyExistsError: idempotency_key уже занят.
        """
        ...

    @abstractmethod
    async def get_by_id(self, payment_id: "UUID") -> "PaymentEntity | None": ...

    @abstractmethod
    async def get_by_idempotency_key(self, key: str) -> "PaymentEntity | None": ...

    @abstractmethod
    async def update(self, payment: "PaymentEntity") -> None: ...

    @abstractmethod
    async def try_mark_processed(
        self, payment_id: "UUID", status: "PaymentStatus", message: str | None
    ) -> bool:
        """Записать результат, только если платёж ещё в PENDING.

        Возвращает False, если платёж уже обработан другой доставкой.
        """
        ...

    @abstractmethod
    async def try_mark_webhook_delivered(self, payment_id: "UUID") -> bool:
        """Отметить доставку вебхука, только если она ещё не отмечена.

        Возвращает False, если доставка уже была отмечена.
        """
        ...


class OutboxRepositoryProtocol(Protocol):
    @abstractmethod
    async def add(
        self,
        *,
        routing_key: str,
        payload: bytes,
        exchange: str = "",
        headers: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> int:
        """Положить событие в outbox. Возвращает id строки."""
        ...
