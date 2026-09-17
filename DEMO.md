# Demo - Payments Service

Полная демонстрация работы микросервиса обработки платежей.

## Запуск через Makefile (Linux/macOS/WSL)

Если у вас установлен `make`:

```bash
make demo
```

Эта команда автоматически:
1. Запустит PostgreSQL и RabbitMQ
2. Применит миграции
3. Запустит API, Consumer, Outbox Publisher
4. Создаст 4 тестовых платежа с разными сценариями
5. Покажет результаты обработки

## Запуск вручную (Windows без make)

### Шаг 1: Запуск инфраструктуры

```bash
docker compose up -d postgres rabbitmq
```

Дождитесь healthy-статуса (5-10 секунд):

```bash
docker compose ps
```

### Шаг 2: Применение миграций

```bash
docker compose --profile migrate run --rm migrate
```

### Шаг 3: Запуск сервисов

```bash
docker compose up -d app consumer outbox-publisher webhook-echo
```

Дождитесь запуска (5 секунд):

```bash
docker compose ps
```

### Шаг 4: Создание тестовых платежей

#### Payment 1: Успешный платёж

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: demo-payment-001" \
  -d "{\"amount\": 100.50, \"currency\": \"RUB\", \"description\": \"Demo payment #1\", \"metadata\": {\"order_id\": \"001\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}"
```

**Ожидаемый ответ:** 202 Accepted

```json
{
  "payment_id": "...",
  "status": "pending",
  "created_at": "..."
}
```

#### Payment 2: Идемпотентный повтор (тот же ключ, то же тело)

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: demo-payment-001" \
  -d "{\"amount\": 100.50, \"currency\": \"RUB\", \"description\": \"Demo payment #1\", \"metadata\": {\"order_id\": \"001\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}"
```

**Ожидаемый ответ:** 202 Accepted с **тем же `payment_id`**, что в Payment 1

#### Payment 3: Конфликт идемпотентности (тот же ключ, другое тело)

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: demo-payment-001" \
  -d "{\"amount\": 200.00, \"currency\": \"USD\", \"description\": \"Different payment\", \"metadata\": {\"order_id\": \"999\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}"
```

**Ожидаемый ответ:** 409 Conflict

```json
{
  "detail": "Idempotency key conflict: different request body for key 'demo-payment-001'"
}
```

#### Payment 4: Ещё один успешный платёж

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -H "Idempotency-Key: demo-payment-002" \
  -d "{\"amount\": 250.75, \"currency\": \"EUR\", \"description\": \"Demo payment #2\", \"metadata\": {\"order_id\": \"002\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}"
```

**Ожидаемый ответ:** 202 Accepted с новым `payment_id`

### Шаг 5: Ожидание обработки

Подождите 10 секунд, чтобы:
- Consumer обработал платежи через эмулятор шлюза
- Outbox Publisher опубликовал события в RabbitMQ
- Webhook-ы были доставлены на webhook-echo

### Шаг 6: Проверка результатов

#### Health check

```bash
curl http://localhost:8000/api/health
```

**Ожидаемый ответ:**

```json
{
  "status": "ok"
}
```

#### Webhook deliveries

Проверьте логи webhook-echo:

```bash
docker compose logs webhook-echo --tail 30
```

Вы должны увидеть 2 POST-запроса (для payment-001 и payment-002) с телами вебхуков:

```json
{
  "payment_id": "...",
  "status": "succeeded",  // или "failed" в зависимости от эмулятора
  "amount": 100.50,
  ...
}
```

#### Статус сервисов

```bash
docker compose ps
```

Все сервисы должны быть `Up`:
- `app` - healthy
- `consumer` - running (unhealthy нормально, нет HTTP endpoint)
- `outbox-publisher` - running (unhealthy нормально)
- `postgres` - healthy
- `rabbitmq` - healthy
- `webhook-echo` - healthy

#### Логи сервисов

```bash
# API
docker compose logs app --tail 20

# Consumer
docker compose logs consumer --tail 20

# Outbox Publisher
docker compose logs outbox-publisher --tail 20
```

### Шаг 7: Остановка сервисов

```bash
docker compose down
```

## Что демонстрирует demo

### 1. Асинхронная обработка

API возвращает `202 Accepted` немедленно, фактическая обработка происходит в consumer.

### 2. Transactional Outbox Pattern

Платёж и событие outbox создаются в одной транзакции БД. Проверьте:

```sql
-- Подключитесь к БД:
docker exec -it payments_service-postgres-1 psql -U postgres -d payments_db

-- Проверка инварианта (должно быть 0):
SELECT count(*) FROM payments p
LEFT JOIN outbox o ON o.payload::jsonb ->> 'payment_id' = p.id::text
WHERE o.id IS NULL;
```

### 3. Идемпотентность

- **Повторный запрос с тем же ключом и телом:** возвращает существующий платёж
- **Повторный запрос с тем же ключом но другим телом:** 409 Conflict

### 4. At-least-once delivery

- Outbox Publisher публикует события с **publisher confirms**
- Events помечаются опубликованными **только после подтверждения брокера**
- Consumer идемпотентен: проверяет `webhook_delivered_at`, игнорирует дубликаты

### 5. Retry mechanism (webhook delivery)

Если вебхук не доставлен (таймаут, ошибка сети, не-2xx ответ):
- Сообщение попадает в `payments.retry.1` (TTL=5s)
- После TTL → возвращается в `payments.new` для повтора
- После 3 неудач → `payments.dlq`

Проверьте в RabbitMQ Management UI: http://localhost:15672 (guest/guest)

### 6. Correlation ID

Все логи содержат `trace_id` для сквозного трейсинга:
- `X-Request-ID` в HTTP-запросе/ответе
- `x-trace-id` в заголовках RabbitMQ
- `trace_id` в структурированных логах

## Дополнительные сценарии

### Тестирование failed платежей

Установите `GATEWAY_SUCCESS_RATE=0.0` в `.env`:

```bash
GATEWAY_SUCCESS_RATE=0.0
```

Перезапустите consumer:

```bash
docker compose restart consumer
```

Создайте платёж — статус будет `failed`, но вебхук всё равно доставится.

### Тестирование retry вебхуков

Остановите webhook-echo:

```bash
docker compose stop webhook-echo
```

Создайте платёж. Через 10 секунд посмотрите логи consumer — вы увидите retry-попытки.

Запустите webhook-echo обратно:

```bash
docker compose start webhook-echo
```

Через несколько секунд вебхук будет доставлен.

## Makefile targets

Если у вас установлен `make`, доступны следующие команды:

```bash
make help              # Показать это сообщение
make install           # Установить зависимости (uv sync)
make check             # Запустить все проверки (ruff, mypy, unit tests)
make format            # Автоформатирование (ruff format)
make migrate           # Применить миграции
make test-unit         # Юнит-тесты
make test-integration  # Интеграционные тесты
make test-all          # Все тесты
make docker-up         # Запустить инфраструктуру
make docker-down       # Остановить инфраструктуру
make clean             # Очистить кеш и артефакты
make demo              # Полная демонстрация (этот файл)
make logs              # Показать логи всех сервисов
```

## Troubleshooting

### Ошибка "port already allocated"

Убедитесь, что порты 8000 (API), 5432 (PostgreSQL), 5672/15672 (RabbitMQ) свободны:

```bash
docker compose down
netstat -ano | findstr "8000 5432 5672 15672"
```

### Сервисы не стартуют

Проверьте логи:

```bash
docker compose logs app
docker compose logs consumer
docker compose logs outbox-publisher
```

### Миграции не применяются

Проверьте, что PostgreSQL запущен и healthy:

```bash
docker compose ps postgres
docker compose logs postgres
```

Попробуйте вручную:

```bash
uv run alembic upgrade head
```
