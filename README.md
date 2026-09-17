# Payments Service

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-blue.svg)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-4.2-orange.svg)

## Оглавление
- [Описание](#описание)
- [Стек технологий](#стек-технологий)
- [Запуск](#запуск)
  - [Требования](#требования)
  - [Быстрый старт](#быстрый-старт)
  - [Управление через Makefile](#управление-через-makefile)
  - [Демонстрация сценария](#демонстрация-сценария)
  - [Локальный запуск без Docker](#локальный-запуск-без-docker)
- [Архитектура](#архитектура)
  - [Схема потоков данных](#схема-потоков-данных)
  - [Жизненный цикл и машина состояний](#жизненный-цикл-и-машина-состояний)
  - [Критичные инварианты](#критичные-инварианты)
  - [Транспортный слой](#транспортный-слой)
- [Справочник API](#справочник-api)
- [Конфигурация окружения (.env)](#конфигурация-окружения-env)
- [Тестирование](#тестирование)
- [Структура проекта](#структура-проекта)
- [Ограничения и особенности](#ограничения-и-особенности)
- [Диагностика и мониторинг](#диагностика-и-мониторинг)

---

## Описание
**Payments Service** — микросервис асинхронной обработки платежей, спроектированный по принципам Clean Architecture. Сервис обеспечивает надёжную доставку уведомлений клиентам (webhooks) с гарантией **at-least-once** и полной защитой от дубликатов на стороне потребителя (**идемпотентный consumer**).

### Ключевые проектные решения:
- **Два механизма повторов**: 
  1. *Transactional Outbox* — надёжная публикация событий в брокер без потерь.
  2. *Лестница TTL-очередей RabbitMQ* — отложенные повторные попытки (retry ladder) при временной недоступности клиентских webhook-серверов.
- **Гарантированная атомарность**: Сохранение платежа и регистрация Outbox-события выполняются в рамках единой транзакции БД через Unit of Work.
- **Двухуровневая идемпотентность**:
  1. *API-уровень*: Детерминированная проверка через заголовок `Idempotency-Key` и хэш тела запроса (предотвращает повторную инициализацию).
  2. *Бизнес-уровень*: Контроль состояния доставки и фиксация успешной обработки платежа.

---

## Стек технологий
- **Язык и фреймворк**: Python 3.12+, FastAPI, Pydantic V2
- **Архитектура и DI**: Clean Architecture, Dishka (IoC/DI контейнер)
- **База данных и ORM**: PostgreSQL, SQLAlchemy 2.0 (Async), Alembic, asyncpg
- **Брокер сообщений**: RabbitMQ, aio-pika (Publisher Confirms, Dead Letter Exchange, TTL Queues)
- **Качество кода и тесты**: uv, Ruff, Mypy (strict), Pytest (unit + integration в test-containers)

---

## Запуск

### Требования
- **Для запуска в контейнерах (основной способ)**:
  - Docker & Docker Compose (Docker Desktop / Docker Engine)
  - `make` (рекомендуется для удобства управления)
  *(Локальная установка Python не требуется)*
- **Для локальной разработки без Docker**:
  - Python 3.12+
  - Менеджер пакетов `uv`

---

### Быстрый старт

1. **Клонирование репозитория и переход в директорию**:
   ```bash
   git clone https://github.com/RansonDev/payment-service.git
   cd payments_service
   ```

2. **Создание конфигурационного файла**:
   ```bash
   cp .env.example .env
   ```

3. **Запуск всех сервисов**:
   ```bash
   # С использованием Makefile:
   make docker-up

   # Либо напрямую через Docker Compose:
   docker compose up -d
   ```

> **Важно**: Сервис станет доступен (статус `healthy`), как только запустятся база данных и брокер (обычно 10–20 секунд).

- **Документация Swagger UI**: [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)
- **Тестовый сервер вебхуков**: `docker compose logs webhook-echo -f`

---

### Управление через Makefile

В проекте настроен удобный `Makefile` для автоматизации повседневных задач:

| Команда | Описание |
| :--- | :--- |
| `make docker-up` | Запуск полного окружения (API, воркеры, PostgreSQL, RabbitMQ, Webhook-Echo) с миграциями |
| `make docker-down` | Остановка и удаление контейнеров |
| `make demo` | **Автоматическая демонстрация**: проверка healthcheck, создание платежа, проверка идемпотентности и логов |
| `make check` | Запуск линтеров (`ruff`, `mypy`) и модульных тестов |
| `make test-unit` | Запуск быстрых unit-тестов |
| `make test-integration` | Запуск интеграционных тестов локально |
| `make test-integration-docker` | Запуск интеграционных тестов в изолированном Docker-контейнере |
| `make test-all` | Полный цикл тестов (unit + integration-docker) |
| `make logs` | Просмотр логов всех сервисов в реальном времени |
| `make clean` | Очистка кэша (`__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`) |

---

### Демонстрация сценария

Вы можете запустить автоматический сценарий через `make demo` или выполнить шаги вручную:

1. **Проверка готовности сервиса**:
   ```bash
   curl http://127.0.0.1:8000/api/health
   ```
   *Ответ:* `{"status":"ok"}`

2. **Создание платежа**:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/payments \
     -H "Content-Type: application/json" \
     -H "X-API-Key: test-api-key-12345" \
     -H "Idempotency-Key: demo-unique-key-001" \
     -d '{
       "amount": 150.00,
       "currency": "RUB",
       "description": "Оплата заказа",
       "webhook_url": "http://webhook-echo:8080/hook"
     }'
   ```
   *Ответ:* `202 Accepted` c телом `{"payment_id": "<uuid>", "status": "pending"}`.

3. **Проверка идемпотентности**:
   - Повтор запроса с тем же `Idempotency-Key` вернет `200/202` с тем же `payment_id`.
   - Запрос с тем же `Idempotency-Key`, но измененным телом (например, другая сумма) вернет `409 Conflict`.

4. **Получение статуса платежа**:
   ```bash
   curl http://127.0.0.1:8000/api/payments/<payment_id>
   ```

5. **Проверка доставки вебхука**:
   ```bash
   docker compose logs webhook-echo -f
   ```

---

### Локальный запуск без Docker

Если требуется запускать компоненты сервиса локально в среде разработки:

```bash
# 1. Установка зависимостей проекта
uv sync

# 2. Запуск инфраструктурных сервисов (БД и брокер)
docker compose up -d postgres rabbitmq

# 3. Применение миграций базы данных
uv run alembic upgrade head

# 4. Запуск API-сервера
uv run uvicorn payments_service.presentation.api.main:app --reload --port 8000

# 5. В отдельных терминалах: запуск фоновых воркеров
uv run python -m payments_service.workers.outbox_publisher
uv run python -m payments_service.workers.consumer
```

---

## Архитектура

Проект строго следует принципам **Clean Architecture**:
- **Domain**: Сущности (`Payment`), Value Objects (`Money`, `PaymentStatus`), чистые бизнес-правила.
- **Application**: Сценарии использования (`Use Cases`), интерфейсы репозиториев и сервисов (Protocols/DTO).
- **Infrastructure**: Реализации адаптеров: PostgreSQL (SQLAlchemy 2.0), RabbitMQ (aio-pika), эмулятор платежного шлюза, HTTP-клиент вебхуков.
- **Presentation**: FastAPI роутеры, Pydantic-схемы, middlewares аутентификации и обработки ошибок.
- **Workers**: Изолированные фоновые процессы (`Consumer`, `OutboxPublisher`).

### Схема потоков данных

```mermaid
flowchart TD
    Client["Клиент (Client)"] -->|"POST /api/payments"| API["FastAPI Presentation Layer"]
    API --> UC["CreatePaymentUseCase"]
    
    subgraph UoW ["Unit of Work (Атомарная транзакция)"]
        UC --> PaymentInsert["1. Вставка Payment (PENDING)"]
        UC --> OutboxEvent["2. Запись Outbox Event"]
        PaymentInsert --> DB[("PostgreSQL DB")]
        OutboxEvent --> DB
    end

    OutboxWorker["Outbox Publisher Worker"] -.->|"FOR UPDATE SKIP LOCKED"| DB
    OutboxWorker -->|"Publisher Confirms"| Exchange{"RabbitMQ Exchange\n(payments.process)"}

    Exchange --> Consumer["Consumer Worker"]
    Consumer --> Gateway["Payment Gateway Emulator"]
    Consumer -->|"Update Payment (SUCCEEDED / FAILED)"| DB
    Consumer --> WebhookSender["Webhook Sender"]
    
    WebhookSender -->|"HTTP POST (2xx OK)"| ClientWebhook["Клиентский Webhook URL"]
    WebhookSender -.->|"Ошибка HTTP / Timeout"| RetryLadder["RabbitMQ Retry Ladder\n(retry.1: 5s ➔ retry.2: 10s ➔ retry.3: 20s)"]
    RetryLadder -.->|"Повтор обработки"| Consumer
    RetryLadder -.->|"Лимит попыток исчерпан"| DLQ[("RabbitMQ DLQ\n(payments.dlq)")]
```

### Жизненный цикл и машина состояний

#### 1. Жизненный цикл платежа
```mermaid
stateDiagram-v2
    [*] --> PENDING: Создание платежа через API
    PENDING --> PROCESSING: Взято в обработку Consumer
    PROCESSING --> SUCCEEDED: Успешный ответ шлюза
    PROCESSING --> FAILED: Ошибка авторизации / отказ шлюза
    SUCCEEDED --> [*]
    FAILED --> [*]
```

#### 2. Жизненный цикл доставки Webhook (Retry Ladder)
```mermaid
stateDiagram-v2
    [*] --> PENDING: Событие создано
    PENDING --> DELIVERED: HTTP 2xx (Успешно)
    PENDING --> RETRY_1: Сбой HTTP / Таймаут (Попытка 1)
    
    RETRY_1 --> DELIVERED: HTTP 2xx (Успешно)
    RETRY_1 --> RETRY_2: Сбой (Задержка 5 сек)
    
    RETRY_2 --> DELIVERED: HTTP 2xx (Успешно)
    RETRY_2 --> RETRY_3: Сбой (Задержка 10 сек)
    
    RETRY_3 --> DELIVERED: HTTP 2xx (Успешно)
    RETRY_3 --> DLQ_FAILED: Сбой (Задержка 20 сек, попытки исчерпаны)
    
    DELIVERED --> [*]
    DLQ_FAILED --> [*]
```

### Критичные инварианты
- **Атомарность Outbox**: Вставка записи о платеже и Outbox-события происходит строго в одной транзакции через Unit of Work.
- **Гарантия публикации**: Запись в Outbox помечается как `published` в БД только после получения подтверждения (ACK) от RabbitMQ.
- **Безопасность параллелизма воркеров**: Выборка событий через `FOR UPDATE SKIP LOCKED` позволяет горизонтально масштабировать `Outbox Publisher` без риска блокировок или дублирования.
- **Лестница повторов (Retry Ladder)**: При сбое доставки вебхука сообщение последовательно перемещается по очередям `retry.1` (5с), `retry.2` (10с), `retry.3` (20с) через механизм TTL и Dead Letter Exchange, а после исчерпания попыток отправляется в `payments.dlq`.

---

### Транспортный слой
Техническое задание предполагает использование FastStream для работы с RabbitMQ. В проекте применяется `aio-pika` напрямую. Основания для отклонения:

1. **Ограничения FastStream**: Фреймворк не реализует отложенную доставку и повторные попытки с настраиваемыми интервалами из коробки. Параметр `retry` у подписчика выполняет `nack(requeue=True)` без задержки и без сохранения счётчика попыток между перезапусками процесса, что не удовлетворяет требованию трёх попыток с экспоненциальной задержкой.
2. **Конфликт жизненного цикла**: Фреймворк задаёт собственную модель жизненного цикла приложения и внедрения зависимостей, что конфликтует с принятой в проекте схемой на основе **Dishka**.

#### Заимствованные компоненты
Из исходного кода FastStream 0.7.5 и `faststream-outbox` перенесены и адаптированы отдельные компоненты:

| Пакет | Источник | Содержание |
|---|---|---|
| `infrastructures/broker/aio_pika` | FastStream 0.7.5, Apache-2.0 | Декларация топологии с кешированием по хешу схемы. Продюсер с publisher confirms и passive-объявлением обменников. Политики подтверждения сообщений с защитой от повторного ack. |
| `infrastructures/outbox` | faststream-outbox, MIT | Выборка событий с `FOR UPDATE SKIP LOCKED`. Стратегии экспоненциальной задержки с джиттером и ограничением. |
| `infrastructures/context` | FastStream 0.7.5, Apache-2.0 | Хранилище контекста на `contextvars` и фильтр логирования для сквозного `trace_id`. |

*Существенное отклонение от оригинала*: в `infrastructures/outbox` модель аренды строки (`acquired_token` с истечением по TTL) заменена на транзакционную блокировку. В данном проекте публикация события выполняется за миллисекунды, транзакция удерживается на всё время операции, а освобождение блокировки при аварийном завершении процесса происходит автоматически на уровне СУБД.

#### Реализовано самостоятельно
Outbox-паттерн в связке с бизнес-транзакцией, лестница retry-очередей с dead-letter маршрутизацией и перевод сообщений в DLQ после исчерпания попыток реализованы в рамках проекта с нуля.

---

## Справочник API

Интерактивная документация (Swagger UI): [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)

### Эндпоинты

#### 1. `POST /api/payments` — Создание платежа
- **Заголовки**:
  - `X-API-Key: <string>` (Обязательный) — Ключ авторизации API.
  - `Idempotency-Key: <string>` (Обязательный) — Уникальный ключ идемпотентности операции.
- **Тело запроса**:
  ```json
  {
    "amount": 150.00,
    "currency": "RUB",
    "description": "Оплата заказа #1042",
    "webhook_url": "http://webhook-echo:8080/hook"
  }
  ```
- **Коды ответов**:
  - `202 Accepted` — Платеж принят в обработку:
    ```json
    {
      "payment_id": "8f3b147e-8557-4ba3-a006-25cf9a9d701e",
      "status": "pending",
      "message": "Payment accepted for processing"
    }
    ```
  - `401 Unauthorized` — Не передан или недействителен `X-API-Key`.
  - `409 Conflict` — Передан существующий `Idempotency-Key`, но тело запроса отличается от исходного.
  - `422 Unprocessable Entity` — Ошибка валидации входных данных.

#### 2. `GET /api/payments/{payment_id}` — Получение статуса платежа
- **Ответ (`200 OK`)**:
  ```json
  {
    "id": "8f3b147e-8557-4ba3-a006-25cf9a9d701e",
    "amount": 150.00,
    "currency": "RUB",
    "status": "succeeded",
    "description": "Оплата заказа #1042",
    "webhook_url": "http://webhook-echo:8080/hook",
    "webhook_delivery_status": "delivered",
    "webhook_attempts": 1,
    "created_at": "2026-09-17T12:00:00Z",
    "updated_at": "2026-09-17T12:00:03Z"
  }
  ```
- **Коды ответов**: `200 OK`, `404 Not Found`.

#### 3. `GET /api/health` — Проверка жизнеспособности сервиса
- **Ответ (`200 OK`)**:
  ```json
  {
    "status": "ok"
  }
  ```

---

## Конфигурация окружения (.env)

| Переменная | Описание | Значение по умолчанию |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Окружение приложения (`dev`, `production`, `test`) | `dev` |
| `LOG_LEVEL` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `DEBUG` |
| `DEBUG` | Режим отладки FastAPI | `true` |
| `API_KEY` | Мастер-ключ для заголовка `X-API-Key` | `test-api-key-12345` |
| `POSTGRES_USER` | Пользователь PostgreSQL | `payments` |
| `POSTGRES_PASSWORD` | Пароль пользователя PostgreSQL | `payments` |
| `POSTGRES_SERVER` | Хост PostgreSQL | `postgres` |
| `POSTGRES_PORT` | Порт PostgreSQL | `5432` |
| `POSTGRES_DB` | Имя базы данных | `payments` |
| `BROKER_URL` | AMQP URL подключения к RabbitMQ | `amqp://guest:guest@rabbitmq:5672/` |
| `BROKER_PREFETCH_COUNT`| Лимит неподтвержденных сообщений (prefetch) на воркер | `10` |
| `RETRY_TTL_LEVEL_1_MS` | Задержка 1-го уровня повтора доставки (мс) | `5000` (5 сек) |
| `RETRY_TTL_LEVEL_2_MS` | Задержка 2-го уровня повтора доставки (мс) | `10000` (10 сек) |
| `RETRY_TTL_LEVEL_3_MS` | Задержка 3-го уровня повтора доставки (мс) | `20000` (20 сек) |
| `GATEWAY_SUCCESS_RATE` | Вероятность успешного платежа в эмуляторе (`0.0` .. `1.0`) | `0.9` (90%) |
| `GATEWAY_MIN_DELAY_SECONDS` | Минимальная задержка ответа шлюза (сек) | `2.0` |
| `GATEWAY_MAX_DELAY_SECONDS` | Максимальная задержка ответа шлюза (сек) | `5.0` |
| `WEBHOOK_TIMEOUT_SECONDS` | Таймаут HTTP-запроса при отправке вебхука (сек) | `5.0` |
| `WEBHOOK_MAX_RETRIES` | Максимальное количество попыток отправки вебхука | `3` |

---

## Тестирование

1. **Unit-тесты** (доменная логика, сущности, use cases без внешних зависимостей):
   ```bash
   make test-unit
   # или напрямую: uv run pytest -m unit
   ```

2. **Интеграционные тесты** (проверка Outbox, взаимодействия с БД, очередей RabbitMQ и DLQ):
   ```bash
   # Запуск в изолированном Docker-окружении (рекомендуется):
   make test-integration-docker

   # Запуск локально (требуется предварительно запустить инфраструктуру):
   make test-integration
   ```

3. **Полный цикл тестирования**:
   ```bash
   make test-all
   ```

---

## Структура проекта

```text
payments_service/
├── src/payments_service/
│   ├── domain/              # Чистая бизнес-логика (Entities, Value Objects, исключения)
│   ├── application/         # Сценарии (Use Cases), интерфейсы (Protocols), DTOs
│   ├── infrastructures/     # Реализации адаптеров:
│   │   ├── db/              # PostgreSQL (SQLAlchemy models, repos, uow, migrations)
│   │   ├── broker/          # RabbitMQ (aio-pika topology, producer, publisher confirms)
│   │   ├── gateway/         # Эмулятор платежного шлюза
│   │   ├── http/            # Webhook HTTP Sender (aiohttp / httpx)
│   │   └── outbox/          # Outbox reader & publisher logic
│   ├── presentation/        # HTTP API (FastAPI routes, schemas, auth middleware)
│   ├── workers/             # Изолированные фоновые процессы (Consumer, OutboxPublisher)
│   └── config/              # Настройки (pydantic-settings), логирование, DI-контейнеры (Dishka)
├── tests/
│   ├── test_domain/         # Unit-тесты доменного слоя
│   ├── test_application/    # Unit-тесты сценариев
│   ├── test_infrastructure/ # Тесты адаптеров
│   └── test_integration/   # Интеграционные сценарии (PostgreSQL + RabbitMQ)
├── scripts/                 # Скрипты инициализации БД и окружения
├── docker-compose.yml       # Декларация полного сервисного стека
├── Dockerfile               # Multi-stage сборка сервиса
└── Makefile                 # Команды сборки, тестирования и запуска
```

---

## Ограничения и особенности
- **Outbox Publisher**: Лимит попыток публикации в брокер не ограничен (повторные попытки выполняются до успешной отправки); это обеспечивает гарантированную доставку событий даже при длительной недоступности брокера сообщений.
- **Безопасность**: Вебхуки отправляются без криптографической подписи (HMAC-SHA256); в производственной среде рекомендуется добавить подпись заголовков и фильтрацию IP-адресов.
- **Эмуляция шлюза**: Вместо интеграции с реальным банковским провайдером используется эмулятор с конфигурируемой вероятностью успеха (`GATEWAY_SUCCESS_RATE`) и случайной задержкой.

---

## Диагностика и мониторинг
- **Мониторинг RabbitMQ**: Web UI панели управления доступен по адресу [http://127.0.0.1:15672](http://127.0.0.1:15672) *(логин/пароль: `guest`/`guest`)*.
- **Статус сервисов**: `docker compose ps` (убедитесь, что все контейнеры находятся в состоянии `Up` или `healthy`).
- **Просмотр логов**:
  ```bash
  # Все логи сервисов
  make logs
  # Логи конкретного сервиса
  docker compose logs -f [app|consumer|outbox-publisher|webhook-echo]
  ```
- **Windows-специфика**:
  - Файлы скриптов (`entrypoint.sh` и др.) должны сохраняться с окончаниями строк `LF`.
  - При отсутствии утилиты `make` на Windows используйте прямые вызовы `docker compose` или `powershell`.
  - Для корректного завершения воркеров на Windows вместо `loop.add_signal_handler` задействован модуль `signal.signal`.
