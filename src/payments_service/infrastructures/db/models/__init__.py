"""Модели SQLAlchemy."""

from payments_service.infrastructures.db.models.base import Base
from payments_service.infrastructures.db.models.payment import Payment
from payments_service.infrastructures.outbox import make_outbox_table

outbox_table = make_outbox_table(Base.metadata)

__all__ = ("Base", "Payment", "outbox_table")
