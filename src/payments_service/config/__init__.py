from payments_service.config.api import APISettings
from payments_service.config.app import AppSettings
from payments_service.config.base import Settings
from payments_service.config.broker import BrokerSettings
from payments_service.config.cors import CORSSettings
from payments_service.config.database import DatabaseSettings
from payments_service.config.settings import Settings as NewSettings

__all__ = [
    "APISettings",
    "AppSettings",
    "Settings",  # Backward compatibility
    "NewSettings",  # New modular settings
    "DatabaseSettings",
    "BrokerSettings",
    "CORSSettings",
]
