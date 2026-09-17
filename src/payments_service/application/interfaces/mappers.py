"""Протоколы маперов слоя приложения."""

from abc import abstractmethod
from typing import Protocol

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.domain.entities.payment import Payment


class DtoEntityMapperProtocol(Protocol):
    """Протокол маппера между доменной сущностью и DTO приложения."""

    @abstractmethod
    def to_dto(self, entity: Payment) -> PaymentDTO:
        """Конвертация доменной сущности в DTO."""
        ...

    @abstractmethod
    def to_entity(self, dto: PaymentDTO) -> Payment:
        """Конвертация DTO в доменную сущность."""
        ...
