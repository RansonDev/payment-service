"""Create payments and outbox tables

Revision ID: e38c5b05cf60
Revises:
Create Date: 2026-09-13 19:35:14.190844

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "e38c5b05cf60"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создание таблиц payments и outbox."""
    # Таблица payments
    op.create_table(
        "payments",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="PENDING"
        ),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("webhook_url", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("webhook_last_error", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
    )
    op.create_index(
        "ix_payments_idempotency_key", "payments", ["idempotency_key"], unique=True
    )

    # Таблица outbox
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("exchange", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("routing_key", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("headers", JSONB, nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column(
            "attempts_count", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "outbox_pending_idx",
        "outbox",
        ["next_attempt_at", "id"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    """Удаление таблиц outbox и payments."""
    op.drop_index("outbox_pending_idx", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("ix_payments_idempotency_key", table_name="payments")
    op.drop_table("payments")
