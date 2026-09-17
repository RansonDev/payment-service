"""DTO слоя приложения для платежей."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentDTO:
    """DTO платежа для передачи между слоями."""

    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    payment_metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    request_hash: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None
    webhook_delivered_at: datetime | None
    webhook_attempts: int
    webhook_last_error: str | None
