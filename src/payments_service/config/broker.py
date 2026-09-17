from typing import final

from pydantic import Field
from pydantic_settings import BaseSettings


@final
class BrokerSettings(BaseSettings):
    """Настройки RabbitMQ брокера."""

    broker_url: str = Field(..., alias="BROKER_URL")
    prefetch_count: int = Field(10, alias="BROKER_PREFETCH_COUNT")

    retry_ttl_level_1_ms: int = Field(5_000, alias="RETRY_TTL_LEVEL_1_MS")
    retry_ttl_level_2_ms: int = Field(10_000, alias="RETRY_TTL_LEVEL_2_MS")
    retry_ttl_level_3_ms: int = Field(20_000, alias="RETRY_TTL_LEVEL_3_MS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
