# Payments Service

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-4.0-orange.svg)
![Docker](https://img.shields.io/badge/Docker-required-blue.svg)

Микросервис асинхронной обработки платежей с гарантиями доставки событий и идемпотентностью.

## О проекте

**Payments Service** — тестовое задание, демонстрирующее микросервис обработки платежей на Clean Architecture. Ключевые возможности:

- **Асинхронная обработка**: API отвечает `202 Accepted` немедленно, обработка в фоновых процессах
- **At-least-once delivery**: события через Transactional Outbox Pattern с publisher confirms
- **Идемпотентность**: безопасные повторные запросы с `Idempotency-Key`
- **Два механизма retry**: outbox с экспоненциальной задержкой + TTL-лестница RabbitMQ для вебхуков
- **Эмулятор платёжного шлюза**: настраиваемый success rate и задержки

## Quick Start

### Вариант 1: make demo (Linux/macOS/WSL)

Если установлен `make`:

```bash
make demo
```

Эта команда автоматически:
1. Запустит PostgreSQL и RabbitMQ
2. Применит миграции БД
3. Запустит API, Consumer, Outbox Publisher
4. Создаст 4 тестовых платежа (успешный, идемпотентный повтор, конфликт, ещё успешный)
5. Покажет результаты обработки

См. подробности в [DEMO.md](./DEMO.md).

### Вариант 2: Вручную (Windows без make)

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd payments_service

# 2. Создать .env
cp .env.example .env

# 3. Запустить инфраструктуру
docker compose up -d postgres rabbitmq

# 4. Применить миграции
docker compose --profile migrate run --rm migrate

# 5. Запустить все сервисы
docker compose up -d

# 6. Проверить работоспособность
curl http://localhost:8000/api/health
```

**Ожидаемый результат:** `{"status":"ok"}`

**Что дальше:** см. раздел [Первые шаги](#первые-шаги) ниже.

## Требования

- **Python 3.12+**
- **Docker Desktop** (с WSL2 на Windows)
- **uv** — менеджер пакетов

Установка uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
irm https://astral.sh/uv/install.ps1 | iex        # Windows PowerShell
```

## Установка

### С Docker (рекомендуется)

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd payments_service

# 2. Создать .env из шаблона
cp .env.example .env
# Отредактируйте .env при необходимости (API_KEY, параметры шлюза)

# 3. Запустить инфраструктуру
docker compose up -d postgres rabbitmq

# Дождитесь healthy-статуса (5-10 секунд)
docker compose ps

# 4. Применить миграции
docker compose --profile migrate run --rm migrate

# 5. Запустить все сервисы
docker compose up -d

# Проверьте статус
docker compose ps
```

Ожидается:
- `app` — healthy (port 8000)
- `consumer` — running
- `outbox-publisher` — running
- `postgres` — healthy
- `rabbitmq` — healthy (ports 5672, 15672)
- `webhook-echo` — healthy (port 8080, тестовый сервер)

**Примечание:** воркеры (`consumer`, `outbox-publisher`) показывают `unhealthy` — это нормально, у них нет HTTP endpoint. Проверяйте логи: `docker logs payments_service-consumer-1`

### Для локальной разработки (без Docker для API)

```bash
# 1. Установить зависимости
uv sync

# 2. Запустить PostgreSQL и RabbitMQ в Docker
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

### 4. FOR UPDATE SKIP LOCKED

- **Outbox publisher:** `fetch_pending()` использует `FOR UPDATE SKIP LOCKED` для защиты от параллельной обработки одного события несколькими экземплярами publisher.
- **Consumer:** `get_for_update()` использует `FOR UPDATE` для защиты от дубликатов сообщений в RabbitMQ.

### 5. Сессия БД в Scope.REQUEST

Все зависимости (`AsyncSession`, `UnitOfWork`, репозитории) зарегистрированы в `Scope.REQUEST`. Одна сессия на запрос API или на одно сообщение в consumer. Использование `Scope.APP` сделало бы сессию общей на все запросы — нарушение изоляции.

### 6. flush() в add()

`PaymentRepositorySQLAlchemy.add()` вызывает `session.flush()` сразу после `session.add(model)`, чтобы `IntegrityError` (конфликт `idempotency_key`) всплыла **здесь**, а не в `__aexit__` UoW, где её перехватить адресно нельзя.

### 7. Перехват конфликта вне UoW

После провалившегося `flush()` сессия непригодна. Следующий запрос даст `PendingRollbackError`. Поэтому `IdempotencyKeyConflictError` ловится **снаружи** блока `async with uow`.

### 8. Никакого SELECT перед INSERT

«SELECT по ключу, потом INSERT» создаёт race condition. Между ними пролезает параллельный запрос. Защита — уникальный индекс плюс обработка конфликта.

### 9. Неуспешный платёж — не повод для retry

Это бизнес-результат (`status=FAILED`) и финальное состояние. Повторяются только технические сбои доставки вебхука (таймаут, сетевая ошибка, ответ не 2xx). Вебхук уходит и для успешного, и для неуспешного платежа.

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

### Все тесты

```bash
uv run pytest -v
```

### Coverage

```bash
uv run pytest --cov=payments_service --cov-report=html
```

Отчёт будет доступен в `htmlcov/index.html`.

### Make команды

```bash
make test-unit         # Только unit-тесты
make test-integration  # Integration тесты (требует docker compose up -d postgres rabbitmq)
make test-all          # Все тесты
make check             # Ruff + Mypy + unit-тесты
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

### Применение миграций

**В Docker:**
```bash
docker compose --profile migrate run --rm migrate
```

**Локально:**
```bash
uv run alembic upgrade head
```

### Создание новой миграции

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

**Проблема:** Миграции не применились автоматически

**Решение:** Миграции находятся за профилем `migrate`. Запустите вручную:
```bash
docker compose --profile migrate run --rm migrate
```

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

**⚠️ Не используйте DEBUG в production!**

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
make demo              # Полная демонстрация сервиса
make logs              # Показать логи всех сервисов
```

**Для Windows без make:** см. [DEMO.md](./DEMO.md) для запуска команд вручную.

## Структура проекта

```
payments_service/
├── src/payments_service/
│   ├── domain/                      # Доменная логика
│   │   ├── entities/payment.py      # Сущность Payment (mutable dataclass)
│   │   ├── value_objects/           # Currency, PaymentStatus (Enums)
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
│   │   ├── broker/aio_pika/         # Vendor: FastStream 0.7.5 (Apache-2.0)
│   │   ├── outbox/                  # Vendor: faststream-outbox (MIT)
│   │   ├── context/                 # Vendor: FastStream 0.7.5 (Apache-2.0)
│   │   ├── gateway/fake.py          # FakePaymentGateway (эмулятор)
│   │   └── http/webhook.py          # HttpWebhookSender (httpx)
│   │
│   ├── presentation/api/rest/       # FastAPI (controllers, schemas, middlewares)
│   ├── workers/                     # Consumer, OutboxPublisher
│   ├── config/                      # Settings, Logging, DI (Dishka)
│   └── main.py                      # FastAPI app, точка входа
│
├── tests/                           # 28 unit-тестов с моками
│   ├── test_domain/                 # 14 тестов доменной логики
│   ├── test_application/            # 7 тестов use-cases
│   └── test_presentation/           # 7 тестов API
│
├── scripts/                         # Shell-скрипты для Docker
├── .env.example                     # Шаблон переменных окружения
├── pyproject.toml                   # Конфигурация проекта (uv, ruff, mypy)
├── uv.lock                          # Lockfile (коммитится!)
├── Dockerfile                       # Multi-stage build
├── docker-compose.yml               # 5 сервисов
├── alembic.ini                      # Конфигурация Alembic
├── Makefile                         # 13 команд
├── DEMO.md                          # Пошаговая демонстрация
├── PROJECT_STRUCTURE.md             # Детальная структура (детали вырезанного кода)
└── README.md                        # Этот файл
```

Детальное описание каждого модуля: [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)

## Вырезанный код из библиотек

Проект включает 3 vendor-пакета, вырезанных вручную из сторонних библиотек:

| Пакет | Источник | Лицензия | Что даёт |
|-------|----------|----------|----------|
| `broker/aio_pika/` | FastStream 0.7.5 | Apache-2.0 | Декларация топологии, продюсер с publisher confirms, consumer, политики ack |
| `outbox/` | faststream-outbox | MIT | Таблица outbox, `FOR UPDATE SKIP LOCKED`, стратегии повторов |
| `context/` | FastStream 0.7.5 | Apache-2.0 | ContextVars, фильтр для логов, correlation ID |

**ВАЖНО:** Файлы `NOTICE` и `README.md` внутри каждого пакета **удалять нельзя** — это условие лицензий.

**Что было изменено:**
- Удалены зависимости на FastStream-специфичные модули
- Убрана интеграция с Kafka, NATS, Redis
- Упрощена структура под нужды проекта
- Добавлена интеграция с correlation ID

**Детали модификаций:** см. `README.md` внутри каждого vendor-пакета.

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

Полный сценарий демонстрации с объяснением каждого шага: **[DEMO.md](./DEMO.md)**

Демо показывает:
- Асинхронную обработку платежей (API → Outbox → RabbitMQ → Consumer → Gateway → Webhook)
- Transactional Outbox Pattern (атомарность платеж + событие)
- Идемпотентность API (повторные запросы, конфликты ключей)
- At-least-once delivery с publisher confirms
- Retry mechanism для вебхуков (TTL-лестница: 5s → 10s → 20s → DLQ)
- Correlation ID для сквозного трейсинга

**Дополнительные сценарии:**
- Эмуляция отказа шлюза (`GATEWAY_SUCCESS_RATE=0.0`)
- Проверка DLQ после неудачных вебхуков
- Мониторинг через RabbitMQ Management UI
