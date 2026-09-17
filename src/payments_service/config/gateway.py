"""Конфигурация эмулятора платёжного шлюза."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Настройки эмулятора платёжного шлюза."""

    model_config = SettingsConfigDict(env_prefix="GATEWAY_")

    success_rate: float = Field(default=0.9, description="Вероятность успеха (0.0-1.0)")
    min_delay_seconds: float = Field(
        default=2.0, description="Минимальная задержка в секундах"
    )
    max_delay_seconds: float = Field(
        default=5.0, description="Максимальная задержка в секундах"
    )
