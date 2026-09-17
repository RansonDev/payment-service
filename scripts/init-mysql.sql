-- MySQL initialization script for Payments Service
-- This script is executed when the MySQL container is first created

-- Create database if it doesn't exist
CREATE DATABASE IF NOT EXISTS `payments` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create user if it doesn't exist and grant privileges
CREATE USER IF NOT EXISTS 'payments'@'%' IDENTIFIED BY 'payments';

-- Grant all privileges on the database to the user
GRANT ALL PRIVILEGES ON `payments`.* TO 'payments'@'%';

-- Flush privileges to apply changes
FLUSH PRIVILEGES;

-- Switch to the created database
USE `payments`;

-- Create initial tables (if needed)
-- This is where you can add any initial table creation
-- Note: Alembic migrations will handle the actual schema creation

-- Show current database and user
SELECT DATABASE() as current_database;
SELECT CURRENT_USER() as current_user;
