"""Исключения слоя приложения."""

from uuid import UUID


class PaymentNotFoundError(Exception):
    """Платёж не найден."""

    def __init__(self, payment_id: UUID) -> None:
        """Инициализация исключения."""
        super().__init__(f"Payment {payment_id} not found")
        self.payment_id = payment_id


class PaymentAlreadyExistsError(Exception):
    """Платёж с таким ключом идемпотентности уже существует."""

    def __init__(self, idempotency_key: str) -> None:
        """Инициализация исключения."""
        message = f"Payment with idempotency key {idempotency_key} already exists"
        super().__init__(message)
        self.idempotency_key = idempotency_key


class IdempotencyKeyConflictError(Exception):
    """Конфликт ключа идемпотентности: тот же ключ, другое тело запроса."""

    def __init__(self, idempotency_key: str) -> None:
        """Инициализация исключения."""
        message = (
            f"Idempotency key {idempotency_key} "
            "already used with different request body"
        )
        super().__init__(message)
        self.idempotency_key = idempotency_key


class WebhookDeliveryError(Exception):
    """Техническая ошибка доставки вебхука."""

    def __init__(self, url: str, reason: str) -> None:
        """Инициализация исключения."""
        super().__init__(f"Failed to deliver webhook to {url}: {reason}")
        self.url = url
        self.reason = reason
