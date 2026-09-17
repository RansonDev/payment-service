"""Протокол платёжного шлюза."""

from dataclasses import dataclass
from typing import Protocol

from payments_service.domain.entities.payment import Payment


@dataclass(frozen=True, slots=True)
class GatewayResult:
    """Результат операции платёжного шлюза."""

    success: bool
    message: str


class PaymentGatewayProtocol(Protocol):
    """Протокол взаимодействия с платёжным шлюзом."""

    async def charge(self, payment: Payment) -> GatewayResult:
        """Выполнить списание через платёжный шлюз.

        Args:
            payment: Доменная сущность платежа.

        Returns:
            Результат операции.

        Raises:
            PaymentGatewayError: При технической ошибке взаимодействия.
        """
        ...
