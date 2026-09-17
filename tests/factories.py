from datetime import UTC, datetime, timezone
from decimal import Decimal

from polyfactory.factories import DataclassFactory

from payments_service.application.dtos.payment import PaymentDTO
from payments_service.domain.entities.payment import Payment
from payments_service.domain.value_objects.currency import Currency
from payments_service.domain.value_objects.payment_status import PaymentStatus
from tests.faker import text, url, uuid4, word


class PaymentFactory(DataclassFactory[Payment]):
    """Factory for Payment entity objects."""

    __model__ = Payment

    @classmethod
    def amount(cls) -> Decimal:
        """Generate valid payment amount (positive, max 2 decimal places)."""
        return Decimal(str(cls.__random__.uniform(1.0, 10000.0))).quantize(
            Decimal("0.01")
        )

    @classmethod
    def currency(cls) -> Currency:
        """Generate random currency."""
        return cls.__random__.choice([Currency.RUB, Currency.USD, Currency.EUR])

    @classmethod
    def status(cls) -> PaymentStatus:
        """Generate random payment status."""
        return cls.__random__.choice(
            [PaymentStatus.PENDING, PaymentStatus.SUCCEEDED, PaymentStatus.FAILED]
        )

    @classmethod
    def description(cls) -> str:
        """Generate payment description."""
        return text()[:200]

    @classmethod
    def payment_metadata(cls) -> dict:
        """Generate payment metadata."""
        return {"order_id": word(), "user_id": str(uuid4())}

    @classmethod
    def idempotency_key(cls) -> str:
        """Generate idempotency key."""
        return f"idem-{uuid4()}"

    @classmethod
    def request_hash(cls) -> str:
        """Generate request hash."""
        return word()[:64]

    @classmethod
    def webhook_url(cls) -> str:
        """Generate webhook URL."""
        return url()

    @classmethod
    def created_at(cls) -> datetime:
        """Generate created_at timestamp."""
        return datetime.now(UTC)


class PaymentDTOFactory(DataclassFactory[PaymentDTO]):
    """Factory for PaymentDTO objects."""

    __model__ = PaymentDTO

    @classmethod
    def amount(cls) -> Decimal:
        """Generate valid payment amount (positive, max 2 decimal places)."""
        return Decimal(str(cls.__random__.uniform(1.0, 10000.0))).quantize(
            Decimal("0.01")
        )

    @classmethod
    def currency(cls) -> Currency:
        """Generate random currency."""
        return cls.__random__.choice([Currency.RUB, Currency.USD, Currency.EUR])

    @classmethod
    def status(cls) -> PaymentStatus:
        """Generate random payment status."""
        return cls.__random__.choice(
            [PaymentStatus.PENDING, PaymentStatus.SUCCEEDED, PaymentStatus.FAILED]
        )

    @classmethod
    def description(cls) -> str:
        """Generate payment description."""
        return text()[:200]

    @classmethod
    def payment_metadata(cls) -> dict:
        """Generate payment metadata."""
        return {"order_id": word(), "user_id": str(uuid4())}

    @classmethod
    def idempotency_key(cls) -> str:
        """Generate idempotency key."""
        return f"idem-{uuid4()}"

    @classmethod
    def request_hash(cls) -> str:
        """Generate request hash."""
        return word()[:64]

    @classmethod
    def webhook_url(cls) -> str:
        """Generate webhook URL."""
        return url()

    @classmethod
    def created_at(cls) -> datetime:
        """Generate created_at timestamp."""
        return datetime.now(UTC)
