"""Репозиторий платежей."""

from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING, final
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from payments_service.application.exceptions import PaymentAlreadyExistsError
from payments_service.application.interfaces.repositories import (
    PaymentRepositoryProtocol,
)
from payments_service.domain.value_objects.payment_status import PaymentStatus
from payments_service.infrastructures.db.models.payment import Payment as PaymentModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from payments_service.domain.entities.payment import Payment as PaymentEntity
    from payments_service.infrastructures.db.mappers.payment import PaymentDbMapper


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentRepositorySQLAlchemy(PaymentRepositoryProtocol):
    """Репозиторий платежей на SQLAlchemy."""

    session: "AsyncSession"
    mapper: "PaymentDbMapper"

    async def add(self, payment: "PaymentEntity") -> None:
        """Сохранить платёж.

        КРИТИЧЕСКИ ВАЖНО: делает flush() внутри, чтобы IntegrityError по
        idempotency_key всплывала здесь, а не в __aexit__ UoW.

        Args:
            payment: Доменная сущность платежа.

        Raises:
            PaymentAlreadyExistsError: idempotency_key уже занят.
        """
        model = self.mapper.to_model(payment)
        self.session.add(model)
        try:
            await self.session.flush()
        except IntegrityError as e:
            if "idempotency_key" in str(e.orig):
                raise PaymentAlreadyExistsError(payment.idempotency_key) from None
            raise

    async def get_by_id(self, payment_id: UUID) -> "PaymentEntity | None":
        """Получить платёж по ID.

        Args:
            payment_id: UUID платежа.

        Returns:
            Доменная сущность или None.
        """
        stmt = select(PaymentModel).where(PaymentModel.id == payment_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self.mapper.to_domain(model) if model else None

    async def get_by_idempotency_key(self, key: str) -> "PaymentEntity | None":
        """Получить платёж по ключу идемпотентности.

        Args:
            key: Ключ идемпотентности.

        Returns:
            Доменная сущность или None.
        """
        stmt = select(PaymentModel).where(PaymentModel.idempotency_key == key)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self.mapper.to_domain(model) if model else None

    async def update(self, payment: "PaymentEntity") -> None:
        """Обновить существующий платёж.

        Args:
            payment: Доменная сущность с изменениями.
        """
        stmt = select(PaymentModel).where(PaymentModel.id == payment.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            model = self.mapper.to_model(payment)
            self.session.add(model)
        else:
            model.amount = payment.amount
            model.currency = payment.currency
            model.description = payment.description
            model.payment_metadata = payment.payment_metadata
            model.status = payment.status
            model.idempotency_key = payment.idempotency_key
            model.request_hash = payment.request_hash
            model.webhook_url = payment.webhook_url
            model.created_at = payment.created_at
            model.processed_at = payment.processed_at
            model.webhook_delivered_at = payment.webhook_delivered_at
            model.webhook_attempts = payment.webhook_attempts
            model.webhook_last_error = payment.webhook_last_error

        await self.session.flush()

    async def try_mark_processed(
        self, payment_id: UUID, status: PaymentStatus, message: str | None
    ) -> bool:
        """Записать результат, только если платёж ещё в PENDING."""
        stmt = (
            update(PaymentModel)
            .where(PaymentModel.id == payment_id)
            .where(PaymentModel.status == PaymentStatus.PENDING)
            .values(
                status=status,
                processed_at=datetime.now(UTC),
                webhook_last_error=message if status == PaymentStatus.FAILED else None,
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def try_mark_webhook_delivered(self, payment_id: UUID) -> bool:
        """Отметить доставку вебхука, только если она еще не была отмечена."""
        stmt = (
            update(PaymentModel)
            .where(PaymentModel.id == payment_id)
            .where(PaymentModel.webhook_delivered_at.is_(None))
            .values(
                webhook_delivered_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0
