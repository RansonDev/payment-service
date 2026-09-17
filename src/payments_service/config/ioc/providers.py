"""Dishka dependency injection providers."""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payments_service.application.interfaces.gateway import PaymentGatewayProtocol
from payments_service.application.interfaces.mappers import DtoEntityMapperProtocol
from payments_service.application.interfaces.repositories import (
    OutboxRepositoryProtocol,
    PaymentRepositoryProtocol,
)
from payments_service.application.interfaces.uow import UnitOfWorkProtocol
from payments_service.application.interfaces.webhook import WebhookSenderProtocol
from payments_service.application.mappers import PaymentMapper
from payments_service.application.use_cases.create_payment import CreatePaymentUseCase
from payments_service.application.use_cases.get_payment import GetPaymentUseCase
from payments_service.application.use_cases.process_payment import ProcessPaymentUseCase
from payments_service.config.settings import Settings
from payments_service.infrastructures.db.mappers.payment import PaymentDbMapper
from payments_service.infrastructures.db.models import outbox_table
from payments_service.infrastructures.db.repositories.outbox import (
    OutboxRepositorySQLAlchemy,
)
from payments_service.infrastructures.db.repositories.payment import (
    PaymentRepositorySQLAlchemy,
)
from payments_service.infrastructures.db.session import (
    create_engine,
    get_session_factory,
)
from payments_service.infrastructures.db.uow import UnitOfWorkSQLAlchemy
from payments_service.infrastructures.gateway.fake import FakePaymentGateway
from payments_service.infrastructures.http.webhook import HttpWebhookSender
from payments_service.infrastructures.outbox.client import OutboxClient


class SettingsProvider(Provider):
    """Provides application settings."""

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """Provides the Settings instance."""
        return Settings()


class DatabaseProvider(Provider):
    """Provides database-related dependencies."""

    @provide(scope=Scope.APP)
    async def get_engine(self, settings: Settings) -> AsyncIterator[AsyncEngine]:
        """Provides an asynchronous SQLAlchemy engine."""
        engine = create_engine(str(settings.database_url), is_echo=settings.debug)
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide(scope=Scope.APP)
    def get_session_factory(
        self, engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Provides an asynchronous session factory for SQLAlchemy."""
        return get_session_factory(engine)

    @provide(scope=Scope.REQUEST)
    async def get_session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        """Provides an asynchronous SQLAlchemy session.

        КРИТИЧНО: сессия в Scope.REQUEST, чтобы каждый запрос получал свою.
        В Scope.APP станет общей на все запросы и сломается тихо.
        """
        async with factory() as session:
            yield session


class OutboxProvider(Provider):
    """Provides outbox client."""

    @provide(scope=Scope.APP)
    def get_outbox_client(self) -> OutboxClient:
        """Provides the OutboxClient."""
        return OutboxClient(table=outbox_table)


class GatewayProvider(Provider):
    """Provides payment gateway emulator."""

    @provide(scope=Scope.APP)
    def get_payment_gateway(self, settings: Settings) -> PaymentGatewayProtocol:
        """Provides the payment gateway emulator."""
        return FakePaymentGateway(
            success_rate=settings.gateway.success_rate,
            min_delay_seconds=settings.gateway.min_delay_seconds,
            max_delay_seconds=settings.gateway.max_delay_seconds,
        )


class WebhookProvider(Provider):
    """Provides webhook HTTP client."""

    @provide(scope=Scope.REQUEST)
    def get_webhook_sender(self, settings: Settings) -> WebhookSenderProtocol:
        """Provides the webhook HTTP client."""
        return HttpWebhookSender(timeout_seconds=settings.webhook.timeout_seconds)


class MapperProvider(Provider):
    """Provides mappers for entities and DTOs."""

    @provide(scope=Scope.APP)
    def get_dto_entity_mapper(self) -> DtoEntityMapperProtocol:
        """Provides the DTO-Entity mapper."""
        return PaymentMapper()

    @provide(scope=Scope.APP)
    def get_db_entity_mapper(self) -> PaymentDbMapper:
        """Provides the DB-Entity mapper."""
        return PaymentDbMapper()


class RepositoryProvider(Provider):
    """Provides repository implementations."""

    @provide(scope=Scope.REQUEST)
    def get_payment_repository(
        self,
        session: AsyncSession,
        mapper: PaymentDbMapper,
    ) -> PaymentRepositoryProtocol:
        """Provides the Payment repository."""
        return PaymentRepositorySQLAlchemy(session=session, mapper=mapper)

    @provide(scope=Scope.REQUEST)
    def get_outbox_repository(
        self,
        session: AsyncSession,
        client: OutboxClient,
    ) -> OutboxRepositoryProtocol:
        """Provides the Outbox repository."""
        return OutboxRepositorySQLAlchemy(session=session, client=client)


class UnitOfWorkProvider(Provider):
    """Provides UnitOfWork implementation."""

    @provide(scope=Scope.REQUEST)
    def get_uow(
        self,
        session: AsyncSession,
        payment_repo: PaymentRepositoryProtocol,
        outbox_repo: OutboxRepositoryProtocol,
    ) -> UnitOfWorkProtocol:
        """Provides the UnitOfWork."""
        return UnitOfWorkSQLAlchemy(
            session=session,
            payments=payment_repo,
            outbox=outbox_repo,
        )


class UseCaseProvider(Provider):
    """Provides use-case implementations."""

    @provide(scope=Scope.REQUEST)
    def get_create_payment_use_case(
        self,
        uow: UnitOfWorkProtocol,
        mapper: DtoEntityMapperProtocol,
    ) -> CreatePaymentUseCase:
        """Provides the CreatePayment use-case."""
        return CreatePaymentUseCase(uow=uow, mapper=mapper)

    @provide(scope=Scope.REQUEST)
    def get_get_payment_use_case(
        self,
        uow: UnitOfWorkProtocol,
        mapper: DtoEntityMapperProtocol,
    ) -> GetPaymentUseCase:
        """Provides the GetPayment use-case."""
        return GetPaymentUseCase(uow=uow, mapper=mapper)

    @provide(scope=Scope.REQUEST)
    def get_process_payment_use_case(
        self,
        uow: UnitOfWorkProtocol,
        gateway: PaymentGatewayProtocol,
        webhook: WebhookSenderProtocol,
    ) -> ProcessPaymentUseCase:
        """Provides the ProcessPayment use-case (для консьюмера)."""
        return ProcessPaymentUseCase(uow=uow, gateway=gateway, webhook=webhook)
