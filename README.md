# Payments Service

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-blue.svg)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-4.2-orange.svg)
![Docker](https://img.shields.io/badge/Docker-required-blue.svg)

Микросервис асинхронной обработки платежей с гарантиями доставки событий, идемпотентностью и развитым механизмом повторных попыток.

## Quick Start

### Запуск одной командой
```bash
# Клонировать и запустить (требуется Docker)
docker compose up -d
```
Сервис будет доступен по адресу: http://localhost:8000/api/health
Документация: http://localhost:8000/api/docs

---

## О проекте

**Payments Service** — это демонстрационный микросервис обработки платежей, построенный на принципах **Clean Architecture**. Проект решает типичные задачи распределенных систем:

- **Асинхронность**: Быстрый ответ `202 Accepted`, вся тяжелая логика выполняется в фоновых воркерах.
- **Гарантии доставки (At-Least-Once)**: Использование Transactional Outbox Pattern гарантирует, что ни одно событие не будет потеряно.
- **Идемпотентность**: Полная защита от дубликатов на уровне API (через `Idempotency-Key` и хэш запроса) и на уровне Consumer.
- **Отказоустойчивость**: 
    - **Outbox Publisher**: Экспоненциальная задержка при ошибках публикации.
    - **Webhook Retry**: Лестница TTL-очередей RabbitMQ (5с → 10с → 20с) для эффективной обработки временных сбоев на стороне клиента.
    - **DLQ (Dead Letter Queue)**: Надежное хранение сообщений, исчерпавших лимит попыток.
- **Автоматизация**: Автоматическое применение миграций при запуске контейнеров через `entrypoint.sh`.

## Установка

Проект строго следует **Clean Architecture**:

- **Domain**: Сущности и бизнес-правила (не зависят от фреймворков).
- **Application**: Use-cases и интерфейсы взаимодействия с инфраструктурой.
- **Infrastructure**: Реализации БД (SQLAlchemy 2.0), Брокера (aio-pika), HTTP-клиентов.
- **Presentation**: FastAPI эндпоинты, Pydantic схемы.

### Схема обработки
1. **API** сохраняет `Payment` и `OutboxMessage` в одной транзакции.
2. **Outbox Publisher** надежно доставляет сообщение в RabbitMQ.
3. **Consumer** выполняет транзакцию через платежный шлюз (эмулятор) и отправляет вебхук.
4. При ошибке вебхука запускается цепочка **TTL-ретраев**.

## Надежность и Инварианты

- **Атомарность**: Платёж и событие всегда создаются вместе.
- **SKIP LOCKED**: Воркеры поддерживают горизонтальное масштабирование без конфликтов за одни и те же строки в БД.
- **Состояние попыток**: Количество попыток вебхука фиксируется в БД (`webhook_attempts`), что позволяет корректно продолжать ретраи даже после перезагрузки компонентов.
- **Безопасность БД**: Воркеры умеют ждать готовности базы данных, корректно обрабатывая временное отсутствие таблиц при накате миграций или очистке БД в тестах.

## Тестирование

Проект содержит развитую базу тестов:
- **Unit-тесты (35+)**: Покрывают доменную логику, мапперы и use-cases. Не требуют инфраструктуры.
- **Integration-тесты**: Проверяют весь цикл с реальным RabbitMQ и PostgreSQL. Покрывают DLQ, TTL-лестницу и Transactional Outbox.

Запуск всех тестов в Docker:
```bash
docker compose --profile test run --rm test pytest tests/test_integration/ -v
```

## Требования

- **Python 3.12+**
- **Docker Desktop**
- **uv** (рекомендуемый менеджер пакетов)

Подробное описание структуры проекта, API и конфигурации доступно в разделах [Структура проекта](#структура-проекта) и [Демонстрация](#демонстрация).

## Установка

### С Docker (рекомендуется)

Используйте `Makefile` для быстрого управления инфраструктурой:

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd payments_service

# 2. Создать .env из шаблона
cp .env.example .env

# 3. Запустить всё (БД, RabbitMQ, API и Воркеры)
# Миграции выполнятся автоматически при старте
make docker-up

# 4. Проверить статус
docker compose ps
```

Или используйте `docker compose` напрямую:
```bash
docker compose up -d
```

Ожидается:
- `app` — healthy (port 8000)
- `consumer` — running
- `outbox-publisher` — running
- `postgres` — healthy
- `rabbitmq` — healthy (ports 25672, 15672)
- `webhook-echo` — healthy (port 8080, тестовый сервер)

---

### Для локальной разработки (без Docker для API)

```bash
# 1. Установить зависимости
uv sync

# 2. Запустить инфраструктуру (PostgreSQL и RabbitMQ)
docker compose up -d postgres rabbitmq

# 3. Применить миграции
uv run alembic upgrade head

# 4. Запустить API локально
uv run uvicorn payments_service.main:app --reload --host 0.0.0.0 --port 8000

# В отдельных терминалах:
# Consumer
uv run python -m payments_service.workers.consumer

# Outbox Publisher
uv run python -m payments_service.workers.outbox_publisher
```

## Первые шаги

После установки проверьте работоспособность:

### 1. Health check

```bash
curl http://localhost:8000/api/health
# Ожидается: {"status":"ok"}
```

### 2. Создать первый платёж

```bash
curl -X POST http://localhost:8000/api/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: my-first-payment" \
  -d '{
    "amount": 100.50,
    "currency": "RUB",
    "description": "Мой первый тестовый платёж",
    "metadata": {"order_id": "123"},
    "webhook_url": "http://webhook-echo:8080/hook"
  }'
```

**Ожидаемый ответ:** `202 Accepted`
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-09-16T12:34:56.789Z"
}
```

### 3. Просмотр логов

Через несколько секунд проверьте обработку:

```bash
# Логи consumer (обработка шлюзом)
docker logs payments_service-consumer-1 --tail 20

# Логи вебхука (доставка уведомления)
docker logs payments_service-webhook-echo-1 --tail 20
```

### 4. Swagger UI

Откройте в браузере: http://localhost:8000/api/docs

Здесь можно:
- Посмотреть все endpoints
- Протестировать API через веб-интерфейс
- Изучить схемы запросов и ответов

## Архитектура

### Clean Architecture

Проект построен на чистой архитектуре с явным разделением зависимостей:

```
┌─────────────────────────────────────────────────────┐
│  Presentation (API, Controllers, Schemas)           │
│  ↓ зависит от Application                           │
├─────────────────────────────────────────────────────┤
│  Application (Use Cases, DTOs, Protocols)           │
│  ↓ зависит от Domain                                │
├─────────────────────────────────────────────────────┤
│  Domain (Entities, Value Objects, Exceptions)       │
│  ↑ не зависит ни от чего                            │
├─────────────────────────────────────────────────────┤
│  Infrastructure (DB, RabbitMQ, HTTP, Gateway)       │
│  ↑ реализует протоколы из Application               │
└─────────────────────────────────────────────────────┘
```

**Ключевые паттерны:**
- **Transactional Outbox**: вставка платежа и события в одной транзакции БД
- **Unit of Work**: управление транзакциями через контекстный менеджер
- **Repository**: инкапсуляция доступа к данным
- **Protocol (ABC)**: инверсия зависимостей через абстрактные протоколы
- **Dependency Injection**: через Dishka (провайдеры в `config/ioc/`)

### Компоненты системы

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────>│  PostgreSQL  │<────│  Consumer   │
│     API     │     │   + Outbox   │     │   Worker    │
└─────────────┘     └──────────────┘     └─────────────┘
                            │                     │
                            v                     v
                    ┌──────────────┐     ┌─────────────┐
                    │   Outbox     │     │   Payment   │
                    │  Publisher   │     │   Gateway   │
                    └──────────────┘     │  (Emulator) │
                            │             └─────────────┘
                            v                     │
                    ┌──────────────┐             v
                    │   RabbitMQ   │     ┌─────────────┐
                    │  + Retry     │     │   Webhook   │
                    │    Queues    │     │   Sender    │
                    └──────────────┘     └─────────────┘
```

### Три процесса

1. **API** (`main.py`, порт 8000):
   - Принимает `POST /api/payments` с заголовками `X-API-Key` и `Idempotency-Key`
   - Валидирует API-ключ через `hmac.compare_digest` (защита от timing attacks)
   - Вычисляет `request_hash` от канонизированного JSON (детерминированная идемпотентность)
   - Создаёт запись `Payment` и событие `OutboxMessage` **в одной транзакции**
   - Возвращает `202 Accepted` с `payment_id` немедленно

2. **Outbox Publisher** (`workers/outbox_publisher.py`):
   - Опрашивает таблицу `outbox` каждые 500ms
   - Забирает пачку событий с `FOR UPDATE SKIP LOCKED` (защита от параллельной обработки)
   - Публикует в RabbitMQ с **publisher confirms** (гарантия доставки)
   - Отмечает событие опубликованным **только после подтверждения брокера**
   - При ошибке: вычисляет экспоненциальную задержку и переносит `next_attempt_at`

3. **Consumer** (`workers/consumer.py`):
   - Читает события из очереди `payments.new`
   - Забирает платёж с `SELECT FOR UPDATE` (защита от дубликатов)
   - Проверяет идемпотентность через `webhook_delivered_at`
   - Если статус `pending`: вызывает эмулятор шлюза, меняет статус на `succeeded`/`failed`
   - Отправляет вебхук клиенту с `X-Request-ID` (correlation ID)
   - При ошибке доставки вебхука: инкремент `x-attempt`, публикация в `retry.{1,2,3}` очередь
   - После 3 попыток: публикация в DLX (`payments.dlq`)

### Топология RabbitMQ

```
payments (exchange, direct)
    │
    └─> payments.new (queue)
            │ x-dead-letter-exchange: payments.dlx
            │
            └─> Consumer читает сообщения

payments.retry (exchange, direct)
    │
    ├─> payments.retry.1 (queue, TTL=5s, без консьюмера)
    │       │ x-dead-letter-exchange: payments
    │       └─> после TTL → payments.new
    │
    ├─> payments.retry.2 (queue, TTL=10s, без консьюмера)
    │       │ x-dead-letter-exchange: payments
    │       └─> после TTL → payments.new
    │
    └─> payments.retry.3 (queue, TTL=20s, без консьюмера)
            │ x-dead-letter-exchange: payments
            └─> после TTL → payments.new

payments.dlx (exchange, direct)
    │
    └─> payments.dlq (queue)
            └─> финальное место для неудавшихся сообщений
```

**Важно:** TTL задаётся на очереди (`x-message-ttl`), а не на сообщении, чтобы избежать head-of-line blocking.

### Потоки данных

**Создание платежа:**
```
Client → POST /payments → API → [Transaction: Payment + OutboxMessage] → DB
                          ↓
                    202 Accepted
```

**Публикация события:**
```
OutboxPublisher → FOR UPDATE SKIP LOCKED → Outbox events → RabbitMQ publish
                                                            ↓ (confirm)
                                            mark_published() → DB
```

**Обработка платежа:**
```
Consumer → payments.new → Payment Gateway → Update Payment status → DB
                                          ↓
                              Webhook Sender → Client's webhook_url
                                          ↓ (error)
                              retry.1 → retry.2 → retry.3 → DLQ
```

## Критичные инварианты

Эти правила ломаются тихо (не видны в тестах), проявляются только при падении процесса.

### 1. Одна транзакция для платежа и события

Вставка `Payment` и `OutboxMessage` **обязаны** происходить в одной транзакции. Два коммита создают окно, где платёж есть, события нет, вебхук не придёт никогда.

**Проверочный запрос** (должен давать `0` в любой момент):
```sql
SELECT count(*) FROM payments p
LEFT JOIN outbox o ON o.payload::jsonb ->> 'payment_id' = p.id::text
WHERE o.id IS NULL;
```

**Реализация:** `CreatePaymentUseCase` открывает `async with self.uow` один раз, внутри вызывает `uow.payments.add()` и `uow.outbox.add()`. Коммит происходит в `__aexit__`.

### 2. Порядок публикации событий

**КРИТИЧНО:** сначала `producer.publish()` с publisher confirms, затем `outbox.mark_published()`. Обратный порядок даёт тихую потерю событий.

Это осознанный **at-least-once**:
- Дубликат события: consumer проверяет `webhook_delivered_at`, игнорирует повторную обработку
- Потеря события: невосполнима, вебхук не будет доставлен

### 3. Идемпотентность

- **API:** повторные запросы с одинаковым `Idempotency-Key` и `request_hash` возвращают существующий платёж. Разные `request_hash` с тем же ключом → `409 Conflict`.
- **Consumer:** проверяет `webhook_delivered_at` (если `not None` — выход), затем `status` (если финальный — пропуск шлюза, только вебхук).

### 4. Атомарные обновления и блокировки

- **Outbox publisher:** `fetch_pending()` использует `FOR UPDATE SKIP LOCKED` для защиты от параллельной обработки одного события несколькими экземплярами publisher.
- **Consumer:** использует атомарные обновления статуса в БД (`UPDATE ... WHERE status = 'pending'`) для защиты от гонок при параллельной обработке дубликатов сообщений. Вызов внешнего шлюза вынесен за пределы транзакции.

### 5. Сессия БД в Scope.REQUEST

Все зависимости (`AsyncSession`, `UnitOfWork`, репозитории) зарегистрированы в `Scope.REQUEST`. Одна сессия на запрос API или на одно сообщение в consumer. Использование `Scope.APP` сделало бы сессию общей на все запросы — нарушение изоляции.

### 6. flush() в add()

`PaymentRepositorySQLAlchemy.add()` вызывает `session.flush()` сразу после `session.add(model)`, чтобы `IntegrityError` (конфликт `idempotency_key`) всплыла **здесь**, а не в `__aexit__` UoW, где её перехватить адресно нельзя.

### 7. Перехват конфликта вне UoW

После провалившегося `flush()` сессия непригодна. Следующий запрос даст `PendingRollbackError`. Поэтому `IdempotencyKeyConflictError` ловится **снаружи** блока `async with uow`.

### 8. Никакого SELECT перед INSERT

«SELECT по ключу, потом INSERT» создаёт race condition. Между ними пролезает параллельный запрос. Защита — уникальный индекс плюс обработка конфликта.

### 9. Неуспешный платёж — не повод для retry

Это бизнес-результат (`status=failed`) и финальное состояние. Повторяются только технические сбои доставки вебхука (таймаут, сетевая ошибка, ответ не 2xx). Вебхук уходит и для успешного, и для неуспешного платежа.

## API Reference

### Документация

- **Swagger UI:** http://localhost:8000/api/docs
- **ReDoc:** http://localhost:8000/api/redoc
- **OpenAPI JSON:** http://localhost:8000/api/openapi.json

### Endpoints

#### POST /api/payments

Создать новый платёж. Возвращает `202 Accepted` немедленно.

**Headers:**
- `X-API-Key` (обязательный): API ключ для аутентификации
- `Idempotency-Key` (обязательный): Уникальный ключ идемпотентности

**Request Body:**
```json
{
  "amount": 100.50,
  "currency": "RUB",
  "description": "Оплата заказа #123",
  "metadata": {
    "order_id": "123",
    "user_id": "456"
  },
  "webhook_url": "http://webhook-echo:8080/hook"
}
```

**Validation:**
- `amount` > 0, максимум 2 знака после запятой
- `currency` ∈ {RUB, USD, EUR}
- `webhook_url` использует схему `http` или `https`

**Response: 202 Accepted**
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-09-16T12:34:56.789Z"
}
```

**Response: 409 Conflict** (повторный запрос с тем же `Idempotency-Key` но другим телом)
```json
{
  "detail": "Idempotency key conflict: different request body for key 'test-001'"
}
```

#### GET /api/payments/{payment_id}

Получить информацию о платеже.

**Headers:**
- `X-API-Key` (обязательный)

**Response: 200 OK**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": 100.50,
  "currency": "RUB",
  "description": "Оплата заказа #123",
  "payment_metadata": {"order_id": "123", "user_id": "456"},
  "status": "succeeded",
  "idempotency_key": "test-001",
  "request_hash": "a1b2c3d4...",
  "webhook_url": "http://webhook-echo:8080/hook",
  "created_at": "2026-09-16T12:34:56.789Z",
  "processed_at": "2026-09-16T12:35:01.234Z",
  "webhook_delivered_at": "2026-09-16T12:35:02.567Z",
  "webhook_attempts": 1,
  "webhook_last_error": null
}
```

**Response: 404 Not Found**
```json
{
  "detail": "Payment not found"
}
```

#### GET /api/health

Проверка доступности сервиса. Не требует аутентификации.

**Response: 200 OK**
```json
{
  "status": "ok"
}
```

## Примеры использования

### Создание платежа

```bash
curl -X POST http://localhost:8000/api/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: order-12345" \
  -d '{
    "amount": 250.75,
    "currency": "RUB",
    "description": "Оплата заказа #12345",
    "metadata": {"order_id": "12345", "user_id": "789"},
    "webhook_url": "http://webhook-echo:8080/hook"
  }'
```

### Получение статуса платежа

```bash
# Используйте payment_id из ответа выше
curl http://localhost:8000/api/payments/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: test-api-key-12345"
```

### Проверка идемпотентности

Повторный запрос с тем же `Idempotency-Key` и телом вернёт существующий платёж:

```bash
# Первый запрос
curl -X POST http://localhost:8000/api/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: idempotent-test-001" \
  -d '{"amount": 100.00, "currency": "RUB", "description": "Test", "metadata": {}, "webhook_url": "http://webhook-echo:8080/hook"}'

# Повторный запрос (тот же ключ, то же тело) - вернёт ТОТ ЖЕ payment_id
curl -X POST http://localhost:8000/api/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: idempotent-test-001" \
  -d '{"amount": 100.00, "currency": "RUB", "description": "Test", "metadata": {}, "webhook_url": "http://webhook-echo:8080/hook"}'
```

### Конфликт идемпотентности

Повторный запрос с тем же ключом, но другим телом вернёт `409 Conflict`:

```bash
curl -X POST http://localhost:8000/api/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: idempotent-test-001" \
  -d '{"amount": 200.00, "currency": "USD", "description": "Different", "metadata": {}, "webhook_url": "http://webhook-echo:8080/hook"}'
# Ожидается: 409 Conflict
```

## Тестирование

### Unit-тесты

Проект содержит **28 unit-тестов** с моками. Docker не требуется.

```bash
# Запустить все unit-тесты
uv run pytest -m unit -v

# Только тесты домена (14 тестов)
uv run pytest tests/test_domain/ -v

# Только тесты use-cases (7 тестов)
uv run pytest tests/test_application/ -v

# Только тесты API (7 тестов)
uv run pytest tests/test_presentation/ -v
```

**Покрытие тестами:**
- Доменная логика: 14 тестов (инварианты, переходы состояний)
- Use cases: 7 тестов (создание, обработка платежа, идемпотентность)
- API endpoints: 7 тестов (создание, получение, ошибки, health check)

### Все тесты (последовательно)

```bash
make test-all
```
Данная команда запустит модульные тесты локально, а затем интеграционные тесты в Docker.

### Coverage

```bash
uv run pytest --cov=payments_service --cov-report=html
```

Отчёт будет доступен в `htmlcov/index.html`.

### Make команды

```bash
make test-unit               # Только unit-тесты (локально)
make test-integration        # Integration тесты (требует работающей БД и RabbitMQ)
make test-integration-docker # Integration тесты в изолированном Docker-окружении
make test-all                # Все тесты последовательно (unit + integration-docker)
make check                   # Ruff + Mypy + unit-тесты
```

### Integration тесты

Интеграционные тесты проверяют работу системы с реальной инфраструктурой:
- PostgreSQL (реальная БД, не in-memory)
- RabbitMQ (реальные очереди и обмены)
- Retry механизм с TTL-лестницей
- Dead Letter Queue (DLQ)
- Transactional Outbox pattern

**Требования:**

```bash
# Запустить PostgreSQL и RabbitMQ
docker compose up -d postgres rabbitmq

# Дождаться готовности
docker compose ps
```

**Запуск:**

```bash
# Все integration тесты
make test-integration

# Или напрямую
uv run pytest -m integration -v

# Конкретный тест
uv run pytest tests/test_integration/test_dlq_and_retry.py::test_outbox_mechanism -v

# Через Docker (рекомендуется)
docker compose --profile test run --rm test pytest tests/test_integration/ -v
```

**Что покрывают (5 тестов):**

1. `test_retry_mechanism_with_ttl_ladder` - TTL-лестница retry.1→retry.2→retry.3→DLQ (⚠️ ~40 сек)
2. `test_dlq_receives_message_after_retries` - проверка DLQ headers после 3 попыток
3. `test_successful_delivery_after_retry` - успешная доставка webhook на 3-й попытке
4. `test_outbox_mechanism` - Transactional Outbox: fetch/publish/mark
5. `test_end_to_end_with_dlq` - полный flow: payment → outbox → retry → DLQ

## Стандарты качества кода

### Линтер (ruff)

```bash
# Проверка
uv run ruff check src/

# Автофикс
uv run ruff check src/ --fix

# Форматирование
uv run ruff format src/ tests/
```

**Ключевые правила:**
- **G004**: никаких f-строк в логировании (только `logger.info("msg %s", var)`)
- **D200, D205, D212**: докстринги по Google Style
- **B008**: FastAPI параметры через `Annotated`, не через defaults
- **ARG001**: неиспользуемые аргументы с `_` префиксом
- Длина строки: 88 символов
- Двойные кавычки
- Запрет относительных импортов

### Проверка типов (mypy)

```bash
uv run mypy src/
```

Проект использует **strict mode**:
- `disallow_untyped_defs = true`
- `disallow_any_unimported = true`
- `warn_return_any = true`
- `warn_unused_ignores = true`

### Архитектурные границы (import-linter)

```bash
uv run lint-imports
```

Проверяет, что:
- Domain не импортирует Application, Infrastructure, Presentation
- Application не импортирует Infrastructure, Presentation
- Infrastructure не импортирует Presentation

## Конфигурация

Все настройки задаются через переменные окружения. См. `.env.example` для полного списка с описанием.

### Основные параметры

| Переменная | Описание | Дефолт |
|------------|----------|--------|
| `ENVIRONMENT` | Окружение (dev/testing/production) | `dev` |
| `DEBUG` | Режим отладки (true/false) | `false` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `API_KEY` | API ключ для аутентификации | `test-api-key-12345` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `BROKER_URL` | RabbitMQ AMQP URL | `amqp://guest:guest@...` |

### Параметры платёжного шлюза (эмулятор)

| Переменная | Описание | Дефолт |
|------------|----------|--------|
| `GATEWAY_SUCCESS_RATE` | Вероятность успеха платежа (0.0-1.0) | `0.8` |
| `GATEWAY_MIN_DELAY_SECONDS` | Минимальная задержка ответа | `0.1` |
| `GATEWAY_MAX_DELAY_SECONDS` | Максимальная задержка ответа | `0.5` |

**Примеры:**
- `GATEWAY_SUCCESS_RATE=1.0` — все платежи успешны (тестирование happy path)
- `GATEWAY_SUCCESS_RATE=0.0` — все платежи failed (тестирование отклонённых платежей)

### Параметры retry

| Переменная | Описание | Дефолт |
|------------|----------|--------|
| `RETRY_TTL_LEVEL_1_MS` | Задержка 1-го retry вебхука | `5000` (5s) |
| `RETRY_TTL_LEVEL_2_MS` | Задержка 2-го retry вебхука | `10000` (10s) |
| `RETRY_TTL_LEVEL_3_MS` | Задержка 3-го retry вебхука | `20000` (20s) |

После 3 неудач сообщение переходит в DLQ.

### Параметры вебхуков

| Переменная | Описание | Дефолт |
|------------|----------|--------|
| `WEBHOOK_TIMEOUT_SECONDS` | Таймаут HTTP-запроса к webhook URL | `5.0` |
| `WEBHOOK_MAX_RETRIES` | Максимум попыток доставки | `3` |

## Миграции БД

Миграции в Docker-окружении применяются **автоматически** при старте контейнеров через `scripts/entrypoint.sh`.

### Ручное управление

Если необходимо управлять миграциями вручную (например, при локальной разработке):

```bash
uv run alembic revision --autogenerate -m "Add new column"
```

### Откат последней миграции

```bash
uv run alembic downgrade -1
```

### История миграций

```bash
uv run alembic history
```

### Проверка состояния

```bash
uv run alembic current
```

**Примечание:** сервис `migrate` в `docker-compose.yml` находится за профилем. Обычный `docker compose up` миграции не применяет.

## Мониторинг и логи

### Логи сервисов

Все сервисы используют structured logging (JSON) через `structlog`:

```bash
# API
docker logs payments_service-app-1 --tail 50

# Consumer
docker logs payments_service-consumer-1 --tail 50

# Outbox Publisher
docker logs payments_service-outbox-publisher-1 --tail 50

# Webhook Echo (тестовый сервер)
docker logs payments_service-webhook-echo-1 --tail 50

# Все сервисы сразу
make logs
```

Логи содержат `trace_id` (correlation ID) для сквозного трейсинга запросов.

### RabbitMQ Management UI

Web-интерфейс: http://localhost:15672

- **Username:** `guest`
- **Password:** `guest`

В UI можно:
- Посмотреть очереди (`payments.new`, `payments.retry.{1,2,3}`, `payments.dlq`)
- Проверить количество сообщений
- Вручную переместить сообщения из DLQ
- Отследить rate публикации и консьюмирования

### База данных

Подключение к PostgreSQL:
```bash
docker exec -it payments_service-postgres-1 psql -U payments -d payments
```

Полезные запросы:
```sql
-- Все платежи
SELECT id, status, amount, webhook_delivered_at FROM payments
ORDER BY created_at DESC
LIMIT 10;

-- События в outbox
SELECT id, published, next_attempt_at, attempts_count
FROM outbox
WHERE NOT published
ORDER BY next_attempt_at;

-- Проверка критичного инварианта (должен давать 0)
SELECT count(*) FROM payments p
LEFT JOIN outbox o ON o.payload::jsonb ->> 'payment_id' = p.id::text
WHERE o.id IS NULL;
```

### Мониторинг процессов

```bash
# Статус всех контейнеров
docker compose ps

# Использование ресурсов
docker stats

# События Docker
docker compose events
```

## Отладка и troubleshooting

### Частые проблемы

**Проблема:** `make: command not found` на Windows

**Решение:** Используйте команды вручную из [DEMO.md](./DEMO.md) или установите `make` через WSL2.

---

**Проблема:** Порт 5432 уже занят

**Решение:** В `docker-compose.yml` PostgreSQL использует порт `5433:5432`. Проверьте, что порт 5433 свободен.

---

**Проблема:** Контейнеры `consumer` и `outbox-publisher` показывают `unhealthy`

**Решение:** Это нормально — у них нет HTTP endpoint для healthcheck. Проверьте логи:
```bash
docker logs payments_service-consumer-1
docker logs payments_service-outbox-publisher-1
```

Если видите сообщения о подключении к RabbitMQ — всё работает корректно.

---

**Проблема:** Вебхуки не доставляются

**Диагностика:**
1. Проверьте логи consumer: `docker logs payments_service-consumer-1 --tail 50`
2. Проверьте очередь DLQ в RabbitMQ UI: http://localhost:15672
3. Убедитесь, что `webhook-echo` запущен: `docker compose ps`
4. Проверьте БД:
```sql
SELECT id, webhook_attempts, webhook_last_error
FROM payments
WHERE webhook_delivered_at IS NULL;
```

---

**Проблема:** Миграции не применились

**Решение:** В текущей версии миграции применяются автоматически через `entrypoint.sh`. Проверьте логи: `docker logs payments_service-app-1`. Если вы запускаете БД локально без Docker, используйте `uv run alembic upgrade head`.

### Windows-специфичные решения

**CRLF в shell-скриптах:**

Если видите ошибку `$'\r': command not found`:
```bash
# Проверьте .gitattributes
cat .gitattributes | grep "*.sh"

# Должно быть: *.sh text eol=lf
```

**Fallback для signal handlers:**

На Windows `loop.add_signal_handler()` не поддерживается. Воркеры используют `signal.signal()` автоматически. Проверьте логи — должно быть сообщение: `"signal.SIGTERM registered via signal.signal()"`

### Режим отладки

Включите DEBUG режим для подробных логов:

```bash
# В .env
DEBUG=true
LOG_LEVEL=DEBUG

# Перезапустите сервисы
docker compose restart
```

В DEBUG режиме логируются:
- Все SQL запросы
- Полные тела запросов/ответов
- Детали работы RabbitMQ consumer

**Не используйте DEBUG в production!**

## Makefile

Проект включает `Makefile` с удобными командами:

```bash
make help              # Показать список доступных команд
make install           # Установить зависимости (uv sync)
make check             # Запустить все проверки (ruff, mypy, unit tests)
make format            # Автоформатирование (ruff format)
make migrate           # Применить миграции БД
make test-unit         # Юнит-тесты (28 тестов)
make test-all          # Все тесты
make docker-up         # Запустить инфраструктуру (postgres, rabbitmq)
make docker-down       # Остановить инфраструктуру
make clean             # Очистить кеш и артефакты
make demo              # Полная демонстрация сервиса (альтернатива: docker compose up -d)
make logs              # Показать логи всех сервисов
```

**Для Windows без make:** используйте `docker compose up -d`. Полный сценарий см. в разделе [Демонстрация](#демонстрация).

## Структура проекта

<details>
<summary>Посмотреть детальную структуру проекта</summary>

### Корень проекта
```
payments_service/
├── src/payments_service/
│   ├── domain/                      # Доменная логика
│   │   ├── entities/payment.py      # Сущность Payment
│   │   ├── value_objects/           # Currency, PaymentStatus
│   │   └── exceptions.py            # Доменные исключения
│   │
│   ├── application/                 # Слой приложения
│   │   ├── use_cases/               # CreatePayment, ProcessPayment, GetPayment
│   │   ├── interfaces/              # Протоколы (Gateway, Repository, UoW, Webhook)
│   │   ├── dtos/payment.py          # PaymentDTO
│   │   └── exceptions.py            # Исключения слоя приложения
│   │
│   ├── infrastructures/             # Инфраструктура
│   │   ├── db/                      # SQLAlchemy (models, repositories, UoW, migrations)
│   │   ├── broker/aio_pika/         # Слой работы с RabbitMQ
│   │   ├── outbox/                  # Транзакционный outbox
│   │   ├── context/                 # Контекст выполнения (Correlation ID)
│   │   ├── gateway/fake.py          # FakePaymentGateway (эмулятор)
│   │   └── http/webhook.py          # HttpWebhookSender (httpx)
│   │
│   ├── presentation/api/rest/       # FastAPI (controllers, schemas, middlewares)
│   ├── workers/                     # Consumer, OutboxPublisher
│   ├── config/                      # Settings, Logging, DI (Dishka)
│   └── main.py                      # FastAPI app, точка входа
│
├── tests/                           # Unit и интеграционные тесты
├── scripts/                         # Shell-скрипты для Docker
├── tools/                           # Вспомогательные инструменты (webhook_echo.py)
├── .env.example                     # Шаблон переменных окружения
├── pyproject.toml                   # Конфигурация проекта
├── uv.lock                          # Lockfile
├── Dockerfile                       # Multi-stage build
├── docker-compose.yml               # Compose-сервисы
├── alembic.ini                      # Конфигурация Alembic
└── Makefile                         # Команды автоматизации
```

### Где искать что

| Что ищешь | Где смотреть |
|---|---|
| Бизнес-правила платежа | `domain/entities/payment.py` |
| API-эндпоинты | `presentation/api/rest/v1/controllers/payment_controller.py` |
| Логика создания платежа | `application/use_cases/create_payment.py` |
| SQL-модель | `infrastructures/db/models/payment.py` |
| RabbitMQ топология | `infrastructures/broker/topology.py` |
| Миграции БД | `infrastructures/db/migrations/versions/` |
| DI-конфигурация | `config/ioc/providers.py` |
| Переменные окружения | `.env.example` |
| Docker-образы | `Dockerfile` |
| Compose-сервисы | `docker-compose.yml` |

</details>

## Известные особенности

### Windows

- Git на Windows не сохраняет executable bit — shell-скрипты вызываются через `bash /app/scripts/...` в Dockerfile
- Файлы `.sh` должны быть в LF, не CRLF (контролируется `.gitattributes`)
- `loop.add_signal_handler()` не поддерживается на Windows — воркеры используют `signal.signal()` как fallback

### Healthchecks

Воркеры (`consumer`, `outbox-publisher`) не имеют HTTP-endpoint, поэтому Docker Compose показывает их как `unhealthy` — это нормально. Проверяйте логи:
```bash
docker logs payments_service-consumer-1 --tail 20
docker logs payments_service-outbox-publisher-1 --tail 20
```

### PostgreSQL порт

В `docker-compose.yml` PostgreSQL использует порт `5433` вместо стандартного `5432` (часто занят локальной установкой PostgreSQL).

## Демонстрация

<details>
<summary>Посмотреть полный сценарий демонстрации</summary>

### Запуск вручную

1. **Запуск инфраструктуры:**
   ```bash
   docker compose up -d
   ```

2. **Создание успешного платежа:**
   ```bash
   curl -X POST http://localhost:8000/api/payments \
     -H "Content-Type: application/json" \
     -H "X-API-Key: test-api-key-12345" \
     -H "Idempotency-Key: demo-payment-001" \
     -d "{\"amount\": 100.50, \"currency\": \"RUB\", \"description\": \"Demo #1\", \"webhook_url\": \"http://webhook-echo:8080/hook\"}"
   ```

3. **Проверка идемпотентности (повтор того же запроса):**
   Должен вернуть тот же `payment_id`.

4. **Проверка результатов:**
   - Health check: `curl http://localhost:8000/api/health`
   - Логи вебхуков: `docker compose logs webhook-echo`

### Что демонстрирует проект
- **Асинхронная обработка**: API отвечает сразу, шлюз вызывается в воркере.
- **Transactional Outbox**: Гарантированная публикация событий.
- **Retry & DLQ**: Автоматические повторы вебхуков через RabbitMQ TTL queues.
- **Идемпотентность**: Защита от дублей на всех уровнях.

</details>
