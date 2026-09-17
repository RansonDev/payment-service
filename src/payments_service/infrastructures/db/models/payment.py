"""Модель SQLAlchemy для платежа."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus
from payments_service.infrastructures.db.models.base import Base


class Payment(Base):
    """Модель платежа в базе данных."""

    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    amount: Mapped[Decimal] = mapped_column()
    currency: Mapped[Currency] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(String)
    payment_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    status: Mapped[PaymentStatus] = mapped_column(
        String(20), default=PaymentStatus.PENDING
    )
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    request_hash: Mapped[str] = mapped_column(String)
    webhook_url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    processed_at: Mapped[datetime | None] = mapped_column(default=None)
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(default=None)
    webhook_attempts: Mapped[int] = mapped_column(default=0)
    webhook_last_error: Mapped[str | None] = mapped_column(String, default=None)
