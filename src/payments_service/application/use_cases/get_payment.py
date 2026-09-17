"""Use-case получения платежа."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, final
from uuid import UUID

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.application.exceptions import PaymentNotFoundError

if TYPE_CHECKING:
    from payments_service.application.interfaces.mappers import (
        DtoEntityMapperProtocol,
    )
    from payments_service.application.interfaces.uow import UnitOfWorkProtocol


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class GetPaymentUseCase:
    """Use-case получения информации о платеже."""

    uow: "UnitOfWorkProtocol"
    mapper: "DtoEntityMapperProtocol"

    async def __call__(self, payment_id: UUID) -> PaymentDTO:
        """Получить платёж по ID.

        Args:
            payment_id: UUID платежа.

        Returns:
            PaymentDTO с информацией о платеже.

        Raises:
            PaymentNotFoundError: Платёж не найден.
        """
        async with self.uow:
            payment = await self.uow.payments.get_by_id(payment_id)

        if payment is None:
            raise PaymentNotFoundError(payment_id)

        return self.mapper.to_dto(payment)
