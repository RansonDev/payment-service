"""Response schemas for payment API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreatePaymentResponseSchema(BaseModel):
    """Схема ответа создания платежа (202 Accepted)."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    payment_id: UUID = Field(..., description="Идентификатор платежа")
    status: str = Field(..., description="Статус платежа")
    created_at: datetime = Field(..., description="Время создания платежа (UTC)")


class PaymentResponseSchema(BaseModel):
    """Полная схема ответа информации о платеже."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        from_attributes=True,
    )

    id: UUID = Field(..., description="Идентификатор платежа")
    amount: str = Field(..., description="Сумма платежа")
    currency: str = Field(..., description="Код валюты")
    status: str = Field(..., description="Статус платежа")
    description: str = Field(..., description="Описание платежа")
    payment_metadata: dict[str, Any] = Field(
        ..., description="Дополнительные метаданные"
    )
    idempotency_key: str = Field(..., description="Ключ идемпотентности")
    webhook_url: str = Field(..., description="URL вебхука")
    created_at: datetime = Field(..., description="Время создания платежа (UTC)")
    processed_at: datetime | None = Field(
        None, description="Время обработки платежа (UTC)"
    )
    webhook_delivered_at: datetime | None = Field(
        None, description="Время доставки вебхука (UTC)"
    )
    webhook_attempts: int = Field(
        ..., description="Количество попыток доставки вебхука"
    )
    webhook_last_error: str | None = Field(
        None, description="Последняя ошибка доставки вебхука"
    )


class HealthResponseSchema(BaseModel):
    """Схема ответа health-check."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: str = Field(..., description="Статус сервиса")
