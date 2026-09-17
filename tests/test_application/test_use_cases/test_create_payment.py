"""Unit tests for CreatePaymentUseCase."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.application.exceptions import (
    IdempotencyKeyConflictError,
    PaymentAlreadyExistsError,
)
from payments_service.application.use_cases.create_payment import (
    CreatePaymentCommand,
    CreatePaymentUseCase,
)
from payments_service.domain.entities.payment import Payment
from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_payment_success():
    """Успешное создание платежа с записью в outbox."""
    command = CreatePaymentCommand(
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        metadata={"order_id": "123"},
        webhook_url="http://example.com/webhook",
        idempotency_key="test-key-001",
        request_hash="hash-001",
    )

    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.payments = AsyncMock()
    uow.outbox = AsyncMock()

    mapper = MagicMock()
    payment_id = uuid4()
    payment_dto = PaymentDTO(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.PENDING,
        idempotency_key="test-key-001",
        request_hash="hash-001",
        webhook_url="http://example.com/webhook",
        created_at=MagicMock(),
        processed_at=None,
        webhook_delivered_at=None,
        webhook_attempts=0,
        webhook_last_error=None,
    )
    mapper.to_dto.return_value = payment_dto

    use_case = CreatePaymentUseCase(uow=uow, mapper=mapper)
    result, is_new = await use_case(command)

    assert result == payment_dto
    assert is_new is True
    uow.payments.add.assert_called_once()
    uow.outbox.add.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_payment_idempotency_key_conflict_same_hash():
    """Конфликт idempotency_key с тем же request_hash - возврат существующего."""
    command = CreatePaymentCommand(
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        metadata={"order_id": "123"},
        webhook_url="http://example.com/webhook",
        idempotency_key="test-key-001",
        request_hash="hash-001",
    )

    payment_id = uuid4()
    existing_payment = Payment(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.PENDING,
        idempotency_key="test-key-001",
        request_hash="hash-001",
        webhook_url="http://example.com/webhook",
        created_at=MagicMock(),
    )

    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.payments = AsyncMock()
    uow.outbox = AsyncMock()

    uow.payments.add.side_effect = PaymentAlreadyExistsError("test-key-001")
    uow.payments.get_by_idempotency_key.return_value = existing_payment

    mapper = MagicMock()
    payment_dto = PaymentDTO(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.PENDING,
        idempotency_key="test-key-001",
        request_hash="hash-001",
        webhook_url="http://example.com/webhook",
        created_at=MagicMock(),
        processed_at=None,
        webhook_delivered_at=None,
        webhook_attempts=0,
        webhook_last_error=None,
    )
    mapper.to_dto.return_value = payment_dto

    use_case = CreatePaymentUseCase(uow=uow, mapper=mapper)
    result, is_new = await use_case(command)

    assert result == payment_dto
    assert is_new is False
    uow.payments.get_by_idempotency_key.assert_called_once_with("test-key-001")
    # outbox.add не должен вызываться при дубликате
    uow.outbox.add.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_payment_idempotency_key_conflict_different_hash():
    """Конфликт idempotency_key с другим request_hash - ошибка."""
    command = CreatePaymentCommand(
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        metadata={"order_id": "123"},
        webhook_url="http://example.com/webhook",
        idempotency_key="test-key-001",
        request_hash="hash-002",  # Другой hash
    )

    payment_id = uuid4()
    existing_payment = Payment(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.PENDING,
        idempotency_key="test-key-001",
        request_hash="hash-001",  # Исходный hash
        webhook_url="http://example.com/webhook",
        created_at=MagicMock(),
    )

    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.payments = AsyncMock()
    uow.outbox = AsyncMock()

    uow.payments.add.side_effect = PaymentAlreadyExistsError("test-key-001")
    uow.payments.get_by_idempotency_key.return_value = existing_payment

    mapper = MagicMock()

    use_case = CreatePaymentUseCase(uow=uow, mapper=mapper)
    with pytest.raises(IdempotencyKeyConflictError) as exc_info:
        await use_case(command)

    assert exc_info.value.idempotency_key == "test-key-001"
