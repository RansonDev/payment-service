"""Доступ к таблице outbox.

Адаптировано из faststream-outbox (MIT), файл faststream_outbox/client.py.

Что изменено:

  * Работа идёт через AsyncSession, а не AsyncConnection — так вставка события
    попадает в ту же сессию и ту же транзакцию, что и запись платежа, ради чего
    outbox и существует.
  * Захват строк — FOR UPDATE SKIP LOCKED в транзакции вызывающего, вместо
    CTE с проставлением аренды. Подробности выбора — в schema.py.
  * Терминальный провал и CTE-архивация в DLQ выброшены: у outbox-строки нет
    терминального состояния.
  * Выброшены валидация схемы по pg_catalog, отмена отложенных задач по
    timer_id и батчевые операции.

Что сохранено дословно:

  * SKIP LOCKED. Без него вторая реплика публикатора вставала бы в очередь за
    блокировками первой вместо того, чтобы забирать соседние строки.
  * next_attempt_at считается выражением `now() + make_interval(secs => :delay)`
    на стороне сервера, а не питоновским datetime. Расхождение часов между
    воркером и БД перестаёт влиять на тайминг повторов.
  * Порядок ORDER BY next_attempt_at, id — совпадает с частичным индексом.
"""

from dataclasses import dataclass
import datetime as dt
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, Table, bindparam, func, insert, select, update

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """Строка outbox, готовая к публикации."""

    id: int
    exchange: str
    routing_key: str
    payload: bytes
    headers: dict[str, Any] | None
    content_type: str | None
    attempts_count: int
    created_at: dt.datetime
    first_attempt_at: dt.datetime | None
    last_attempt_at: dt.datetime | None

    @property
    def message_id(self) -> str:
        """Идентификатор сообщения в AMQP.

        Совпадает с первичным ключом строки, поэтому повторная публикация после
        падения между publish и commit придёт к консьюмеру с тем же message_id.
        """
        return str(self.id)


class OutboxClient:
    """Все обращения к таблице outbox.

    Транзакциями управляет вызывающий: и API-хендлер, которому нужна одна
    транзакция на платёж вместе с событием, и публикатор, которому нужно
    удерживать блокировку строк до подтверждения от брокера.
    """

    __slots__ = ("_table",)

    def __init__(self, table: Table) -> None:
        self._table = table

    @property
    def table(self) -> Table:
        return self._table

    async def add(
        self,
        session: "AsyncSession",
        *,
        routing_key: str,
        payload: bytes,
        exchange: str = "",
        headers: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> int:
        """Положить событие в outbox в транзакции вызывающего.

        Вызывается из того же use-case, что создаёт платёж, и до коммита. Если
        транзакция откатится, события не останется — в этом весь смысл паттерна.
        """
        stmt = (
            insert(self._table)
            .values(
                exchange=exchange,
                routing_key=routing_key,
                payload=payload,
                headers=headers,
                content_type=content_type,
            )
            .returning(self._table.c.id)
        )
        result = await session.execute(stmt)
        return int(result.scalar_one())

    async def fetch_pending(
        self,
        session: "AsyncSession",
        *,
        limit: int,
    ) -> list[OutboxEvent]:
        """Захватить до limit готовых строк.

        ВЫЗЫВАТЬ ТОЛЬКО ВНУТРИ ОТКРЫТОЙ ТРАНЗАКЦИИ. Блокировки живут до её
        завершения — именно они защищают строки от второй реплики публикатора,
        и именно их обрыв при падении воркера возвращает строки в оборот.

        Строка готова, если она не опубликована и её гейт наступил. Никакого
        отдельного состояния «в обработке» нет: строка либо свободна, либо
        заблокирована чьей-то живой транзакцией.
        """
        t = self._table
        stmt = (
            select(t)
            .where(
                t.c.published_at.is_(None),
                t.c.next_attempt_at <= func.now(),
            )
            .order_by(t.c.next_attempt_at, t.c.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return [
            OutboxEvent(
                id=row.id,
                exchange=row.exchange,
                routing_key=row.routing_key,
                payload=row.payload,
                headers=row.headers,
                content_type=row.content_type,
                attempts_count=row.attempts_count,
                created_at=row.created_at,
                first_attempt_at=row.first_attempt_at,
                last_attempt_at=row.last_attempt_at,
            )
            for row in result.mappings().all()
        ]

    async def mark_published(
        self,
        session: "AsyncSession",
        event_ids: "Sequence[int]",
    ) -> int:
        """Отметить строки опубликованными.

        Вызывается только после подтверждения от брокера. Порядок «сначала
        publish, потом отметка» даёт at-least-once: падение между ними приводит
        к повторной публикации того же message_id, и это осознанный выбор —
        дубликат гасит идемпотентный консьюмер, а потеря события невосполнима.
        """
        if not event_ids:
            return 0

        t = self._table
        stmt = (
            update(t)
            .where(t.c.id.in_(event_ids), t.c.published_at.is_(None))
            .values(published_at=func.now(), last_error=None)
        )
        result = await session.execute(stmt)
        return result.rowcount or 0  # type: ignore[attr-defined]

    async def reschedule(
        self,
        session: "AsyncSession",
        event_id: int,
        *,
        delay_seconds: float,
        attempts_count: int,
        first_attempt_at: dt.datetime,
        last_attempt_at: dt.datetime,
        error: str | None = None,
    ) -> bool:
        """Отложить следующую попытку публикации.

        Момент next_attempt_at вычисляет сервер БД: `now()` плюс интервал из
        delay_seconds. Часы воркера в расчёте не участвуют.

        delay_seconds берётся у стратегии из retry.py, а first_attempt_at и
        last_attempt_at она же требует на вход для max_total_delay_seconds.
        """
        t = self._table
        next_attempt_at = func.now() + func.make_interval(
            0,
            0,
            0,
            0,
            0,
            0,
            bindparam("delay", type_=Float),
        )
        stmt = (
            update(t)
            .where(t.c.id == event_id, t.c.published_at.is_(None))
            .values(
                next_attempt_at=next_attempt_at,
                attempts_count=attempts_count,
                first_attempt_at=first_attempt_at,
                last_attempt_at=last_attempt_at,
                last_error=error,
            )
        )
        result = await session.execute(stmt, {"delay": max(0.0, delay_seconds)})
        return (result.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def count_pending(self, session: "AsyncSession") -> int:
        """Размер необработанного хвоста. Полезно для health-эндпоинта."""
        t = self._table
        stmt = select(func.count()).select_from(t).where(t.c.published_at.is_(None))
        result = await session.execute(stmt)
        return int(result.scalar_one())
