"""Use-case обработки платежа консьюмером."""

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, final
from uuid import UUID

from payments_service.domain.value_objects.payment_status import PaymentStatus

if TYPE_CHECKING:
    from payments_service.application.interfaces.gateway import (
        PaymentGatewayProtocol,
    )
    from payments_service.application.interfaces.uow import UnitOfWorkProtocol
    from payments_service.application.interfaces.webhook import (
        WebhookSenderProtocol,
    )


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessPaymentUseCase:
    """Use-case обработки платежа консьюмером.

    Идемпотентность реализована через ветвление по состоянию платежа:
    - webhook_delivered_at заполнен → сообщение дубликат, выход
    - status PENDING → вызвать шлюз, проставить результат, отправить вебхук
    - status финальный, вебхук не доставлен → пропустить шлюз, сразу вебхук

    КРИТИЧНО: неуспешный платёж (FAILED) - финальное состояние, НЕ повод для
    повтора. Повторяются только технические сбои доставки вебхука.
    """

    uow: "UnitOfWorkProtocol"
    gateway: "PaymentGatewayProtocol"
    webhook: "WebhookSenderProtocol"

    async def __call__(self, payment_id: UUID) -> None:
        """Обработать платёж.

        Args:
            payment_id: UUID платежа для обработки.

        Raises:
            PaymentNotFoundError: Платёж не найден.
            WebhookDeliveryError: Техническая ошибка доставки вебхука.
        """
        # 1. Получение и проверка статуса
        async with self.uow:
            payment = await self.uow.payments.get_for_update(payment_id)
 
        if payment is None:
            import structlog
            structlog.get_logger(__name__).error("payment not found", payment_id=str(payment_id))
            return
 
        # Идемпотентность: вебхук уже доставлен - это дубликат события
        if payment.webhook_delivered_at is not None:
            import structlog
            structlog.get_logger(__name__).info("webhook already delivered", payment_id=str(payment_id))
            return

        # 2. Обработка платежа в шлюзе (если еще не обработан)
        if payment.status is PaymentStatus.PENDING:
            result = await self.gateway.charge(payment)

            async with self.uow:
                payment = await self.uow.payments.get_for_update(payment_id)
                if payment is None:
                    return

                if result.success:
                    payment.mark_succeeded()
                else:
                    payment.mark_failed(result.message)

                await self.uow.payments.update(payment)

        # 3. Подготовка и отправка вебхука
        event_type = (
            "payment.succeeded"
            if payment.status is PaymentStatus.SUCCEEDED
            else "payment.failed"
        )

        payload = {
            "event": event_type,
            "data": {
                "payment_id": str(payment.id),
                "amount": str(payment.amount),
                "currency": payment.currency.value,
                "status": payment.status.value,
                "description": payment.description,
                "metadata": payment.payment_metadata,
                "created_at": payment.created_at.isoformat(),
                "processed_at": (
                    payment.processed_at.isoformat() if payment.processed_at else None
                ),
            },
        }

        try:
            await self.webhook.send(payment.webhook_url, payload)

            # 4. Успешная доставка
            async with self.uow:
                payment = await self.uow.payments.get_for_update(payment_id)
                if payment is not None:
                    payment.mark_webhook_delivered()
                    await self.uow.payments.update(payment)

        except Exception as e:
            # 5. Ошибка доставки - сохраняем состояние попытки
            async with self.uow:
                payment = await self.uow.payments.get_for_update(payment_id)
                if payment is not None:
                    payment.register_webhook_failure(str(e))
                    await self.uow.payments.update(payment)
            raise
