"""Транзакционный outbox поверх Postgres.

Код вырезан из faststream-outbox (MIT) и очищен от FastStream. Подробности —
в README.md и NOTICE.
"""

from .client import OutboxClient, OutboxEvent
from .retry import (
    ConstantRetry,
    ExponentialRetry,
    LinearRetry,
    NoRetry,
    RetryStrategyProto,
)
from .schema import make_outbox_table

__all__ = (
    "ConstantRetry",
    "ExponentialRetry",
    "LinearRetry",
    "NoRetry",
    "OutboxClient",
    "OutboxEvent",
    "RetryStrategyProto",
    "make_outbox_table",
)
