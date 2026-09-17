"""Webhook echo service - для тестирования отправки вебхуков.

Крошечный FastAPI на POST /hook, который логирует тело запроса.
"""

import logging

import uvicorn
from fastapi import FastAPI, Request

# Настроить простое логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Webhook Echo Service", version="1.0.0")


@app.post("/hook")
async def webhook_handler(request: Request) -> dict[str, str]:
    """Принять вебхук и залогировать его содержимое.

    Args:
        request: Входящий HTTP-запрос.

    Returns:
        Подтверждение приема.
    """
    body = await request.json()
    headers = dict(request.headers)

    logger.info(
        "Received webhook: event=%s, payment_id=%s, status=%s, trace_id=%s",
        body.get("event"),
        body.get("data", {}).get("payment_id"),
        body.get("data", {}).get("status"),
        headers.get("x-request-id", "-"),
    )
    logger.debug("Full webhook body: %s", body)
    logger.debug("Full webhook headers: %s", headers)

    return {"status": "ok", "message": "Webhook received"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
