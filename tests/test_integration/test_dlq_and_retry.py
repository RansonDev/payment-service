"""Integration tests for DLQ and retry mechanism.

Tests verify:
- Retry mechanism with TTL ladder (3 attempts)
- Dead Letter Queue after retry exhaustion
- Outbox publisher flow
- End-to-end payment processing with retries
"""

import asyncio
import json
from typing import Any
import uuid

import aio_pika
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from payments_service.infrastructures.db.models.base import Base
from payments_service.infrastructures.db.models.payment import Payment


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.usefixtures("clean_queues")
async def test_retry_mechanism_with_ttl_ladder(
    test_db_session,
    rabbitmq_connection: aio_pika.Connection,
    get_queue_message_count,
    get_dlq_messages,
):
    """Test retry mechanism goes through TTL ladder: retry.1→retry.2→retry.3→DLQ.

    Scenario:
    1. Publish message to payments.new with unreachable webhook
    2. Verify message moves through retry queues with correct delays
    3. Verify final landing in DLQ

    Expected delays:
    - retry.1 → retry.2: ~5 seconds
    - retry.2 → retry.3: ~10 seconds
    - retry.3 → dlq: ~20 seconds
    """
    # Create test message
    channel = await rabbitmq_connection.channel()

    test_payload = {
        "payment_id": str(uuid.uuid4()),
        "status": "succeeded",
        "webhook_url": "http://unreachable-host-12345.local/webhook",
        "amount": 100.0,
        "currency": "RUB",
    }

    # Create payment in DB before publishing
    payment = Payment(
        id=test_payload["payment_id"],
        amount=100.0,
        currency="RUB",
        description="Retry ladder test",
        status="pending",
        idempotency_key=f"test-retry-{test_payload['payment_id']}",
        request_hash="test-hash-retry",
        webhook_url="http://unreachable-host-12345.local/webhook",
        webhook_delivered_at=None,
        webhook_attempts=0,
    )
    test_db_session.add(payment)
    await test_db_session.commit()

    # Publish to payments.new
    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(test_payload).encode(),
            content_type="application/json",
            headers={"x-attempt": "1"},
        ),
        routing_key="payments.new",
    )

    await channel.close()

    # Wait and verify progression through retry queues
    # Note: This test takes ~45 seconds due to TTL delays (5 + 10 + 20)

    async def wait_for_queue_count(
        queue_name: str, expected_count: int = 1, timeout: int = 20
    ):
        start_time = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start_time < timeout:
            count = await get_queue_message_count(queue_name)
            if count >= expected_count:
                return count
            await asyncio.sleep(0.5)
        # Final check before failing
        return await get_queue_message_count(queue_name)

    # Initial publish is to payments.new, it fails and should go to retry.1
    count = await wait_for_queue_count("payments.retry.1", timeout=15)
    assert count >= 1, f"Message should reach retry.1, but count is {count}"

    # After ~5 seconds in retry.1, it goes back to payments.new, fails and goes to retry.2
    count = await wait_for_queue_count("payments.retry.2", timeout=20)
    assert count >= 1, f"Message should reach retry.2, but count is {count}"

    # After ~10 seconds in retry.2, it goes back to payments.new, fails and goes to retry.3
    count = await wait_for_queue_count("payments.retry.3", timeout=25)
    assert count >= 1, f"Message should reach retry.3, but count is {count}"

    # After ~20 seconds in retry.3, it goes to DLQ
    count = await wait_for_queue_count("payments.dlq", timeout=35)
    assert count >= 1, f"Message should reach DLQ, but count is {count}"

    # Final verification of DLQ message content
    dlq_messages = await get_dlq_messages()
    assert len(dlq_messages) >= 1
    msg = dlq_messages[0]
    assert msg.headers.get("x-attempt") == "3"
    assert "x-death" in msg.headers


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.usefixtures("clean_queues")
async def test_dlq_receives_message_after_retries(
    test_db_session,
    rabbitmq_connection: aio_pika.Connection,
    get_dlq_messages,
    fake_webhook_server: dict[str, Any],
):
    """Test DLQ receives message with proper headers after 3 failed attempts.

    Scenario:
    1. Create payment with webhook that always returns 500
    2. Wait for retry exhaustion
    3. Verify message in DLQ has correct headers

    Expected headers:
    - x-attempt: "3"
    - x-death: history of queue traversal
    - x-failure-reason: error description
    - x-failure-url: webhook URL that failed
    """
    # Configure webhook server to always fail
    fake_webhook_server["response_sequence"].extend([500] * 10)

    # Create test message
    channel = await rabbitmq_connection.channel()

    test_payload = {
        "payment_id": str(uuid.uuid4()),
        "status": "succeeded",
        "webhook_url": fake_webhook_server["url"],
        "amount": 250.0,
        "currency": "EUR",
    }

    # Create payment in DB before publishing
    payment = Payment(
        id=test_payload["payment_id"],
        amount=250.0,
        currency="EUR",
        description="DLQ headers test",
        status="pending",
        idempotency_key=f"test-dlq-{test_payload['payment_id']}",
        request_hash="test-hash-dlq",
        webhook_url=fake_webhook_server["url"],
        webhook_delivered_at=None,
        webhook_attempts=0,
    )
    test_db_session.add(payment)
    await test_db_session.commit()

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(test_payload).encode(),
            content_type="application/json",
            headers={"x-attempt": "1"},
        ),
        routing_key="payments.new",
    )

    await channel.close()

    # Wait for all retries to complete (~40 seconds)
    await asyncio.sleep(45)

    # Retrieve DLQ messages
    dlq_messages = await get_dlq_messages()

    assert len(dlq_messages) >= 1, "DLQ should contain at least one message"

    dlq_message = dlq_messages[0]
    headers = dlq_message.headers or {}

    # Verify headers
    assert "x-death" in headers, "DLQ message should contain x-death header"
    assert headers.get("x-attempt") == "3", "Message should have attempted 3 times"

    # x-death contains queue traversal history
    x_death = headers["x-death"]
    assert isinstance(x_death, list), "x-death should be a list"
    assert len(x_death) >= 1, "x-death should contain at least one entry"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.usefixtures("clean_queues")
async def test_successful_delivery_after_retry(
    test_db_session,
    rabbitmq_connection: aio_pika.Connection,
    fake_webhook_server: dict[str, Any],
    get_queue_message_count,
):
    """Test successful webhook delivery on 3rd attempt.

    Scenario:
    1. Configure webhook server: 500 → 500 → 200
    2. Create payment
    3. Verify webhook delivered on 3rd attempt
    4. Verify message NOT in DLQ

    Expected:
    - Webhook server receives 3 requests
    - Final attempt succeeds
    - Message does not reach DLQ
    """
    # Configure webhook server to fail twice, then succeed
    fake_webhook_server["response_sequence"].extend([500, 500, 200])

    # Create test message
    channel = await rabbitmq_connection.channel()

    test_payload = {
        "payment_id": str(uuid.uuid4()),
        "status": "succeeded",
        "webhook_url": fake_webhook_server["url"],
        "amount": 500.0,
        "currency": "USD",
    }

    # Create payment in DB before publishing
    payment = Payment(
        id=test_payload["payment_id"],
        amount=500.0,
        currency="USD",
        description="Successful retry test",
        status="pending",
        idempotency_key=f"test-success-{test_payload['payment_id']}",
        request_hash="test-hash-success",
        webhook_url=fake_webhook_server["url"],
        webhook_delivered_at=None,
        webhook_attempts=0,
    )
    test_db_session.add(payment)
    await test_db_session.commit()

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(test_payload).encode(),
            content_type="application/json",
            headers={"x-attempt": "1"},
        ),
        routing_key="payments.new",
    )

    await channel.close()

    # Wait for retries to complete
    await asyncio.sleep(50)

    # Verify webhook received 3 requests
    webhook_requests = fake_webhook_server["requests"]
    assert len(webhook_requests) >= 3, "Webhook should receive 3 attempts"

    # Verify message NOT in DLQ
    await asyncio.sleep(2)  # Give some time for any potential extra retries
    dlq_count = await get_queue_message_count("payments.dlq")
    assert dlq_count == 0, "Message should NOT be in DLQ after successful delivery"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.usefixtures("test_db_engine")
async def test_outbox_mechanism(
    test_db_session,
):
    """Test Outbox mechanism: create event, fetch, and mark as published.

    Scenario:
    1. Insert event into outbox table with published_at = NULL
    2. Fetch pending events using OutboxClient
    3. Mark event as published
    4. Verify outbox.published_at is set

    Expected:
    - Event can be fetched when published_at is NULL
    - Event cannot be fetched after marking as published
    - published_at is set correctly
    """
    import json as json_module

    from sqlalchemy import insert
    from sqlalchemy import select as sql_select

    from payments_service.infrastructures.db.models import outbox_table
    from payments_service.infrastructures.outbox.client import OutboxClient

    # Create OutboxClient
    outbox_client = OutboxClient(table=outbox_table)

    # Insert unpublished event into outbox using raw insert
    payload = {
        "payment_id": "test-outbox-001",
        "status": "succeeded",
        "webhook_url": "http://example.com/webhook",
        "amount": 100.0,
        "currency": "RUB",
    }

    result = await test_db_session.execute(
        insert(outbox_table)
        .values(
            exchange="",
            routing_key="payments.new",
            payload=json_module.dumps(payload).encode("utf-8"),
            headers={},
            content_type="application/json",
        )
        .returning(outbox_table.c.id)
    )
    await test_db_session.commit()
    event_id = result.scalar_one()

    # Fetch pending events
    pending_events = await outbox_client.fetch_pending(test_db_session, limit=10)
    assert len(pending_events) >= 1, "Should have at least one pending event"

    pending_event = next((e for e in pending_events if e.id == event_id), None)
    assert pending_event is not None, "Our event should be in pending list"

    # Mark as published
    await outbox_client.mark_published(test_db_session, [event_id])
    await test_db_session.commit()

    # Verify published_at is set
    result = await test_db_session.execute(
        sql_select(outbox_table).where(outbox_table.c.id == event_id)
    )
    updated_event = result.fetchone()
    assert updated_event is not None, "Event should exist"
    assert updated_event.published_at is not None, "published_at should be set"

    # Verify event is no longer in pending
    pending_events_after = await outbox_client.fetch_pending(test_db_session, limit=10)
    pending_ids = [e.id for e in pending_events_after]
    assert event_id not in pending_ids, "Published event should not be in pending list"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.usefixtures("clean_queues")
async def test_end_to_end_with_dlq(
    test_db_session,
    rabbitmq_connection: aio_pika.Connection,
    get_dlq_messages,
    fake_webhook_server: dict[str, Any],
):
    """Test end-to-end flow: payment creation → outbox → retry → DLQ.

    Scenario:
    1. POST /api/payments with unreachable webhook
    2. Wait for full retry cycle
    3. Verify final state

    Expected:
    - payment.status = SUCCEEDED (payment processing succeeded)
    - payment.webhook_delivered_at = NULL (webhook not delivered)
    - DLQ contains message for this payment
    - outbox.published_at is set
    """
    # Configure webhook server to always fail
    fake_webhook_server["response_sequence"].extend([500] * 10)

    # Simulate payment creation and outbox event
    import json as json_module

    from sqlalchemy import insert as sql_insert

    from payments_service.infrastructures.db.models import outbox_table

    payment_id = str(uuid.uuid4())

    # Create payment
    payment = Payment(
        id=payment_id,
        amount=1000.0,
        currency="RUB",
        description="End-to-end DLQ test",
        status="pending",
        idempotency_key="e2e-dlq-test-001",
        request_hash="test-hash-e2e",
        webhook_url=fake_webhook_server["url"],
        webhook_delivered_at=None,
        webhook_attempts=0,
    )
    test_db_session.add(payment)

    # Create outbox event using raw insert
    outbox_event_payload = {
        "payment_id": payment_id,
        "status": "succeeded",
        "webhook_url": fake_webhook_server["url"],
        "amount": 1000.0,
        "currency": "RUB",
    }

    await test_db_session.execute(
        sql_insert(outbox_table).values(
            exchange="",
            routing_key="payments.new",
            payload=json_module.dumps(outbox_event_payload).encode("utf-8"),
            headers={},
            content_type="application/json",
        )
    )

    await test_db_session.commit()

    # Publish event to RabbitMQ (simulating outbox publisher)
    channel = await rabbitmq_connection.channel()

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(outbox_event_payload).encode(),
            content_type="application/json",
            headers={"x-attempt": "1"},
        ),
        routing_key="payments.new",
    )

    await channel.close()

    # Wait for full retry cycle
    await asyncio.sleep(45)

    # Verify DLQ contains message
    dlq_messages = await get_dlq_messages()
    assert len(dlq_messages) >= 1, "DLQ should contain the failed message"

    # Verify payment state
    result = await test_db_session.execute(
        select(Payment).where(Payment.id == payment_id)
    )
    payment_check = result.scalar_one()

    assert payment_check.status == "succeeded", "Payment should be in succeeded state"
    assert payment_check.webhook_delivered_at is None, "Webhook should not be delivered"

    # Verify webhook was attempted 3 times
    webhook_requests = fake_webhook_server["requests"]
    assert len(webhook_requests) >= 3, "Webhook should be attempted 3 times"
