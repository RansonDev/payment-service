"""Тесты доменной сущности Payment."""

from decimal import Decimal
from uuid import uuid4

import pytest

from payments_service.domain.entities.payment import Payment
from payments_service.domain.exceptions import (
    InvalidAmountError,
    InvalidPaymentTransitionError,
    InvalidWebhookURLError,
)
from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus


class TestPaymentInvariants:
    """Тесты инвариантов домена."""

    @pytest.mark.unit
    def test_amount_must_be_positive(self) -> None:
        """Сумма платежа должна быть больше нуля."""
        with pytest.raises(InvalidAmountError) as exc_info:
            Payment(
                id=uuid4(),
                amount=Decimal("0"),
                currency=Currency.RUB,
                description="Test",
                idempotency_key="test-key",
                request_hash="hash",
                webhook_url="https://example.com/webhook",
            )
        assert "must be greater than zero" in str(exc_info.value)

    @pytest.mark.unit
    def test_amount_negative_fails(self) -> None:
        """Отрицательная сумма недопустима."""
        with pytest.raises(InvalidAmountError) as exc_info:
            Payment(
                id=uuid4(),
                amount=Decimal("-100"),
                currency=Currency.USD,
                description="Test",
                idempotency_key="test-key",
                request_hash="hash",
                webhook_url="https://example.com/webhook",
            )
        assert "must be greater than zero" in str(exc_info.value)

    @pytest.mark.unit
    def test_amount_max_two_decimal_places(self) -> None:
        """Сумма не должна иметь больше двух знаков после запятой."""
        with pytest.raises(InvalidAmountError) as exc_info:
            Payment(
                id=uuid4(),
                amount=Decimal("100.123"),
                currency=Currency.EUR,
                description="Test",
                idempotency_key="test-key",
                request_hash="hash",
                webhook_url="https://example.com/webhook",
            )
        assert "at most 2 decimal places" in str(exc_info.value)

    @pytest.mark.unit
    def test_amount_two_decimal_places_allowed(self) -> None:
        """Два знака после запятой допустимы."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100.99"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        assert payment.amount == Decimal("100.99")

    @pytest.mark.unit
    def test_webhook_url_must_be_http_or_https(self) -> None:
        """Webhook URL должен использовать http или https схему."""
        with pytest.raises(InvalidWebhookURLError) as exc_info:
            Payment(
                id=uuid4(),
                amount=Decimal("100"),
                currency=Currency.RUB,
                description="Test",
                idempotency_key="test-key",
                request_hash="hash",
                webhook_url="ftp://example.com/webhook",
            )
        assert "must use http or https scheme" in str(exc_info.value)

    @pytest.mark.unit
    def test_webhook_url_http_allowed(self) -> None:
        """HTTP URL допустим."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="http://example.com/webhook",
        )
        assert payment.webhook_url == "http://example.com/webhook"

    @pytest.mark.unit
    def test_webhook_url_https_allowed(self) -> None:
        """HTTPS URL допустим."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        assert payment.webhook_url == "https://example.com/webhook"


class TestPaymentTransitions:
    """Тесты переходов состояний."""

    @pytest.mark.unit
    def test_mark_succeeded_from_pending(self) -> None:
        """Переход из PENDING в SUCCEEDED допустим."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        assert payment.status == PaymentStatus.PENDING
        assert payment.processed_at is None

        payment.mark_succeeded()

        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.processed_at is not None

    @pytest.mark.unit
    def test_mark_failed_from_pending(self) -> None:
        """Переход из PENDING в FAILED допустим."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        assert payment.status == PaymentStatus.PENDING

        payment.mark_failed("Gateway timeout")

        assert payment.status == PaymentStatus.FAILED
        assert payment.processed_at is not None
        assert payment.webhook_last_error == "Gateway timeout"

    @pytest.mark.unit
    def test_cannot_mark_succeeded_twice(self) -> None:
        """Повторный переход в SUCCEEDED запрещён."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        payment.mark_succeeded()

        with pytest.raises(InvalidPaymentTransitionError) as exc_info:
            payment.mark_succeeded()

        assert str(payment.id) in str(exc_info.value)
        assert PaymentStatus.SUCCEEDED.value in str(exc_info.value)

    @pytest.mark.unit
    def test_cannot_mark_failed_after_succeeded(self) -> None:
        """Переход из SUCCEEDED в FAILED запрещён."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        payment.mark_succeeded()

        with pytest.raises(InvalidPaymentTransitionError):
            payment.mark_failed("Too late")

    @pytest.mark.unit
    def test_cannot_mark_succeeded_after_failed(self) -> None:
        """Переход из FAILED в SUCCEEDED запрещён."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        payment.mark_failed("Gateway error")

        with pytest.raises(InvalidPaymentTransitionError):
            payment.mark_succeeded()

    @pytest.mark.unit
    def test_mark_webhook_delivered(self) -> None:
        """Отметка вебхука как доставленного."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        assert payment.webhook_delivered_at is None

        payment.mark_webhook_delivered()

        assert payment.webhook_delivered_at is not None

    @pytest.mark.unit
    def test_register_webhook_failure(self) -> None:
        """Регистрация неудачной попытки доставки вебхука."""
        payment = Payment(
            id=uuid4(),
            amount=Decimal("100"),
            currency=Currency.RUB,
            description="Test",
            idempotency_key="test-key",
            request_hash="hash",
            webhook_url="https://example.com/webhook",
        )
        assert payment.webhook_attempts == 0
        assert payment.webhook_last_error is None

        payment.register_webhook_failure("Connection timeout")

        assert payment.webhook_attempts == 1
        assert payment.webhook_last_error == "Connection timeout"

        payment.register_webhook_failure("Service unavailable")

        assert payment.webhook_attempts == 2
        assert payment.webhook_last_error == "Service unavailable"
