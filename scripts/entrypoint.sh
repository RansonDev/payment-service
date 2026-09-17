#!/bin/bash
set -e

# Ожидание готовности базы данных (опционально, но полезно)
# Здесь можно добавить проверку через pg_isready, если установлены postgresql-client

echo "Running database migrations..."
alembic upgrade head

echo "Starting service: $@"
exec "$@"
