"""Unit tests for Payment API with mocks.

Тесты используют моки вместо реальных БД и брокера.
"""

from datetime import UTC, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.application.exceptions import (
    IdempotencyKeyConflictError,
    PaymentNotFoundError,
)
from payments_service.application.use_cases.create_payment import CreatePaymentUseCase
from payments_service.application.use_cases.get_payment import GetPaymentUseCase
from payments_service.config.settings import Settings
from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus
from payments_service.presentation.api.rest.error_handling import (
    setup_exception_handlers,
)
from payments_service.presentation.api.rest.v1.routers import api_v1_router

# Global mocks that will be configured per test
_mock_create_payment_use_case: AsyncMock | None = None
_mock_get_payment_use_case: AsyncMock | None = None


class TestUseCaseProvider(Provider):
    """Test provider with mocked use cases."""

    scope = Scope.REQUEST

    @provide
    def get_create_payment_use_case(self) -> CreatePaymentUseCase:
        """Provide mocked CreatePaymentUseCase."""
        assert _mock_create_payment_use_case is not None
        return _mock_create_payment_use_case  # type: ignore[return-value]

    @provide
    def get_get_payment_use_case(self) -> GetPaymentUseCase:
        """Provide mocked GetPaymentUseCase."""
        assert _mock_get_payment_use_case is not None
        return _mock_get_payment_use_case  # type: ignore[return-value]


class TestSettingsProvider(Provider):
    """Test provider with test settings."""

    scope = Scope.APP

    @provide
    def get_settings(self) -> Settings:
        """Provide test settings."""
        settings = Mock(spec=Settings)
        settings.api = Mock()
        settings.api.api_key = "test-api-key"
        return settings  # type: ignore[return-value]


def create_test_app() -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI(
        title="Test Payments API",
        version="test",
    )

    container: AsyncContainer = make_async_container(
        TestSettingsProvider(),
        TestUseCaseProvider(),
    )
    setup_dishka(container, app)

    setup_exception_handlers(app)
    app.include_router(api_v1_router, prefix="/api")

    return app


@pytest.fixture
def test_app() -> FastAPI:
    """Create test FastAPI app."""
    return create_test_app()


@pytest.fixture
async def test_client(test_app: FastAPI) -> AsyncClient:
    """Create test HTTP client."""
    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_payment_api(test_client: AsyncClient) -> None:
    """Тест создания платежа через API."""
    # Arrange
    global _mock_create_payment_use_case
    _mock_create_payment_use_case = AsyncMock(spec=CreatePaymentUseCase)

    payment_id = uuid4()
    payment_dto = PaymentDTO(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Integration test payment",
        payment_metadata={"order_id": "test-123"},
        status=PaymentStatus.PENDING,
        idempotency_key="integration-test-key-001",
        request_hash="test-hash",
        webhook_url="http://example.com/webhook",
        created_at=datetime.now(UTC),
        processed_at=None,
        webhook_delivered_at=None,
        webhook_attempts=0,
        webhook_last_error=None,
    )

    _mock_create_payment_use_case.return_value = (payment_dto, True)

    payload = {
        "amount": 100.50,
        "currency": "RUB",
        "description": "Integration test payment",
        "metadata": {"order_id": "test-123"},
        "webhook_url": "http://example.com/webhook",
    }

    headers = {
        "X-API-Key": "test-api-key",
        "Idempotency-Key": "integration-test-key-001",
    }

    # Act
    response = await test_client.post(
        "/api/payments",
        json=payload,
        headers=headers,
    )

    # Assert
    assert response.status_code == 202
    data = response.json()
    assert "payment_id" in data
    assert data["status"] == "pending"  # PaymentStatus.PENDING enum value
    assert "created_at" in data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_payment_idempotency(test_client: AsyncClient) -> None:
    """Тест идемпотентности создания платежа."""
    # Arrange
    global _mock_create_payment_use_case
    _mock_create_payment_use_case = AsyncMock(spec=CreatePaymentUseCase)

    payment_id = uuid4()
    payment_dto = PaymentDTO(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Idempotency test",
        payment_metadata={"order_id": "test-456"},
        status=PaymentStatus.PENDING,
        idempotency_key="integration-test-key-002",
        request_hash="test-hash",
        webhook_url="http://example.com/webhook",
        created_at=datetime.now(UTC),
        processed_at=None,
        webhook_delivered_at=None,
        webhook_attempts=0,
        webhook_last_error=None,
    )

    # Оба вызова возвращают одинаковый результат
    _mock_create_payment_use_case.return_value = (payment_dto, False)

    payload = {
        "amount": 100.50,
        "currency": "RUB",
        "description": "Idempotency test",
        "metadata": {"order_id": "test-456"},
        "webhook_url": "http://example.com/webhook",
    }

    headers = {
        "X-API-Key": "test-api-key",
        "Idempotency-Key": "integration-test-key-002",
    }

    # Act
    response1 = await test_client.post(
        "/api/payments",
        json=payload,
        headers=headers,
    )

    response2 = await test_client.post(
        "/api/payments",
        json=payload,
        headers=headers,
    )

    # Assert
    assert response1.status_code == 202
    assert response2.status_code == 202

    data1 = response1.json()
    data2 = response2.json()

    # Должны вернуть тот же самый платёж
    assert data1["payment_id"] == data2["payment_id"]
    assert data1["status"] == data2["status"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_payment_idempotency_conflict(test_client: AsyncClient) -> None:
    """Тест конфликта идемпотентного ключа с разным телом."""
    # Arrange
    global _mock_create_payment_use_case
    _mock_create_payment_use_case = AsyncMock(spec=CreatePaymentUseCase)

    payment_id = uuid4()
    payment_dto = PaymentDTO(
        id=payment_id,
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="First request",
        payment_metadata={"order_id": "test-789"},
        status=PaymentStatus.PENDING,
        idempotency_key="integration-test-key-003",
        request_hash="hash1",
        webhook_url="http://example.com/webhook",
        created_at=datetime.now(UTC),
        processed_at=None,
        webhook_delivered_at=None,
        webhook_attempts=0,
        webhook_last_error=None,
    )

    # Первый запрос успешен
    _mock_create_payment_use_case.return_value = (payment_dto, True)

    headers = {
        "X-API-Key": "test-api-key",
        "Idempotency-Key": "integration-test-key-003",
    }

    payload1 = {
        "amount": 100.50,
        "currency": "RUB",
        "description": "First request",
        "metadata": {"order_id": "test-789"},
        "webhook_url": "http://example.com/webhook",
    }

    payload2 = {
        "amount": 200.00,  # Другая сумма
        "currency": "RUB",
        "description": "Second request",
        "metadata": {"order_id": "test-789"},
        "webhook_url": "http://example.com/webhook",
    }

    # Act
    response1 = await test_client.post(
        "/api/payments",
        json=payload1,
        headers=headers,
    )

    # Для второго запроса мок должен выбросить IdempotencyKeyConflictError
    _mock_create_payment_use_case.side_effect = IdempotencyKeyConflictError(
        "integration-test-key-003"
    )

    response2 = await test_client.post(
        "/api/payments",
        json=payload2,
        headers=headers,
    )

    # Assert
    assert response1.status_code == 202
    assert response2.status_code == 409


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_payment_api(test_client: AsyncClient) -> None:
    """Тест получения информации о платеже."""
    # Arrange
    global _mock_get_payment_use_case
    _mock_get_payment_use_case = AsyncMock(spec=GetPaymentUseCase)

    payment_id = uuid4()
    # Mock возвращает dict вместо PaymentDTO для совместимости с Pydantic
    payment_response = {
        "id": payment_id,
        "amount": "100.50",  # str as expected by PaymentResponseSchema
        "currency": "RUB",  # str
        "description": "Get payment test",
        "payment_metadata": {"order_id": "test-999"},
        "status": "pending",  # str
        "idempotency_key": "integration-test-key-004",
        "request_hash": "test-hash",
        "webhook_url": "http://example.com/webhook",
        "created_at": datetime.now(UTC),
        "processed_at": None,
        "webhook_delivered_at": None,
        "webhook_attempts": 0,
        "webhook_last_error": None,
    }

    # Возвращаем PaymentDTO но Pydantic будет использовать from_attributes
    payment_dto = type(
        "PaymentDTO", (), payment_response
    )()  # Create object with attributes
    _mock_get_payment_use_case.return_value = payment_dto

    # Act
    get_response = await test_client.get(
        f"/api/payments/{payment_id}",
        headers={"X-API-Key": "test-api-key"},
    )

    # Assert
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == str(payment_id)
    assert data["amount"] == "100.50"  # str in response
    assert data["currency"] == "RUB"
    assert data["description"] == "Get payment test"
    assert data["status"] == "pending"  # Enum value as string
    assert data["payment_metadata"] == {"order_id": "test-999"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_payment_not_found(test_client: AsyncClient) -> None:
    """Тест получения несуществующего платежа."""
    # Arrange
    global _mock_get_payment_use_case
    _mock_get_payment_use_case = AsyncMock(spec=GetPaymentUseCase)

    non_existent_id = uuid4()

    _mock_get_payment_use_case.side_effect = PaymentNotFoundError(non_existent_id)

    # Act
    response = await test_client.get(
        f"/api/payments/{non_existent_id}",
        headers={"X-API-Key": "test-api-key"},
    )

    # Assert
    assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_key_validation(test_client: AsyncClient) -> None:
    """Тест валидации API ключа."""
    payload = {
        "amount": 100.50,
        "currency": "RUB",
        "description": "API key test",
        "metadata": {},
        "webhook_url": "http://example.com/webhook",
    }

    # Missing X-API-Key header -> 422 Unprocessable Entity
    response1 = await test_client.post(
        "/api/payments",
        json=payload,
        headers={"Idempotency-Key": "key-005"},
    )

    # Wrong X-API-Key -> 401 Unauthorized
    response2 = await test_client.post(
        "/api/payments",
        json=payload,
        headers={
            "X-API-Key": "wrong-key",
            "Idempotency-Key": "key-006",
        },
    )

    assert response1.status_code == 422  # Missing required header
    assert response2.status_code == 401  # Invalid API key


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_endpoint(test_client: AsyncClient) -> None:
    """Тест health endpoint."""
    response = await test_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
