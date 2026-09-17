"""Use-case обработки платежа консьюмером."""

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, final
from uuid import UUID

import structlog

from payments_service.application.exceptions import WebhookDeliveryError
from payments_service.domain.value_objects.payment_status import PaymentStatus

logger = structlog.get_logger(__name__)

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
        # 1. Получение и проверка статуса (без блокировки)
        async with self.uow:
            payment = await self.uow.payments.get_by_id(payment_id)

        if payment is None:
            logger.error("payment not found", payment_id=str(payment_id))
            return

        # Идемпотентность: вебхук уже доставлен - это дубликат события
        if payment.webhook_delivered_at is not None:
            logger.info("webhook already delivered", payment_id=str(payment_id))
            return

        # 2. Обработка платежа в шлюзе (если еще не обработан)
        if payment.status is PaymentStatus.PENDING:
            # Вызов шлюза ВНЕ транзакции
            result = await self.gateway.charge(payment)

            async with self.uow:
                # Атомарное обновление статуса
                status = (
                    PaymentStatus.SUCCEEDED if result.success else PaymentStatus.FAILED
                )
                message = None if result.success else result.message

                updated = await self.uow.payments.try_mark_processed(
                    payment_id=payment_id, status=status, message=message
                )

                if not updated:
                    # Платёж уже обработан другой доставкой, перечитываем актуальное состояние
                    payment = await self.uow.payments.get_by_id(payment_id)
                    if payment is None:
                        return
                else:
                    # Обновляем локальную сущность для формирования вебхука и корректного состояния
                    if status is PaymentStatus.SUCCEEDED:
                        payment.mark_succeeded()
                    else:
                        payment.mark_failed(message or "Gateway declined payment")

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

            # 4. Успешная доставка (атомарно)
            async with self.uow:
                updated = await self.uow.payments.try_mark_webhook_delivered(payment_id)
                if updated:
                    payment.mark_webhook_delivered()

        except Exception as e:
            # 5. Ошибка доставки - сохраняем состояние попытки
            async with self.uow:
                payment = await self.uow.payments.get_by_id(payment_id)
                if payment is not None:
                    payment.register_webhook_failure(str(e))
                    await self.uow.payments.update(payment)

            # Ретрай только при технических ошибках вебхука.
            # Остальные ошибки (включая DB) не должны приводить к ретраю вебхука консьюмером.
            if isinstance(e, WebhookDeliveryError):
                raise

            logger.exception(
                "unexpected error in webhook delivery phase", payment_id=str(payment_id)
            )
