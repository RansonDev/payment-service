"""Fixtures for integration tests."""

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any

import aio_pika
import pytest
from aiohttp import web
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from payments_service.infrastructures.db.models.base import Base


@pytest.fixture(scope="function")
async def test_db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """PostgreSQL engine for integration tests."""
    # Подключение к running postgres из docker-compose
    # Использует переменные окружения или дефолты
    db_host = os.getenv("POSTGRES_SERVER", "postgres")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_user = os.getenv("POSTGRES_USER", "payments")
    db_password = os.getenv("POSTGRES_PASSWORD", "payments")
    db_name = os.getenv("POSTGRES_DB", "payments")

    engine = create_async_engine(
        f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}",
        echo=False,
        connect_args={"ssl": False},
    )

    # Создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Очистка
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine: AsyncEngine):
    """Session for each test."""
    async_session = async_sessionmaker(
        test_db_engine, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        # Rollback removed: TRUNCATE below already cleans up,
        # and rollback undoes committed changes needed by consumer

    # Очистка таблиц после теста
    async with test_db_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE payments, outbox RESTART IDENTITY CASCADE")
        )


@pytest.fixture(scope="function")
async def rabbitmq_connection() -> AsyncGenerator[aio_pika.Connection, None]:
    """RabbitMQ connection for integration tests."""
    # Подключение к RabbitMQ из docker-compose
    # Использует переменные окружения или дефолты
    rabbit_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbit_port = os.getenv("RABBITMQ_PORT", "5672")
    rabbit_user = os.getenv("RABBITMQ_USER", "guest")
    rabbit_password = os.getenv("RABBITMQ_PASSWORD", "guest")

    connection = await aio_pika.connect_robust(
        f"amqp://{rabbit_user}:{rabbit_password}@{rabbit_host}:{rabbit_port}/"
    )

    yield connection

    await connection.close()


@pytest.fixture
async def clean_queues(rabbitmq_connection: aio_pika.Connection):
    """Clean all payment queues before test."""
    channel = await rabbitmq_connection.channel()

    queue_names = [
        "payments.new",
        "payments.retry.1",
        "payments.retry.2",
        "payments.retry.3",
        "payments.dlq",
    ]

    for queue_name in queue_names:
        try:
            queue = await channel.get_queue(queue_name, ensure=False)
            await queue.purge()
        except Exception:
            # Очередь может не существовать
            pass

    await channel.close()


@pytest.fixture
async def fake_webhook_server() -> AsyncGenerator[dict[str, Any], None]:
    """Fake HTTP server for webhook testing."""
    import socket

    requests: list[dict] = []
    response_sequence: list[int] = []  # Список статус-кодов для последовательных ответов

    async def handler(request):
        """Handle webhook requests."""
        body = await request.json()
        requests.append({
            "method": request.method,
            "path": request.path,
            "body": body,
            "headers": dict(request.headers),
        })

        # Если задана последовательность ответов
        if response_sequence:
            status = response_sequence.pop(0)
            if status >= 400:
                return web.Response(status=status, text="Error")

        return web.Response(status=200, text="OK")

    app = web.Application()
    app.router.add_post("/webhook", handler)

    runner = web.AppRunner(app)
    await runner.setup()

    # Listen on 0.0.0.0 to accept connections from other containers
    site = web.TCPSite(runner, "0.0.0.0", 9999)
    await site.start()

    # Get container hostname for URL accessible from other containers
    hostname = socket.gethostname()

    yield {
        "requests": requests,
        "response_sequence": response_sequence,
        "url": f"http://{hostname}:9999/webhook",
    }

    await runner.cleanup()


@pytest.fixture
async def get_queue_message_count(rabbitmq_connection: aio_pika.Connection):
    """Helper to get message count in queue."""
    async def _get_count(queue_name: str) -> int:
        channel = await rabbitmq_connection.channel()
        try:
            queue = await channel.get_queue(queue_name, ensure=False)
            result = await queue.declare(passive=True)
            return result.message_count
        except Exception:
            return 0
        finally:
            await channel.close()

    return _get_count


@pytest.fixture
async def get_dlq_messages(rabbitmq_connection: aio_pika.Connection):
    """Helper to get messages from DLQ."""
    async def _get_messages() -> list[aio_pika.IncomingMessage]:
        channel = await rabbitmq_connection.channel()
        messages = []

        try:
            queue = await channel.get_queue("payments.dlq", ensure=False)

            while True:
                message = await queue.get(timeout=1, fail=False)
                if message is None:
                    break
                messages.append(message)
                await message.ack()

        except Exception:
            pass
        finally:
            await channel.close()

        return messages

    return _get_messages
