# Структура проекта

## Корень проекта

```
payments_service/
├── README.md              — Полная документация (807 строк)
├── DEMO.md                — Пошаговая демонстрация работы (328 строк)
├── PROJECT_STRUCTURE.md   — Этот файл
├── pyproject.toml         — Зависимости и конфигурация всех инструментов
├── uv.lock                — Закоммиченный lockfile для uv sync --frozen
├── .env.example           — Шаблон переменных окружения
├── Dockerfile             — Multi-stage build (5 stages)
├── docker-compose.yml     — 5 сервисов: app, consumer, outbox, postgres, rabbitmq
├── Makefile               — 13 targets (install, check, test, docker, demo)
├── alembic.ini            — Настройки миграций
└── webhook_echo.py        — Тестовый вебхук-сервер для демо
```

## Исходный код: `src/payments_service/`

### Слой домена: `domain/`
Бизнес-логика, не зависит ни от чего.

```
domain/
├── entities/
│   └── payment.py         — Сущность Payment (mutable dataclass)
├── value_objects/
│   ├── currency.py        — Enum валют (RUB, USD, EUR)
│   └── payment_status.py  — Enum статусов (PENDING, SUCCEEDED, FAILED)
└── exceptions.py          — Доменные исключения (InvalidAmountError, InvalidPaymentTransitionError)
```

### Слой приложения: `application/`
Use-cases и интерфейсы (протоколы).

```
application/
├── dtos/
│   └── payment.py         — PaymentDTO (frozen dataclass для передачи данных)
├── exceptions.py          — Исключения слоя приложения (PaymentNotFoundError, WebhookDeliveryError)
├── interfaces/
│   ├── db_mapper.py       — Протокол маппинга Entity ↔ DB-модель
│   ├── gateway.py         — Протокол платёжного шлюза
│   ├── mappers.py         — Протокол маппинга DTO ↔ Entity
│   ├── repositories.py    — Протокол репозитория платежей
│   ├── uow.py             — Протокол Unit of Work
│   └── webhook.py         — Протокол отправки вебхуков
├── mappers.py             — Реализация маппинга DTO ↔ Entity
└── use_cases/
    ├── create_payment.py  — Use-case создания платежа (CreatePaymentCommand)
    ├── get_payment.py     — Use-case получения платежа по ID
    └── process_payment.py — Use-case обработки платежа (шлюз + вебхук)
```

### Слой инфраструктуры: `infrastructures/`

#### База данных: `infrastructures/db/`

```
db/
├── models/
│   ├── base.py            — DeclarativeBase для SQLAlchemy
│   └── payment.py         — Модель Payment (mapped_column, JSONB)
├── mappers/
│   └── payment.py         — Маппинг Entity ↔ DB-модель
├── repositories/
│   └── payment.py         — Репозиторий платежей (add, get_by_id, update)
├── migrations/
│   └── versions/
│       └── e38c5b05cf60_create_payments_and_outbox_tables.py
├── exceptions.py          — Исключения БД (DatabaseConnectionError)
├── session.py             — create_engine, get_session_factory
└── uow.py                 — UnitOfWork (commit/rollback транзакций)
```

#### Брокер сообщений: `infrastructures/broker/`

```
broker/
├── aio_pika/              — Вырезанный код из FastStream 0.7.5
│   ├── NOTICE             — Apache-2.0 лицензия FastStream
│   ├── README.md          — Карта модулей, отличия от оригинала
│   ├── schemas.py         — RabbitQueue, RabbitExchange (декларативное описание)
│   ├── channel.py         — ChannelManager (пул каналов)
│   ├── declarer.py        — RabbitDeclarer (идемпотентная декларация)
│   ├── message.py         — RabbitMessage (защита от двойного ack)
│   ├── ack.py             — AckPolicy (5 режимов подтверждения)
│   ├── parser.py          — build_message (persist=True по умолчанию)
│   ├── producer.py        — RabbitProducer (publisher confirms)
│   ├── consumer.py        — RabbitConsumer (declare → bind → consume)
│   └── connection.py      — RabbitConnection (connect_robust)
└── topology.py            — Топология RabbitMQ (PAYMENTS, DLX, RETRY-очереди)
```

#### Outbox: `infrastructures/outbox/`

```
outbox/
├── NOTICE                 — MIT лицензия faststream-outbox
├── README.md              — Обоснование FOR UPDATE SKIP LOCKED, два механизма ретраев
├── schema.py              — Таблица outbox_table (SQLAlchemy Table)
├── client.py              — OutboxClient (add, fetch_pending, mark_published)
└── retry.py               — ExponentialRetry (стратегия повторов)
```

#### Context (Correlation ID): `infrastructures/context/`

```
context/
├── NOTICE                 — Apache-2.0 лицензия FastStream
├── README.md              — bind() vs scope(), логирующий фильтр
├── repository.py          — ContextRepository (ContextVar на лету)
└── logging.py             — ExtendedFilter (проброс контекста в логи)
```

#### Платёжный шлюз: `infrastructures/gateway/`

```
gateway/
└── fake.py                — FakePaymentGateway (эмулятор с настраиваемым success_rate)
```

#### Вебхуки: `infrastructures/webhook/`

```
webhook/
└── sender.py              — WebhookSender (httpx, таймауты, ретраи)
```

### Слой представления: `presentation/`

#### REST API: `presentation/api/rest/`

```
rest/
├── error_handling.py      — Exception handlers (404, 409, 400)
├── middlewares.py         — TraceIDMiddleware (X-Request-ID)
└── v1/
    ├── controllers/
    │   └── payment_controller.py  — POST /payments, GET /payments/{id}, GET /health
    └── schemas/
        ├── requests.py    — CreatePaymentRequestSchema (Pydantic)
        └── responses.py   — PaymentResponseSchema, HealthResponseSchema
```

### Воркеры: `workers/`

```
workers/
├── consumer.py            — PaymentConsumer (обрабатывает payments.new)
└── outbox_publisher.py    — OutboxPublisher (публикует события из outbox)
```

### Конфигурация: `config/`

```
config/
├── settings.py            — Settings (Pydantic BaseSettings, читает .env)
├── api.py                 — APIConfig (API_KEY)
├── app.py                 — AppConfig (DEBUG, LOG_LEVEL)
├── broker.py              — BrokerConfig (BROKER_URL, retry TTL)
├── cors.py                — CORSConfig (CORS_ORIGINS)
├── database.py            — DatabaseConfig (DATABASE_URL)
├── gateway.py             — GatewayConfig (success_rate, delays)
├── webhook.py             — WebhookConfig (WEBHOOK_TIMEOUT)
├── logging.py             — setup_logging (structlog + stdlib)
└── ioc/
    ├── di.py              — get_providers (список провайдеров Dishka)
    └── providers.py       — Все DI-провайдеры (settings, db, broker, use-cases)
```

### Точка входа: `main.py`

```
main.py                    — FastAPI app, роутеры, middleware, lifespan
```

## Тесты: `tests/`

```
tests/
├── conftest.py              — Общие фикстуры (моки для unit-тестов)
├── faker.py                 — Faker wrapper
├── factories.py             — Polyfactory фабрики (Payment, PaymentDTO)
├── test_domain/
│   └── test_entities/
│       └── test_payment.py  — Тесты доменной логики (21 тест)
├── test_application/
│   └── test_use_cases/
│       ├── test_create_payment.py   — CreatePaymentUseCase (3 теста)
│       └── test_process_payment.py  — ProcessPaymentUseCase (4 теста)
└── test_presentation/
    └── test_payment_api.py  — API эндпоинты (7 тестов)
```

**Всего: 35 unit-тестов с моками. Docker не требуется.**

## Docker

```
Dockerfile                 — 5 stages:
                             • base: Python 3.12 + uv
                             • deps: uv sync --frozen --no-install-project
                             • production: uv sync --frozen --no-dev
                             • development: uv sync --frozen (с dev deps)
                             • testing: pytest + coverage
```

```
docker-compose.yml         — 5 сервисов:
                             • postgres:16-alpine (порт 5433)
                             • rabbitmq:4-management (порт 5672, 15672)
                             • app (FastAPI, порт 8000)
                             • consumer (PaymentConsumer)
                             • outbox (OutboxPublisher)
```

## Важные служебные файлы

```
.env.example               — Шаблон окружения
.gitattributes             — LF для shell-скриптов
.dockerignore              — Исключения для Docker build
alembic.ini                — Настройки Alembic
webhook_echo.py            — Тестовый сервер для демо
```

## Вырезанный код из сторонних библиотек

**3 пакета с лицензиями:**

| Пакет | Источник | Лицензия | Файлы |
|---|---|---|---|
| `broker/aio_pika/` | FastStream 0.7.5 | Apache-2.0 | NOTICE, README.md |
| `outbox/` | faststream-outbox | MIT | NOTICE, README.md |
| `context/` | FastStream 0.7.5 | Apache-2.0 | NOTICE, README.md |

**Критично:** Файлы `NOTICE` и `README.md` удалять нельзя — это условие лицензий.

## Статистика

```
95 Python файлов            5353 строки кода
79 зависимостей             uv.lock закоммичен
807 строк README.md         328 строк DEMO.md
13 Makefile targets         5 Docker stages
```

## Быстрый старт

```bash
# Установка зависимостей
uv sync

# Запуск проверок
uv run ruff check src/
uv run mypy src/
uv run pytest -m unit

# Запуск инфраструктуры
docker compose up -d postgres rabbitmq

# Миграции
uv run alembic upgrade head

# Запуск API
uv run uvicorn payments_service.main:app --reload

# Полная демонстрация
docker compose up --build
# В другом терминале:
python webhook_echo.py
# В третьем терминале:
# Следуй инструкциям из DEMO.md
```

## Где искать что

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
| Лицензии вырезанного кода | `*/NOTICE`, `*/README.md` в broker/, outbox/, context/ |
