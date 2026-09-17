"""Подмешивание контекста в записи логов.

Зачем это нужно. Без фильтра сквозной идентификатор приходится передавать
в каждый вызов логгера через extra=, и достаточно забыть в одном месте, чтобы
цепочка порвалась. Хуже того, логи, которые пишут SQLAlchemy, aio-pika и
uvicorn, про твой extra не знают вообще.

Фильтр снимает обе проблемы: контекст открывается один раз на обработку
сообщения, и дальше все записи, включая чужие, получают нужные поля.
Приоритет у явного extra: если вызов передал trace_id сам, значение
из контекста его не перезапишет.
"""

from collections.abc import Mapping
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .repository import ContextRepo


class ContextFilter(logging.Filter):
    """Переносит значения из log_context в атрибуты LogRecord."""

    def __init__(
        self,
        context: "ContextRepo",
        default_context: Mapping[str, Any] | None = None,
        name: str = "",
    ) -> None:
        """Создать фильтр.

        :param context: хранилище контекста.
        :param default_context: значения-заглушки для ключей, которые ожидает
            строка формата. Без них запись, сделанная вне открытого scope,
            уронит форматирование.
        """
        self.context = context
        self.default_context = dict(default_context or {})
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        if not super().filter(record):
            return False

        log_context: Mapping[str, Any] = self.context.get_local("log_context", {})

        for key, fallback in {**self.default_context, **log_context}.items():
            # getattr, а не прямое присваивание: явный extra= в вызове
            # логгера имеет приоритет над контекстом
            setattr(record, key, getattr(record, key, fallback))

        return True


def install_context_filter(
    logger: logging.Logger,
    context: "ContextRepo",
    default_context: Mapping[str, Any] | None = None,
) -> ContextFilter:
    """Повесить фильтр на логгер.

    Важно, куда вешать. Фильтры логгера применяются только к записям, которые
    сделаны через него самого, и НЕ применяются к записям дочерних логгеров,
    всплывающим по иерархии. Поэтому чтобы контекст попал и в логи SQLAlchemy
    с aio-pika, фильтр вешается на обработчик корневого логгера, а не на сам
    корневой логгер:

        root = logging.getLogger()
        for handler in root.handlers:
            handler.addFilter(ContextFilter(context, defaults))
    """
    log_filter = ContextFilter(context, default_context)
    logger.addFilter(log_filter)
    return log_filter


def install_on_handlers(
    context: "ContextRepo",
    default_context: Mapping[str, Any] | None = None,
    logger: logging.Logger | None = None,
) -> ContextFilter:
    """Повесить фильтр на все обработчики логгера, по умолчанию корневого.

    Рабочий вариант для приложения: ловит записи любых библиотек.
    Вызывать после настройки логирования, когда обработчики уже созданы.
    """
    target = logger or logging.getLogger()
    log_filter = ContextFilter(context, default_context)
    for handler in target.handlers:
        handler.addFilter(log_filter)
    return log_filter
