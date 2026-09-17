"""API v1 routers."""

from fastapi import APIRouter

from payments_service.presentation.api.rest.v1.controllers.payment_controller import (
    health_router,
    payment_router,
)

api_v1_router = APIRouter()
api_v1_router.include_router(payment_router)
api_v1_router.include_router(health_router)
