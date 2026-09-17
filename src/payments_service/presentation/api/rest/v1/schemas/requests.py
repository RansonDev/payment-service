"""Request schemas for payment API."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreatePaymentRequestSchema(BaseModel):
    """Схема запроса создания платежа."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    amount: Decimal = Field(..., description="Сумма платежа", gt=0, decimal_places=2)
    currency: str = Field(
        ..., description="Код валюты (RUB, USD, EUR)", pattern="^(RUB|USD|EUR)$"
    )
    description: str = Field(..., description="Описание платежа")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Дополнительные метаданные"
    )
    webhook_url: str = Field(..., description="URL для отправки вебхука с результатом")
