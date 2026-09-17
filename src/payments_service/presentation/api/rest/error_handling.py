"""Exception handlers for FastAPI application."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from payments_service.application.exceptions import (
    IdempotencyKeyConflictError,
    PaymentNotFoundError,
)
from payments_service.domain.exceptions import DomainValidationError


def setup_exception_handlers(app: FastAPI) -> None:
    """Зарегистрировать обработчики исключений в FastAPI приложении.

    Args:
        app: FastAPI приложение.
    """

    @app.exception_handler(PaymentNotFoundError)
    async def payment_not_found_exception_handler(
        _request: Request,
        exc: PaymentNotFoundError,
    ) -> JSONResponse:
        """Обработчик PaymentNotFoundError → 404."""
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": str(exc)},
        )

    @app.exception_handler(IdempotencyKeyConflictError)
    async def idempotency_key_conflict_exception_handler(
        _request: Request,
        exc: IdempotencyKeyConflictError,
    ) -> JSONResponse:
        """Обработчик IdempotencyKeyConflictError → 409."""
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": str(exc)},
        )

    @app.exception_handler(DomainValidationError)
    async def domain_validation_error_handler(
        _request: Request,
        exc: DomainValidationError,
    ) -> JSONResponse:
        """Обработчик DomainValidationError → 422."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"message": str(exc)},
        )
