"""Таблица outbox.

Адаптировано из faststream-outbox (MIT), файл faststream_outbox/schema.py.

Что изменено по сравнению с оригиналом и почему:

  * Убрана модель аренды (acquired_token + acquired_at), CHECK-констрейнт на
    её полуустановленное состояние и два обслуживающих её частичных индекса.
    Аренда нужна там, где строка захватывается одной транзакцией, а
    обрабатывается вне её, — у них в хендлере крутится произвольная
    пользовательская логика на секунды. Наш публикатор делает ровно одну
    операцию, publish с подтверждением брокера, и её можно выполнить не
    отпуская транзакцию. Тогда работает FOR UPDATE SKIP LOCKED: воркер упал —
    транзакция оборвалась, блокировка снялась, строка видна снова в ту же
    секунду. Ни TTL подбирать, ни разгребать подвисшие строки не нужно.

  * Признак необработанности — published_at IS NULL. Отдельная enum-колонка
    статуса не заводится: у строки ровно два состояния.

  * Убрана DLQ-таблица. У outbox-строки нет терминального провала: пока брокер
    лежит, публиковать обязаны до победы, иначе теряется событие, уже
    зафиксированное в бизнес-транзакции. DLQ у нас живёт в RabbitMQ, куда её и
    требует ТЗ.

  * Убраны timer_id с его частичным уникальным индексом и проверка 63-байтового
    лимита идентификаторов Postgres — первое из их API отложенных задач,
    вторая защищала имя канала LISTEN/NOTIFY, а имя таблицы у нас фиксированное.

Что сохранено дословно:

  * payload как LargeBinary. Тело кодируется один раз на входе и кладётся в
    брокер байт в байт — пересериализации между БД и RabbitMQ не происходит.
  * next_attempt_at с server_default now(). Без этой колонки публикатор на
    следующем же тике возьмёт ту же строку снова и получится горячий цикл
    против лежащего брокера.
  * Частичный индекс, буквально повторяющий предикат выборки. Полный индекс по
    next_attempt_at рос бы вместе со всей таблицей, а нам нужен только
    неопубликованный хвост.
"""

from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    LargeBinary,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from sqlalchemy import MetaData


def make_outbox_table(metadata: "MetaData", table_name: str = "outbox") -> Table:
    """Собрать таблицу outbox и привязать её к переданной MetaData.

    Пакет не владеет схемой: таблица цепляется к MetaData приложения, чтобы её
    подхватил автогенератор Alembic, а миграцию пишет пользователь.
    """
    table = Table(
        table_name,
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        # Точка назначения в брокере. exchange пустой — default exchange.
        Column("exchange", String(255), nullable=False, server_default=""),
        Column("routing_key", String(255), nullable=False),
        # Уже закодированное тело. Публикатор отдаёт его в aio-pika как есть.
        Column("payload", LargeBinary, nullable=False),
        Column("headers", JSONB, nullable=True),
        Column("content_type", String(255), nullable=True),
        # Счётчик попыток публикации. Растёт только при неудаче: успех —
        # это одна попытка и сразу published_at.
        Column("attempts_count", BigInteger, nullable=False, server_default="0"),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        # Гейт выборки. Пока now() его не догнал, строка публикатору не видна.
        Column(
            "next_attempt_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        # Нужны стратегии повтора: max_total_delay_seconds считается как
        # last_attempt_at - first_attempt_at.
        Column("first_attempt_at", DateTime(timezone=True), nullable=True),
        Column("last_attempt_at", DateTime(timezone=True), nullable=True),
        # Единственный признак состояния. NULL — не опубликовано.
        Column("published_at", DateTime(timezone=True), nullable=True),
        Column("last_error", Text, nullable=True),
    )

    # Частичный индекс под горячий путь выборки:
    #   WHERE published_at IS NULL AND next_attempt_at <= now()
    #   ORDER BY next_attempt_at, id
    # Порядок колонок совпадает с ORDER BY, поэтому сортировка берётся из
    # индекса. Опубликованные строки в индекс не попадают вовсе, так что его
    # размер определяется длиной необработанного хвоста, а не всей таблицей.
    Index(
        f"{table_name}_pending_idx",
        table.c.next_attempt_at,
        table.c.id,
        postgresql_where=table.c.published_at.is_(None),
    )

    return table
