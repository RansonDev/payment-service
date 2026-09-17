"""Контекст выполнения на contextvars.

Ради чего берётся, а не пишется на голых contextvars:

  * scope() гарантирует reset в finally. Без него исключение в обработчике
    оставляет токен невосстановленным, и значение протекает на следующее
    сообщение, обработанное в том же таске. Это ровно тот баг, при котором
    в логах платежа A виден trace_id платежа B;
  * ContextVar создаётся лениво, по первому обращению к ключу — регистрировать
    переменные заранее не нужно;
  * два уровня, глобальный на процесс и локальный на задачу, с единым get().

Про asyncio: каждая задача получает копию контекста в момент создания,
поэтому scope, открытый в одной задаче, не виден соседним. Это свойство
contextvars, и оно нам нужно — параллельные доставки не путают свои значения.
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, TypeVar

T = TypeVar("T")

_NOT_SET: Any = object()


class ContextError(KeyError):
    """Запрошенного ключа нет ни в глобальном, ни в локальном контексте."""

    def __init__(self, context: Mapping[str, Any], field: str) -> None:
        self.context = context
        self.field = field
        super().__init__(field)

    def __str__(self) -> str:
        return f"`{self.field}` not found in context: {list(self.context.keys())}"


class ContextRepo:
    """Хранилище контекста выполнения."""

    __slots__ = ("_global_context", "_scope_context")

    def __init__(self, initial: dict[str, Any] | None = None, /) -> None:
        self._global_context: dict[str, Any] = dict(initial or {})
        self._scope_context: dict[str, ContextVar[Any]] = {}

    @property
    def context(self) -> dict[str, Any]:
        """Полный текущий контекст: глобальный, перекрытый локальным."""
        local = {}
        for key, var in self._scope_context.items():
            value = var.get()
            if value is not _NOT_SET:
                local[key] = value
        return {**self._global_context, **local}

    # --- глобальный уровень (на процесс) ---

    def set_global(self, key: str, value: Any) -> None:
        self._global_context[key] = value

    def reset_global(self, key: str) -> None:
        self._global_context.pop(key, None)

    # --- локальный уровень (на задачу) ---

    def set_local(self, key: str, value: T) -> "Token[T]":
        context_var = self._scope_context.get(key)
        if context_var is None:
            context_var = ContextVar(key, default=_NOT_SET)
            self._scope_context[key] = context_var
        return context_var.set(value)

    def reset_local(self, key: str, token: "Token[Any]") -> None:
        self._scope_context[key].reset(token)

    def get_local(self, key: str, default: Any = None) -> Any:
        if (context_var := self._scope_context.get(key)) is None:
            return default
        if (value := context_var.get()) is _NOT_SET:
            return default
        return value

    # --- доступ ---

    def get(self, key: str, default: Any = None) -> Any:
        """Значение по ключу: сначала локальный уровень, затем глобальный."""
        local = self.get_local(key, _NOT_SET)
        if local is not _NOT_SET:
            return local
        return self._global_context.get(key, default)

    def require(self, key: str) -> Any:
        """То же, но с исключением вместо значения по умолчанию."""
        value = self.get(key, _NOT_SET)
        if value is _NOT_SET:
            raise ContextError(self.context, key)
        return value

    # --- управление областью видимости ---

    @contextmanager
    def scope(self, key: str, value: Any) -> Generator[None, None, None]:
        """Выставить значение на время блока и вернуть прежнее на выходе.

        Сброс в finally: при исключении в теле токен всё равно восстановится.
        """
        token = self.set_local(key, value)
        try:
            yield
        finally:
            self.reset_local(key, token)

    @contextmanager
    def bind(self, **values: Any) -> Generator[None, None, None]:
        """Добавить значения в log_context, сохранив уже выставленные.

        Именно этим отличается от scope(): вложенный вызов дополняет контекст,
        а не затирает его. Нужно, чтобы trace_id с HTTP-слоя дожил до места,
        где добавляется payment_id.

            with context.bind(trace_id=tid):
                with context.bind(payment_id=pid):
                    ...  # в логах видны оба
        """
        current: dict[str, Any] = self.get_local("log_context", {})
        with self.scope("log_context", {**current, **values}):
            yield

    def clear(self) -> None:
        self._global_context.clear()
        self._scope_context.clear()


context = ContextRepo()
"""Экземпляр на процесс. Отдельный контекст на каждый воркер не нужен:
изоляцию между сообщениями обеспечивают contextvars, а не разные объекты."""
