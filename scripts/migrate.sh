#!/bin/bash

# Wait for database to be ready
echo "Waiting for database to be ready..."
sleep 10

# Run migrations
echo "Running database migrations..."
alembic upgrade head

echo "Migrations completed successfully!"
