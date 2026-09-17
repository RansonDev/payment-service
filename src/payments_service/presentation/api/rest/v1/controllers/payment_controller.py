"""Payment API controller."""

import hashlib
import hmac
import json
from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Body, Header, HTTPException, Path, status

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.application.use_cases.create_payment import (
    CreatePaymentCommand,
    CreatePaymentUseCase,
)
from payments_service.application.use_cases.get_payment import GetPaymentUseCase
from payments_service.config.settings import Settings
from payments_service.domain.value_objects.currency import Currency
from payments_service.presentation.api.rest.v1.schemas.requests import (
    CreatePaymentRequestSchema,
)
from payments_service.presentation.api.rest.v1.schemas.responses import (
    CreatePaymentResponseSchema,
    HealthResponseSchema,
    PaymentResponseSchema,
)

payment_router = APIRouter(
    prefix="/payments", tags=["payments"], route_class=DishkaRoute
)
health_router = APIRouter(tags=["health"], route_class=DishkaRoute)


def compute_request_hash(body: CreatePaymentRequestSchema) -> str:
    """Вычислить SHA256-хеш от канонизированного JSON тела запроса.

    КРИТИЧНО: ключи должны быть отсортированы для детерминированного хеша.

    Args:
        body: Тело запроса.

    Returns:
        SHA256-хеш в hex формате.
    """
    canonical_json = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@payment_router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreatePaymentResponseSchema,
    summary="Создать платёж",
    description="Принимает запрос на создание платежа, отвечает 202 Accepted немедленно.",
)
async def create_payment(
    body: Annotated[CreatePaymentRequestSchema, Body()],
    x_api_key: Annotated[str, Header(...)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    settings: FromDishka[Settings],
    use_case: FromDishka[CreatePaymentUseCase],
) -> CreatePaymentResponseSchema:
    """Создать платёж.

    Args:
        body: Тело запроса с параметрами платежа.
        x_api_key: API-ключ из заголовка X-API-Key.
        idempotency_key: Ключ идемпотентности из заголовка Idempotency-Key.
        settings: Настройки приложения.
        use_case: Use-case создания платежа.

    Returns:
        Информация о созданном платеже (payment_id, status, created_at).

    Raises:
        HTTPException: 401 если API-ключ неверен.
    """
    # КРИТИЧНО: hmac.compare_digest защищает от timing attacks
    if not hmac.compare_digest(x_api_key, settings.api.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    request_hash = compute_request_hash(body)

    command = CreatePaymentCommand(
        amount=body.amount,
        currency=Currency(body.currency),
        description=body.description,
        metadata=body.metadata,
        webhook_url=body.webhook_url,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )

    payment_dto, _created = await use_case(command)

    return CreatePaymentResponseSchema(
        payment_id=payment_dto.id,
        status=payment_dto.status,
        created_at=payment_dto.created_at,
    )


@payment_router.get(
    "/{payment_id}",
    status_code=status.HTTP_200_OK,
    response_model=PaymentResponseSchema,
    summary="Получить информацию о платеже",
    description="Возвращает полную информацию о платеже по его ID.",
)
async def get_payment(
    payment_id: Annotated[UUID, Path(description="Идентификатор платежа")],
    x_api_key: Annotated[str, Header(...)],
    settings: FromDishka[Settings],
    use_case: FromDishka[GetPaymentUseCase],
) -> PaymentDTO:
    """Получить информацию о платеже.

    Args:
        payment_id: UUID платежа.
        x_api_key: API-ключ из заголовка X-API-Key.
        settings: Настройки приложения.
        use_case: Use-case получения платежа.

    Returns:
        Полная информация о платеже.

    Raises:
        HTTPException: 401 если API-ключ неверен.
    """
    # КРИТИЧНО: hmac.compare_digest защищает от timing attacks
    if not hmac.compare_digest(x_api_key, settings.api.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return await use_case(payment_id)


@health_router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    response_model=HealthResponseSchema,
    summary="Health check",
    description="Проверка работоспособности сервиса. Не требует авторизации.",
)
async def health_check() -> HealthResponseSchema:
    """Health check endpoint.

    Returns:
        Статус сервиса.
    """
    return HealthResponseSchema(status="ok")
