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
    uow.payments.get_by_id.return_value = payment

    gateway = AsyncMock()
    gateway.charge.return_value = GatewayResult(
        success=True, message="Payment approved"
    )

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)

    # Мокаем методы репозитория
    uow.payments.get_by_id = AsyncMock(return_value=payment)
    uow.payments.try_mark_processed = AsyncMock(return_value=True)
    uow.payments.try_mark_webhook_delivered = AsyncMock(return_value=True)

    await use_case(payment_id)

    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None
    assert payment.webhook_delivered_at is not None
    gateway.charge.assert_called_once_with(payment)
    webhook.send.assert_called_once()
    uow.payments.try_mark_processed.assert_called_once()
    uow.payments.try_mark_webhook_delivered.assert_called_once()


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
    uow.payments.get_by_id.return_value = payment

    gateway = AsyncMock()
    gateway.charge.return_value = GatewayResult(
        success=False, message="Insufficient funds"
    )

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)

    # Мокаем методы репозитория
    uow.payments.get_by_id = AsyncMock(return_value=payment)
    uow.payments.try_mark_processed = AsyncMock(return_value=True)
    uow.payments.try_mark_webhook_delivered = AsyncMock(return_value=True)

    await use_case(payment_id)

    assert payment.status == PaymentStatus.FAILED
    assert payment.processed_at is not None
    assert payment.webhook_delivered_at is not None
    gateway.charge.assert_called_once_with(payment)
    webhook.send.assert_called_once()
    uow.payments.try_mark_processed.assert_called_once()
    uow.payments.try_mark_webhook_delivered.assert_called_once()


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
    uow.payments.get_by_id.return_value = payment

    gateway = AsyncMock()

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)

    # Мокаем методы репозитория
    uow.payments.get_by_id = AsyncMock(return_value=payment)

    await use_case(payment_id)

    # Gateway и webhook НЕ должны вызываться
    gateway.charge.assert_not_called()
    webhook.send.assert_not_called()


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
    uow.payments.get_by_id.return_value = payment

    gateway = AsyncMock()

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)

    # Мокаем методы репозитория
    uow.payments.get_by_id = AsyncMock(return_value=payment)
    uow.payments.try_mark_webhook_delivered = AsyncMock(return_value=True)

    await use_case(payment_id)

    # Gateway НЕ должен вызываться (статус уже финальный)
    gateway.charge.assert_not_called()
    # Webhook ДОЛЖЕН вызываться
    webhook.send.assert_called_once()
    assert payment.webhook_delivered_at is not None
    uow.payments.try_mark_webhook_delivered.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_payment_race_condition_gateway_called_twice():
    """Гонка: два процесса вызывают шлюз, выигрывает только первый."""
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

    gateway = AsyncMock()
    gateway.charge.return_value = GatewayResult(success=True, message="Approved")

    webhook = AsyncMock()

    use_case = ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)

    # Имитируем ситуацию:
    # 1. Оба читают статус PENDING
    # 2. Оба вызывают gateway.charge()
    # 3. Первый вызывает try_mark_processed -> True
    # 4. Второй вызывает try_mark_processed -> False

    # Состояние для первого вызова
    uow.payments.get_by_id.side_effect = [payment, payment, payment]
    uow.payments.try_mark_processed.side_effect = [True]
    uow.payments.try_mark_webhook_delivered.side_effect = [True]

    await use_case(payment_id)

    assert gateway.charge.call_count == 1
    assert uow.payments.try_mark_processed.call_count == 1
    assert webhook.send.call_count == 1

    # Сбрасываем моки для второго "процесса"
    gateway.charge.reset_mock()
    webhook.send.reset_mock()
    uow.payments.try_mark_processed.reset_mock()
    uow.payments.try_mark_webhook_delivered.reset_mock()
    uow.payments.get_by_id.reset_mock()

    # Состояние для второго вызова (гонка)
    # Платёж всё ещё выглядит как PENDING при первом чтении
    payment_pending = Payment(
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
    # Но после неудачи try_mark_processed он перечитывается как SUCCEEDED
    payment_succeeded = Payment(
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
    )

    uow.payments.get_by_id.side_effect = [
        payment_pending,
        payment_succeeded,
        payment_succeeded,
    ]
    uow.payments.try_mark_processed.side_effect = [False]  # Второй проиграл гонку
    uow.payments.try_mark_webhook_delivered.side_effect = [
        False
    ]  # Вебхук уже доставлен первым

    await use_case(payment_id)

    # Шлюз ВЫЗЫВАЕТСЯ (так как мы не можем предотвратить это в распределенной системе без блокировок)
    assert gateway.charge.call_count == 1
    # try_mark_processed вызывается и возвращает False
    assert uow.payments.try_mark_processed.call_count == 1
    # Вебхук вызывается повторно (это нормально, он идемпотентен на стороне получателя)
    assert webhook.send.call_count == 1
    # try_mark_webhook_delivered вызывается и возвращает False
    assert uow.payments.try_mark_webhook_delivered.call_count == 1
