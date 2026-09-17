"""Simple Alembic environment configuration for the Payments Service project."""

import asyncio
from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import your models here
from payments_service.infrastructures.db.models import Base, Payment, outbox_table

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url() -> str:
    """Get database URL from environment variable or config.

    Converts any postgresql URL to postgresql+asyncpg:// for async migrations.
    """
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # Convert to asyncpg if needed
        if "postgresql" in db_url and "+asyncpg" not in db_url:
            # Replace psycopg2 or plain postgresql with asyncpg
            db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        return db_url
    config_url = config.get_main_option("sqlalchemy.url")
    if config_url:
        # Convert to asyncpg if needed
        if "postgresql" in config_url and "+asyncpg" not in config_url:
            config_url = config_url.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://"
            )
            config_url = config_url.replace("postgresql://", "postgresql+asyncpg://")
        return config_url
    msg = "Database URL not found in environment or config"
    raise ValueError(msg)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section)
    if configuration is None:
        msg = "Configuration section not found"
        raise ValueError(msg)

    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
