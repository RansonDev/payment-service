"""Протокол Unit of Work.

Заменяет application/interfaces/uow.py из шаблона. Единственное изменение —
вместо одного поля `repository` два именованных: `payments` и `outbox`.

Важно понимать, что этот объект НЕ обеспечивает атомарность. Атомарность даёт
общая AsyncSession, которую оба репозитория получают из REQUEST-скоупа dishka.
UnitOfWork управляет ровно одним — моментом коммита.

Отсюда правило, которое надо держать: транзакцию открывает ровно один use-case,
тот, что владеет операцией целиком. Если разнести сохранение платежа и запись
события по двум use-case'ам, каждый со своим `async with self.uow`, получится два
коммита и окно, в котором платёж зафиксирован, а событие ещё нет. Это ровно тот
отказ, ради которого outbox и существует.

Объект не реентерабелен: вложенный `async with` по тому же инстансу закоммитит
раньше времени, потому что из REQUEST-скоупа приходит один и тот же UoW.
"""

from abc import abstractmethod
from types import TracebackType
from typing import Protocol

from payments_service.application.interfaces.repositories import (
    OutboxRepositoryProtocol,
    PaymentRepositoryProtocol,
)


class UnitOfWorkProtocol(Protocol):
    payments: PaymentRepositoryProtocol
    outbox: OutboxRepositoryProtocol

    @abstractmethod
    async def __aenter__(self) -> "UnitOfWorkProtocol": ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
