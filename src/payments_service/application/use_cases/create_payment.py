"""Use-case создания платежа."""

from dataclasses import dataclass
from decimal import Decimal
import json
from typing import TYPE_CHECKING, Any, final
from uuid import uuid4

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.application.exceptions import (
    IdempotencyKeyConflictError,
    PaymentAlreadyExistsError,
)
from payments_service.domain.entities.payment import Payment
from payments_service.infrastructures.context import context

if TYPE_CHECKING:
    from payments_service.application.interfaces.mappers import (
        DtoEntityMapperProtocol,
    )
    from payments_service.application.interfaces.uow import UnitOfWorkProtocol
    from payments_service.domain.value_objects.currency import Currency


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatePaymentCommand:
    """Команда создания платежа."""

    amount: Decimal
    currency: "Currency"
    description: str
    metadata: dict[str, Any]
    webhook_url: str
    idempotency_key: str
    request_hash: str


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CreatePaymentUseCase:
    """Use-case создания платежа.

    КРИТИЧЕСКИ ВАЖНО: платёж и событие о нём попадают в базу ОДНИМ коммитом.
    Один async with self.uow, обе вставки внутри.

    Обработка конфликта по idempotency_key СНАРУЖИ блока async with, так как
    после провалившегося flush сессия непригодна.
    """

    uow: "UnitOfWorkProtocol"
    mapper: "DtoEntityMapperProtocol"

    async def __call__(self, command: CreatePaymentCommand) -> tuple[PaymentDTO, bool]:
        """Создать платёж.

        Возвращает кортеж (PaymentDTO, created), где created=True если платёж
        только что создан, False если это повтор с тем же idempotency_key.

        Args:
            command: Команда создания платежа.

        Returns:
            Кортеж (платёж, создан_ли_новый).

        Raises:
            IdempotencyKeyConflictError: Тот же ключ, другое тело запроса.
            DomainValidationError: Нарушение инвариантов домена.
        """
        payment = Payment(
            id=uuid4(),
            amount=command.amount,
            currency=command.currency,
            description=command.description,
            payment_metadata=command.metadata,
            webhook_url=command.webhook_url,
            idempotency_key=command.idempotency_key,
            request_hash=command.request_hash,
        )

        try:
            # Одна транзакция для payment и outbox - иначе платёж без события
            async with self.uow:
                await self.uow.payments.add(payment)

                trace_id = context.get("log_context", {}).get("trace_id", "")

                await self.uow.outbox.add(
                    exchange="payments",
                    routing_key="payments.new",
                    payload=json.dumps({"payment_id": str(payment.id)}).encode(),
                    headers={"x-attempt": "0", "x-trace-id": trace_id},
                    content_type="application/json",
                )
        except PaymentAlreadyExistsError:
            # __aexit__ уже откатил транзакцию, сессия снова рабочая
            async with self.uow:
                existing = await self.uow.payments.get_by_idempotency_key(
                    command.idempotency_key
                )

            if existing is None:
                raise

            if existing.request_hash != command.request_hash:
                raise IdempotencyKeyConflictError(command.idempotency_key) from None

            return self.mapper.to_dto(existing), False

        return self.mapper.to_dto(payment), True
