"""Репозиторий outbox.

Тонкий адаптер: вся работа с таблицей уже лежит в вырезанном пакете
infrastructures/outbox. Здесь только приведение к протоколу application-слоя и
передача той же сессии, что у репозитория платежей, — именно это делает вставку
события и вставку платежа одной транзакцией.

Обрати внимание, что метода «пометить опубликованным» тут нет. Он нужен только
outbox-публикатору, который живёт отдельным процессом со своей сессией и ходит
в OutboxClient напрямую, минуя UoW. UoW здесь — это граница транзакции
HTTP-запроса, и публикатору она не нужна.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, final

from payments_service.application.interfaces.repositories import (
    OutboxRepositoryProtocol,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from payments_service.infrastructures.outbox import OutboxClient


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class OutboxRepositorySQLAlchemy(OutboxRepositoryProtocol):
    session: "AsyncSession"
    client: "OutboxClient"

    async def add(
        self,
        *,
        routing_key: str,
        payload: bytes,
        exchange: str = "",
        headers: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> int:
        return await self.client.add(
            self.session,
            routing_key=routing_key,
            payload=payload,
            exchange=exchange,
            headers=headers,
            content_type=content_type,
        )
