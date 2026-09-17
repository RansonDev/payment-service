"""Протокол отправки вебхуков."""

from typing import Any, Protocol


class WebhookSenderProtocol(Protocol):
    """Протокол отправки вебхуков клиентам."""

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        """Отправить вебхук на указанный URL.

        Args:
            url: URL для отправки вебхука.
            payload: Тело вебхука (JSON-сериализуемый dict).

        Raises:
            WebhookDeliveryError: При технической ошибке доставки
                (таймаут, сетевая ошибка, ответ не 2xx).
        """
        ...
