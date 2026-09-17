"""API configuration settings."""

from pydantic import Field
from pydantic_settings import BaseSettings


class APISettings(BaseSettings):
    """API configuration settings."""

    api_key: str = Field(..., description="API key for authentication", alias="API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
