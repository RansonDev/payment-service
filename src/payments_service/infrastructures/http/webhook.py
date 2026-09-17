"""HTTP-клиент для отправки вебхуков."""

from dataclasses import dataclass
from typing import Any, final

import httpx

from payments_service.application.exceptions import WebhookDeliveryError
from payments_service.application.interfaces.webhook import WebhookSenderProtocol
from payments_service.infrastructures.context import context


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class HttpWebhookSender(WebhookSenderProtocol):
    """HTTP-клиент для отправки вебхуков на httpx.

    Таймаут и количество попыток берутся из конфигурации.
    Успехом считается любой 2xx ответ.
    """

    timeout_seconds: float

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        """Отправить вебхук через HTTP POST.

        Args:
            url: URL для отправки вебхука.
            payload: Тело вебхука (JSON-сериализуемый dict).

        Raises:
            WebhookDeliveryError: При технической ошибке доставки
                (таймаут, сетевая ошибка, ответ не 2xx).
        """
        try:
            trace_id = context.get("log_context", {}).get("trace_id", "")

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Request-ID": trace_id,
                    },
                )

                if not (200 <= response.status_code < 300):
                    reason = f"HTTP {response.status_code}: {response.text[:200]}"
                    raise WebhookDeliveryError(url, reason)

        except httpx.TimeoutException as e:
            raise WebhookDeliveryError(url, f"Timeout: {e}") from e
        except httpx.NetworkError as e:
            raise WebhookDeliveryError(url, f"Network error: {e}") from e
        except httpx.HTTPError as e:
            raise WebhookDeliveryError(url, f"HTTP error: {e}") from e
