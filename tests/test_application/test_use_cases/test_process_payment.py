"""Unit tests for ProcessPaymentUseCase."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from payments_service.application.interfaces.gateway import GatewayResult
from payments_service.application.use_cases.process_payment import ProcessPaymentUseCase
from payments_service.domain.entities.payment import Payment
from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_payment_gateway_success():
    """Успешная обработка платежа шлюзом."""
    payment_id = uuid4()
    payment = Payment(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.PENDING,
        idempotency_key="test-key-001",
        request_hash="hash-001",
        webhook_url="http://example.com/webhook",
        created_at=datetime.now(UTC),
    )

    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.payments = AsyncMock()
    uow.payments.get_for_update.return_value = payment

    gateway = AsyncMock()
    gateway.charge.return_value = GatewayResult(success=True, message="Payment approved")

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)
    await use_case(payment_id)

    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None
    assert payment.webhook_delivered_at is not None
    gateway.charge.assert_called_once_with(payment)
    webhook.send.assert_called_once()
    # update вызывается дважды: после gateway и после webhook
    assert uow.payments.update.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_payment_gateway_failure():
    """Провал платежа в шлюзе."""
    payment_id = uuid4()
    payment = Payment(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.PENDING,
        idempotency_key="test-key-001",
        request_hash="hash-001",
        webhook_url="http://example.com/webhook",
        created_at=datetime.now(UTC),
    )

    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.payments = AsyncMock()
    uow.payments.get_for_update.return_value = payment

    gateway = AsyncMock()
    gateway.charge.return_value = GatewayResult(
        success=False, message="Insufficient funds"
    )

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)
    await use_case(payment_id)

    assert payment.status == PaymentStatus.FAILED
    assert payment.processed_at is not None
    assert payment.webhook_delivered_at is not None
    assert payment.webhook_last_error == "Insufficient funds"
    gateway.charge.assert_called_once_with(payment)
    webhook.send.assert_called_once()
    # update вызывается дважды: после gateway и после webhook
    assert uow.payments.update.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_payment_idempotency_webhook_already_delivered():
    """Идемпотентность - вебхук уже доставлен, повторная обработка игнорируется."""
    payment_id = uuid4()
    payment = Payment(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key="test-key-001",
        request_hash="hash-001",
        webhook_url="http://example.com/webhook",
        created_at=datetime.now(UTC),
        processed_at=datetime.now(UTC),
        webhook_delivered_at=datetime.now(UTC),  # Уже доставлен
    )

    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.payments = AsyncMock()
    uow.payments.get_for_update.return_value = payment

    gateway = AsyncMock()

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)
    await use_case(payment_id)

    # Gateway и webhook НЕ должны вызываться
    gateway.charge.assert_not_called()
    webhook.send.assert_not_called()
    # Update НЕ должен вызываться (ничего не изменилось)
    uow.payments.update.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_payment_idempotency_final_status_webhook_not_delivered():
    """Идемпотентность - финальный статус, вебхук не доставлен, отправка вебхука."""
    payment_id = uuid4()
    payment = Payment(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Test payment",
        payment_metadata={"order_id": "123"},
        status=PaymentStatus.FAILED,  # Финальный статус
        idempotency_key="test-key-001",
        request_hash="hash-001",
        webhook_url="http://example.com/webhook",
        created_at=datetime.now(UTC),
        processed_at=datetime.now(UTC),
        webhook_delivered_at=None,  # Вебхук еще не доставлен
    )

    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.payments = AsyncMock()
    uow.payments.get_for_update.return_value = payment

    gateway = AsyncMock()

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)
    await use_case(payment_id)

    # Gateway НЕ должен вызываться (статус уже финальный)
    gateway.charge.assert_not_called()
    # Webhook ДОЛЖЕН вызываться
    webhook.send.assert_called_once()
    assert payment.webhook_delivered_at is not None
    uow.payments.update.assert_called_once_with(payment)
