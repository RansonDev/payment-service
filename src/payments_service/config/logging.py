"""Logging configuration with structlog and correlation ID support."""

import logging
import sys
from typing import Any

import structlog

from payments_service.infrastructures.context import context, install_on_handlers


def setup_logging(level: str = "INFO") -> None:
    """Настроить structlog и стандартное логирование с correlation ID.

    КРИТИЧНО: фильтр вешается на обработчики корневого логгера, а не на сам
    логгер, чтобы trace_id появлялся в логах SQLAlchemy и aio-pika.

    Args:
        level: Уровень логирования (INFO, DEBUG, и т.д.).
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.ExtraAdder(),  # Добавляет поля из LogRecord.extra
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    def extract_from_record(
        logger: Any,  # noqa: ARG001
        method_name: str,  # noqa: ARG001
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Извлечь поля из LogRecord (установленные фильтром)."""
        record = event_dict.get("_record")
        if record:
            for key in ["trace_id", "payment_id", "message_id"]:
                if hasattr(record, key):
                    event_dict[key] = getattr(record, key)
        return event_dict

    for handler in logging.root.handlers:
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
                foreign_pre_chain=[
                    extract_from_record,  # type: ignore[list-item]
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.ExtraAdder(),
                    structlog.processors.TimeStamper(fmt="iso"),
                ],
            )
        )

    install_on_handlers(
        context,
        default_context={"trace_id": "-", "payment_id": "-", "message_id": "-"},
    )
