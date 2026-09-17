from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from payments_service.config.ioc.di import get_providers
from payments_service.config.logging import setup_logging
from payments_service.presentation.api.rest.error_handling import (
    setup_exception_handlers,
)
from payments_service.presentation.api.rest.middlewares import TraceIDMiddleware
from payments_service.presentation.api.rest.v1.routers import api_v1_router

setup_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Asynchronous context manager for managing the lifespan of the FastAPI application.

    Args:
        _: The FastAPI application instance.

    Yields:
        None
    """
    logger.info("Starting application...")
    yield
    logger.info("Shutting down application...")


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application.

    Returns:
        FastAPI: The configured FastAPI application instance.
    """
    app = FastAPI(
        title="Payments Service API",
        version="1.0.0",
        description="API for Async payment processing service",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(  # type: ignore[call-arg]
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=[
            "http://localhost",
            "http://localhost:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware для correlation ID (trace_id)
    app.add_middleware(TraceIDMiddleware)  # type: ignore[arg-type, call-arg]

    container: AsyncContainer = make_async_container(*get_providers())
    setup_dishka(container, app)

    setup_exception_handlers(app)
    app.include_router(api_v1_router, prefix="/api")

    return app


app = create_app()
