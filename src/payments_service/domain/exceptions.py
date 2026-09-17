"""Доменные исключения."""

from uuid import UUID

from payments_service.domain.value_objects.payment_status import PaymentStatus


class DomainValidationError(Exception):
    """Базовое исключение валидации домена."""


class InvalidAmountError(DomainValidationError):
    """Некорректная сумма платежа."""

    def __init__(self, amount: float, reason: str) -> None:
        """Инициализация исключения."""
        super().__init__(f"Invalid amount {amount}: {reason}")
        self.amount = amount
        self.reason = reason


class InvalidCurrencyError(DomainValidationError):
    """Некорректная валюта."""

    def __init__(self, currency: str) -> None:
        """Инициализация исключения."""
        super().__init__(f"Invalid currency: {currency}")
        self.currency = currency


class InvalidWebhookURLError(DomainValidationError):
    """Некорректный URL вебхука."""

    def __init__(self, url: str, reason: str) -> None:
        """Инициализация исключения."""
        super().__init__(f"Invalid webhook URL {url}: {reason}")
        self.url = url
        self.reason = reason


class InvalidPaymentTransitionError(DomainValidationError):
    """Недопустимый переход статуса платежа."""

    def __init__(self, payment_id: UUID, current_status: PaymentStatus) -> None:
        """Инициализация исключения."""
        super().__init__(
            f"Cannot transition payment {payment_id} from status {current_status.value}"
        )
        self.payment_id = payment_id
        self.current_status = current_status
