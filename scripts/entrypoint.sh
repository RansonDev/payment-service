#!/bin/bash
set -e

# Ожидание готовности базы данных (опционально, но полезно)
# Здесь можно добавить проверку через pg_isready, если установлены postgresql-client

if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

echo "Starting service: $@"
exec "$@"
