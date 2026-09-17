"""Маппер между доменной сущностью Payment и SQLAlchemy-моделью."""

from dataclasses import dataclass
from typing import final

from payments_service.application.interfaces.db_mapper import DbMapperProtocol
from payments_service.domain.entities.payment import Payment as DomainPayment
from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus
from payments_service.infrastructures.db.models.payment import Payment as PaymentModel


@final
@dataclass(frozen=True, slots=True)
class PaymentDbMapper(DbMapperProtocol[PaymentModel]):
    """Маппер для преобразования Payment между доменом и БД."""

    def to_domain(self, model: PaymentModel) -> DomainPayment:
        """Преобразовать модель БД в доменную сущность.

        Args:
            model: Модель SQLAlchemy.

        Returns:
            Доменная сущность Payment.
        """
        # SQLAlchemy возвращает currency и status как строки, конвертируем в enums
        currency = (
            Currency(model.currency)
            if isinstance(model.currency, str)
            else model.currency
        )
        status = (
            PaymentStatus(model.status)
            if isinstance(model.status, str)
            else model.status
        )

        return DomainPayment(
            id=model.id,
            amount=model.amount,
            currency=currency,
            description=model.description,
            payment_metadata=model.payment_metadata,
            status=status,
            idempotency_key=model.idempotency_key,
            request_hash=model.request_hash,
            webhook_url=model.webhook_url,
            created_at=model.created_at,
            processed_at=model.processed_at,
            webhook_delivered_at=model.webhook_delivered_at,
            webhook_attempts=model.webhook_attempts,
            webhook_last_error=model.webhook_last_error,
        )

    def to_model(self, entity: DomainPayment) -> PaymentModel:
        """Преобразовать доменную сущность в модель БД.

        Args:
            entity: Доменная сущность Payment.

        Returns:
            Модель SQLAlchemy.
        """
        return PaymentModel(
            id=entity.id,
            amount=entity.amount,
            currency=entity.currency,
            description=entity.description,
            payment_metadata=entity.payment_metadata,
            status=entity.status,
            idempotency_key=entity.idempotency_key,
            request_hash=entity.request_hash,
            webhook_url=entity.webhook_url,
            created_at=entity.created_at,
            processed_at=entity.processed_at,
            webhook_delivered_at=entity.webhook_delivered_at,
            webhook_attempts=entity.webhook_attempts,
            webhook_last_error=entity.webhook_last_error,
        )

    def insert(self, model: PaymentModel) -> None:
        """Вставка модели не реализована напрямую.

        Используется через репозиторий.
        """
        msg = "Insert operation should be done through repository"
        raise NotImplementedError(msg)

    def update(self, model: PaymentModel) -> None:
        """Обновление модели не реализовано напрямую.

        Используется через репозиторий.
        """
        msg = "Update operation should be done through repository"
        raise NotImplementedError(msg)

    def delete(self, model: PaymentModel) -> None:
        """Удаление модели не реализовано напрямую.

        Используется через репозиторий.
        """
        msg = "Delete operation should be done through repository"
        raise NotImplementedError(msg)
