"""Доменный value object: валюта платежа."""

from enum import Enum


class Currency(str, Enum):
    """Валюта платежа."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
