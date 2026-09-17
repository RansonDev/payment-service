"""Реализация Unit of Work на SQLAlchemy.

Заменяет infrastructures/db/uow.py из шаблона. Логика __aexit__ сохранена как в
оригинале: коммит при чистом выходе, откат при исключении, исключение
пробрасывается дальше (не подавляется).

После отката сессия снова пригодна к работе — на этом построена обработка гонки
по idempotency_key в CreatePaymentUseCase: первый блок падает, __aexit__ делает
rollback, второй блок открывает новую транзакцию и перечитывает платёж.

Файл infrastructures/db/uow_new.py из шаблона — дубль, его нужно удалить.
"""

from dataclasses import dataclass
import logging
from types import TracebackType
from typing import final

from sqlalchemy.ext.asyncio import AsyncSession

from payments_service.application.interfaces.repositories import (
    OutboxRepositoryProtocol,
    PaymentRepositoryProtocol,
)
from payments_service.application.interfaces.uow import UnitOfWorkProtocol

logger = logging.getLogger(__name__)


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class UnitOfWorkSQLAlchemy(UnitOfWorkProtocol):
    """Координирует транзакцию и даёт доступ к репозиториям.

    Все три поля ссылаются на одну сессию: repositories получают её тем же
    провайдером dishka, что и сам UoW.
    """

    session: AsyncSession
    payments: PaymentRepositoryProtocol
    outbox: OutboxRepositoryProtocol

    async def __aenter__(self) -> "UnitOfWorkSQLAlchemy":
        logger.debug("Starting database transaction")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            logger.warning(
                "Transaction rolled back due to exception: %s - %s",
                exc_type.__name__,
                exc_val,
            )
            await self.rollback()
        else:
            await self.commit()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
