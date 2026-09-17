"""Эмулятор платёжного шлюза."""

import asyncio
from dataclasses import dataclass
import random
from typing import TYPE_CHECKING, final

from payments_service.application.interfaces.gateway import (
    GatewayResult,
    PaymentGatewayProtocol,
)

if TYPE_CHECKING:
    from payments_service.domain.entities.payment import Payment


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class FakePaymentGateway(PaymentGatewayProtocol):
    """Эмулятор платёжного шлюза с настраиваемыми параметрами.

    Параметры эмуляции берутся из конфигурации, чтобы можно было:
    - Поставить success_rate=0.0 и сразу увидеть ветку неуспеха
    - Поставить min_delay=0.1 для быстрых тестов
    - Поставить success_rate=1.0 для отладки успешного пути
    """

    success_rate: float
    min_delay_seconds: float
    max_delay_seconds: float

    async def charge(self, payment: "Payment") -> GatewayResult:
        """Эмулировать списание через платёжный шлюз.

        Args:
            payment: Доменная сущность платежа.

        Returns:
            GatewayResult с результатом операции.
        """
        delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)  # noqa: S311
        await asyncio.sleep(delay)

        success = random.random() < self.success_rate  # noqa: S311

        if success:
            return GatewayResult(
                success=True,
                message=f"Payment {payment.id} charged successfully",
            )

        return GatewayResult(
            success=False,
            message=f"Payment {payment.id} declined by gateway",
        )
