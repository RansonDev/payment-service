-- Database initialization script for Payments Service application
-- This script runs when the PostgreSQL container starts for the first time

-- Note: User and database are created automatically by postgres image
-- from POSTGRES_USER and POSTGRES_DB environment variables

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Set timezone
SET timezone = 'UTC';

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO payments;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO payments;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO payments;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO payments;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO payments;
