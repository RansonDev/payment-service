"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from payments_service.application.interfaces.repositories import (
    PaymentRepositoryProtocol,
)
from payments_service.application.interfaces.uow import UnitOfWorkProtocol
from payments_service.config.settings import Settings


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Set asyncio as the backend for anyio tests."""
    return "asyncio"


@pytest.fixture
async def test_engine() -> AsyncGenerator[Any, None]:
    """Create test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine: Any) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_settings() -> Mock:
    """Mock Settings for unit tests."""
    settings = Mock(spec=Settings)
    settings.api.api_key = "test-api-key"
    return settings


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock PaymentRepository for unit tests."""
    return AsyncMock(spec=PaymentRepositoryProtocol)


@pytest.fixture
def mock_uow() -> AsyncMock:
    """Mock UnitOfWork for unit tests."""
    uow = AsyncMock(spec=UnitOfWorkProtocol)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    return uow
