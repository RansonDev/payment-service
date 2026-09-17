"""Доменный value object: статус платежа."""

from enum import Enum


class PaymentStatus(str, Enum):
    """Статус платежа."""

    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
