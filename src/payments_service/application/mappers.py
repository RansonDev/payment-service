"""Мапперы слоя приложения."""

from dataclasses import dataclass
from typing import final

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.application.interfaces.mappers import DtoEntityMapperProtocol
from payments_service.domain.entities.payment import Payment


@final
@dataclass(frozen=True, slots=True)
class PaymentMapper(DtoEntityMapperProtocol):
    """Маппер между доменной сущностью Payment и DTO.

    Часть слоя приложения, обрабатывает конвертацию между:
    - Domain Entities (бизнес-логика)
    - Application DTOs (передача данных между use-cases)
    """

    def to_dto(self, entity: Payment) -> PaymentDTO:
        """Конвертация доменной сущности в DTO."""
        return PaymentDTO(
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

    def to_entity(self, dto: PaymentDTO) -> Payment:
        """Конвертация DTO в доменную сущность."""
        return Payment(
            id=dto.id,
            amount=dto.amount,
            currency=dto.currency,
            description=dto.description,
            payment_metadata=dto.payment_metadata,
            status=dto.status,
            idempotency_key=dto.idempotency_key,
            request_hash=dto.request_hash,
            webhook_url=dto.webhook_url,
            created_at=dto.created_at,
            processed_at=dto.processed_at,
            webhook_delivered_at=dto.webhook_delivered_at,
            webhook_attempts=dto.webhook_attempts,
            webhook_last_error=dto.webhook_last_error,
        )
