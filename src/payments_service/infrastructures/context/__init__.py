"""Контекст выполнения и проброс его в логи.

Код вырезан из FastStream 0.7.5 (Apache-2.0). Подробности — в README.md
и NOTICE.
"""

from .logging import ContextFilter, install_context_filter, install_on_handlers
from .repository import ContextError, ContextRepo, context

__all__ = (
    "ContextError",
    "ContextFilter",
    "ContextRepo",
    "context",
    "install_context_filter",
    "install_on_handlers",
)
