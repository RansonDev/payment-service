.PHONY: help install check format migrate test-unit test-integration test-all docker-up docker-down clean demo logs

.DEFAULT_GOAL := help

SHELL := bash
UV := uv
DOCKER_COMPOSE := docker compose
PYTHON := $(UV) run python
PYTEST := $(UV) run pytest
RUFF := $(UV) run ruff
MYPY := $(UV) run mypy
ALEMBIC := $(UV) run alembic

help:
	@echo "Payments Service - Available targets:"
	@echo ""
	@echo "  make help              Show this help message (default)"
	@echo "  make install           Install dependencies (uv sync)"
	@echo "  make check             Run all checks (ruff, mypy, unit tests)"
	@echo "  make format            Auto-format code (ruff format)"
	@echo "  make migrate           Apply database migrations"
	@echo "  make test-unit         Run unit tests"
	@echo "  make test-integration  Run integration tests (infrastructure required)"
	@echo "  make test-integration-docker Run integration tests in Docker"
	@echo "  make test-all          Run all tests sequentially (unit + integration-docker)"
	@echo "  make docker-up         Start full infrastructure (API, workers, DB, broker)"
	@echo "  make docker-down       Stop infrastructure"
	@echo "  make clean             Clean cache and artifacts"
	@echo "  make demo              Full demonstration of the service"
	@echo "  make logs              Show logs from all services"
	@echo ""

install:
	@echo "Installing dependencies..."
	$(UV) sync
	@echo "Dependencies installed successfully."

check:
	@echo "Running linter..."
	$(RUFF) check src/
	@echo ""
	@echo "Running type checker..."
	$(MYPY) src/
	@echo ""
	@echo "Running unit tests..."
	$(PYTEST) -m unit -q
	@echo ""
	@echo "All checks passed!"

format:
	@echo "Formatting code..."
	$(RUFF) format src/ tests/
	@echo "Code formatted successfully."

migrate:
	@echo "Applying database migrations..."
	$(ALEMBIC) upgrade head
	@echo "Migrations applied successfully."

test-unit:
	@echo "Running unit tests..."
	$(PYTEST) -m unit -v

test-integration:
	@echo "Running integration tests (infrastructure required)..."
	$(PYTEST) -m integration -v

test-integration-docker:
	@echo "Running integration tests in Docker..."
	$(DOCKER_COMPOSE) --profile test run --rm test pytest tests/test_integration/ -v

test-all:
	@echo "Running all tests sequentially..."
	@echo ""
	@echo "==> Step 1: Unit tests (Local)"
	@$(MAKE) test-unit
	@echo ""
	@echo "==> Step 2: Integration tests (Docker)"
	@$(MAKE) test-integration-docker
	@echo ""
	@echo "All tests completed!"

docker-up:
	@echo "Starting full infrastructure (API, workers, DB, broker)..."
	$(DOCKER_COMPOSE) up -d postgres rabbitmq
	@echo "Waiting for core services (8s)..."
	@powershell -Command "Start-Sleep -Seconds 8"
	@echo "Starting application and workers..."
	@echo "Note: Database migrations will be applied automatically via entrypoint.sh"
	$(DOCKER_COMPOSE) up -d app consumer outbox-publisher webhook-echo
	@echo "Waiting for services to start (15s)..."
	@powershell -Command "Start-Sleep -Seconds 15"
	$(DOCKER_COMPOSE) ps
	@echo "Infrastructure is up."

docker-down:
	@echo "Stopping infrastructure..."
	$(DOCKER_COMPOSE) down
	@echo "Infrastructure stopped."

clean:
	@echo "Cleaning cache and artifacts..."
	@powershell -Command "Get-ChildItem -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Get-ChildItem -Recurse -Directory -Filter '.pytest_cache' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Get-ChildItem -Recurse -Directory -Filter '.ruff_cache' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Get-ChildItem -Recurse -Directory -Filter '.mypy_cache' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Get-ChildItem -Recurse -Directory -Filter 'htmlcov' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Get-ChildItem -Recurse -Filter '*.pyc' | Remove-Item -Force -ErrorAction SilentlyContinue"
	@echo "Cache and artifacts cleaned."

demo:
	@echo "========================================="
	@echo "Payments Service - Full Demonstration"
	@echo "========================================="
	@echo ""
	@echo "[1/7] Starting infrastructure (PostgreSQL, RabbitMQ)..."
	$(DOCKER_COMPOSE) up -d postgres rabbitmq
	@echo "Waiting for services to be healthy..."
	@powershell -Command "Start-Sleep -Seconds 8"
	@echo ""
	@echo "[2/7] Starting API, Consumer, Outbox Publisher..."
	@echo "Note: Database migrations will be applied automatically via entrypoint.sh"
	$(DOCKER_COMPOSE) up -d app consumer outbox-publisher webhook-echo
	@echo "Waiting for services to start (15s)..."
	@powershell -Command "Start-Sleep -Seconds 15"
	$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "[3/7] Creating test payments..."
	@echo ""
	@echo "==> Payment 1: Successful payment"
	@curl -s -X POST http://127.0.0.1:8000/api/payments \
		-H "Content-Type: application/json" \
		-H "X-API-Key: test-api-key-12345" \
		-H "Idempotency-Key: demo-payment-001" \
		-d "{\"amount\": 100.50, \"currency\": \"RUB\", \"description\": \"Demo payment #1\", \"metadata\": {\"order_id\": \"001\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}" \
		| $(PYTHON) -m json.tool
	@echo ""
	@echo "==> Payment 2: Idempotent retry (same key, same body)"
	@curl -s -X POST http://127.0.0.1:8000/api/payments \
		-H "Content-Type: application/json" \
		-H "X-API-Key: test-api-key-12345" \
		-H "Idempotency-Key: demo-payment-001" \
		-d "{\"amount\": 100.50, \"currency\": \"RUB\", \"description\": \"Demo payment #1\", \"metadata\": {\"order_id\": \"001\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}" \
		| $(PYTHON) -m json.tool
	@echo ""
	@echo "==> Payment 3: Idempotency conflict (same key, different body) - expect 409"
	@curl -s -X POST http://127.0.0.1:8000/api/payments \
		-H "Content-Type: application/json" \
		-H "X-API-Key: test-api-key-12345" \
		-H "Idempotency-Key: demo-payment-001" \
		-d "{\"amount\": 200.00, \"currency\": \"USD\", \"description\": \"Different payment\", \"metadata\": {\"order_id\": \"999\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}" \
		| $(PYTHON) -m json.tool || echo "(Expected 409 Conflict)"
	@echo ""
	@echo "==> Payment 4: Another successful payment"
	@curl -s -X POST http://127.0.0.1:8000/api/payments \
		-H "Content-Type: application/json" \
		-H "X-API-Key: test-api-key-12345" \
		-H "Idempotency-Key: demo-payment-002" \
		-d "{\"amount\": 250.75, \"currency\": \"EUR\", \"description\": \"Demo payment #2\", \"metadata\": {\"order_id\": \"002\"}, \"webhook_url\": \"http://webhook-echo:8080/hook\"}" \
		| $(PYTHON) -m json.tool
	@echo ""
	@echo "[4/7] Waiting for payment processing (10 seconds)..."
	@powershell -Command "Start-Sleep -Seconds 10"
	@echo ""
	@echo "[5/7] Checking payment statuses..."
	@echo ""
	@echo "==> Health check:"
	@curl -s http://127.0.0.1:8000/api/health | $(PYTHON) -m json.tool
	@echo ""
	@echo "[6/7] Checking webhook deliveries..."
	@echo ""
	@echo "==> Webhook echo logs (last 30 lines):"
	@$(DOCKER_COMPOSE) logs webhook-echo --tail 30 | grep -E "(POST|payment_id|status)" || echo "No webhook deliveries yet"
	@echo ""
	@echo "[7/7] Service status:"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "========================================="
	@echo "Demo completed successfully!"
	@echo "========================================="
	@echo ""
	@echo "Next steps:"
	@echo "  - Check logs: make logs"
	@echo "  - View RabbitMQ UI: http://127.0.0.1:15672 (guest/guest)"
	@echo "  - View API docs: http://127.0.0.1:8000/api/docs"
	@echo "  - Stop services: make docker-down"
	@echo ""

logs:
	@echo "Service logs:"
	@echo ""
	@echo "==> API:"
	@$(DOCKER_COMPOSE) logs app --tail 20
	@echo ""
	@echo "==> Consumer:"
	@$(DOCKER_COMPOSE) logs consumer --tail 20
	@echo ""
	@echo "==> Outbox Publisher:"
	@$(DOCKER_COMPOSE) logs outbox-publisher --tail 20
	@echo ""
	@echo "==> Webhook Echo:"
	@$(DOCKER_COMPOSE) logs webhook-echo --tail 20
