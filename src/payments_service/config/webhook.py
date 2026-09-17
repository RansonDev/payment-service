"""Конфигурация HTTP-клиента для вебхуков."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebhookSettings(BaseSettings):
    """Настройки HTTP-клиента для отправки вебхуков."""

    model_config = SettingsConfigDict(env_prefix="WEBHOOK_")

    timeout_seconds: float = Field(
        default=5.0, description="Таймаут запроса в секундах"
    )
    max_retries: int = Field(default=3, description="Максимальное количество попыток")
