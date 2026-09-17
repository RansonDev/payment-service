"""Доменная сущность: платёж."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from payments_service.domain.exceptions import (
    InvalidAmountError,
    InvalidPaymentTransitionError,
    InvalidWebhookURLError,
)
from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus


@dataclass(slots=True, kw_only=True)
class Payment:
    """Доменная сущность платежа.

    Mutable dataclass с методами перехода состояний.
    Инварианты проверяются в __post_init__.
    """

    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    payment_metadata: dict[str, Any] = field(default_factory=dict)
    status: PaymentStatus = PaymentStatus.PENDING
    idempotency_key: str
    request_hash: str
    webhook_url: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None
    webhook_delivered_at: datetime | None = None
    webhook_attempts: int = 0
    webhook_last_error: str | None = None

    def __post_init__(self) -> None:
        """Проверка инвариантов домена."""
        if self.amount <= 0:
            raise InvalidAmountError(
                float(self.amount), "Amount must be greater than zero"
            )

        if self.amount.as_tuple().exponent < -2:  # type: ignore[operator]
            raise InvalidAmountError(
                float(self.amount), "Amount must have at most 2 decimal places"
            )

        if not self.webhook_url.startswith(("http://", "https://")):
            raise InvalidWebhookURLError(
                self.webhook_url, "URL must use http or https scheme"
            )

    def mark_succeeded(self) -> None:
        """Отметить платёж как успешный.

        Raises:
            InvalidPaymentTransitionError: Если платёж уже не в статусе PENDING.
        """
        if self.status is not PaymentStatus.PENDING:
            raise InvalidPaymentTransitionError(self.id, self.status)
        self.status = PaymentStatus.SUCCEEDED
        self.processed_at = datetime.now(UTC)

    def mark_failed(self, reason: str) -> None:
        """Отметить платёж как неуспешный.

        Args:
            reason: Причина неуспеха.

        Raises:
            InvalidPaymentTransitionError: Если платёж уже не в статусе PENDING.
        """
        if self.status is not PaymentStatus.PENDING:
            raise InvalidPaymentTransitionError(self.id, self.status)
        self.status = PaymentStatus.FAILED
        self.processed_at = datetime.now(UTC)
        self.webhook_last_error = reason

    def mark_webhook_delivered(self) -> None:
        """Отметить вебхук как доставленный."""
        self.webhook_delivered_at = datetime.now(UTC)

    def register_webhook_failure(self, error: str) -> None:
        """Зарегистрировать неудачную попытку доставки вебхука.

        Args:
            error: Описание ошибки доставки.
        """
        self.webhook_attempts += 1
        self.webhook_last_error = error
