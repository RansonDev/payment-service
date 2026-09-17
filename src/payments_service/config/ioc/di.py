"""Dishka dependency injection configuration."""

from dishka import Provider

from payments_service.config.ioc.providers import (
    DatabaseProvider,
    GatewayProvider,
    MapperProvider,
    OutboxProvider,
    RepositoryProvider,
    SettingsProvider,
    UnitOfWorkProvider,
    UseCaseProvider,
    WebhookProvider,
)


def get_providers() -> list[Provider]:
    """Returns a list of Dishka providers for dependency injection.

    Returns:
        list[Provider]: A list of configured providers.
    """
    return [
        SettingsProvider(),
        DatabaseProvider(),
        OutboxProvider(),
        GatewayProvider(),
        WebhookProvider(),
        MapperProvider(),
        RepositoryProvider(),
        UnitOfWorkProvider(),
        UseCaseProvider(),
    ]
