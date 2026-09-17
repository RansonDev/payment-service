"""FastAPI middlewares."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from payments_service.infrastructures.context import context


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Middleware для генерации и проброса correlation ID (trace_id).

    Читает входящий заголовок X-Request-ID если он есть, иначе генерирует новый.
    Открывает контекст с trace_id для всех логов в рамках запроса.
    Возвращает X-Request-ID в заголовках ответа.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Any:
        """Обработать запрос с trace_id в контексте.

        Args:
            request: Входящий HTTP-запрос.
            call_next: Следующий обработчик в цепочке.

        Returns:
            HTTP-ответ с заголовком X-Request-ID.
        """
        trace_id = request.headers.get("X-Request-ID") or str(uuid4())

        with context.bind(trace_id=trace_id):
            response = await call_next(request)

        response.headers["X-Request-ID"] = trace_id
        return response
