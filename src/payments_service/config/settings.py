from pydantic import Field
from pydantic_settings import BaseSettings

from payments_service.config.api import APISettings
from payments_service.config.app import AppSettings
from payments_service.config.broker import BrokerSettings
from payments_service.config.cors import CORSSettings
from payments_service.config.database import DatabaseSettings
from payments_service.config.gateway import GatewaySettings
from payments_service.config.webhook import WebhookSettings


class Settings(BaseSettings):
    """Main application settings that combines all configuration objects.

    This class serves as a facade that provides access to all configuration
    sections of the application. Each configuration section is responsible
    for a specific domain (database, broker, cors, etc.).
    """

    app: AppSettings = Field(default_factory=AppSettings)
    api: APISettings = Field(default_factory=APISettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    webhook: WebhookSettings = Field(default_factory=WebhookSettings)

    @property
    def app_name(self) -> str:
        """Get application name."""
        return self.app.app_name

    @property
    def environment(self) -> str:
        """Get application environment."""
        return self.app.environment

    @property
    def log_level(self) -> str:
        """Get log level."""
        return self.app.log_level

    @property
    def debug(self) -> bool:
        """Get debug flag."""
        return self.app.debug

    @property
    def database_url(self) -> str:
        """Get database URL."""
        return str(self.database.database_url)

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Get SQLAlchemy database URI."""
        return str(self.database.sqlalchemy_database_uri)

    @property
    def broker_url(self) -> str:
        """Get broker URL."""
        return self.broker.broker_url

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS origins."""
        return self.cors.cors_origins

    @property
    def cors_allow_credentials(self) -> bool:
        """Get CORS allow credentials flag."""
        return self.cors.cors_allow_credentials

    @property
    def cors_allow_methods(self) -> list[str]:
        """Get CORS allow methods."""
        return self.cors.cors_allow_methods

    @property
    def cors_allow_headers(self) -> list[str]:
        """Get CORS allow headers."""
        return self.cors.cors_allow_headers

    @property
    def postgres_user(self) -> str:
        """Get PostgreSQL username."""
        return self.database.postgres_user

    @property
    def postgres_password(self) -> str:
        """Get PostgreSQL password."""
        return self.database.postgres_password

    @property
    def postgres_server(self) -> str:
        """Get PostgreSQL server."""
        return self.database.postgres_server

    @property
    def postgres_port(self) -> int:
        """Get PostgreSQL port."""
        return self.database.postgres_port

    @property
    def postgres_db(self) -> str:
        """Get PostgreSQL database name."""
        return self.database.postgres_db
