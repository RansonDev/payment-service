#!/bin/bash

# PostgreSQL Database Initialization Script
# This script initializes the PostgreSQL database with proper schema and extensions

set -e  # Exit on any error

echo "🚀 Starting PostgreSQL database initialization..."

# Load environment variables
if [ -f .env ]; then
    echo "📝 Loading environment variables from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "⚠️  Warning: .env file not found. Using default values."
fi

# Default database connection parameters
DB_HOST=${POSTGRES_SERVER:-localhost}
DB_PORT=${POSTGRES_PORT:-5432}
DB_USER=${POSTGRES_USER:-payments}
DB_PASSWORD=${POSTGRES_PASSWORD:-payments}
DB_NAME=${POSTGRES_DB:-payments}

# Construct database URL
DB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/postgres"

echo "🔗 Connecting to PostgreSQL at ${DB_HOST}:${DB_PORT}"

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if docker-compose exec -T postgres psql -U "${DB_USER}" -d postgres -c "SELECT 1;" > /dev/null 2>&1; then
        echo "✅ Database is ready!"
        break
    fi

    echo "🔄 Attempt ${attempt}/${max_attempts}: Database not ready, waiting 2 seconds..."
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    echo "❌ Error: Database is not ready after ${max_attempts} attempts"
    exit 1
fi

# Check if database already exists
echo "🔍 Checking if database '${DB_NAME}' exists..."
DB_EXISTS=$(docker-compose exec -T postgres psql -U "${DB_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")

if [ "$DB_EXISTS" = "1" ]; then
    echo "⚠️  Database '${DB_NAME}' already exists. Skipping initialization."
    echo "💡 If you want to reinitialize the database, drop it first:"
    echo "   docker-compose exec postgres psql -U \"${DB_USER}\" -d postgres -c \"DROP DATABASE IF EXISTS ${DB_NAME};\""
    exit 0
fi

# Create database
echo "🏗️  Creating database '${DB_NAME}'..."
docker-compose exec -T postgres psql -U "${DB_USER}" -d postgres -c "CREATE DATABASE ${DB_NAME};"

# Connect to the new database and create extensions
echo "🔧 Creating extensions in database '${DB_NAME}'..."
docker-compose exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -c "
    CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
    CREATE EXTENSION IF NOT EXISTS \"pg_trgm\";
    SET timezone = 'UTC';
"

# Run the init-db.sql script if it exists
if [ -f "scripts/init-db.sql" ]; then
    echo "📄 Running init-db.sql script..."
    docker-compose exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" < scripts/init-db.sql
else
    echo "ℹ️  init-db.sql not found, skipping custom initialization script"
fi

# Grant privileges
echo "🔐 Setting up privileges..."
docker-compose exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -c "
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${DB_USER};
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${DB_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${DB_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${DB_USER};
"

echo "✅ Database initialization completed successfully!"
echo "🎉 Database '${DB_NAME}' is ready for use."
echo ""
echo "📋 Connection details:"
echo "   Host: ${DB_HOST}"
echo "   Port: ${DB_PORT}"
echo "   Database: ${DB_NAME}"
echo "   User: ${DB_USER}"
echo ""
echo "💡 Next steps:"
echo "   1. Run migrations: make migrate"
echo "   2. Start the application: make docker-up-dev"
