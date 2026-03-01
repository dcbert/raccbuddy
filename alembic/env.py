"""Alembic migration environment for RaccBuddy.

Uses the synchronous psycopg2 driver for migrations, reading the same
DATABASE_URL env var (but replacing ``asyncpg`` → ``psycopg2``).
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool, text

from alembic import context

# Ensure project root is on sys.path so model imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import ALL model modules so that Base.metadata is fully populated.
from src.core.db import Base  # noqa: E402
from src.core.memory import OwnerMemory, SemanticMemory  # noqa: E402, F401

config = context.config

# Set URL from env (replace async driver with sync for migrations)
raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://raccbuddy:raccbuddy@localhost:5432/raccbuddy",
)
sync_url = raw_url.replace("+asyncpg", "+psycopg2").replace(
    "postgresql://",
    "postgresql+psycopg2://",
)
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Skip pgvector extension objects during autogenerate."""
    if type_ == "table" and name == "pg_vector":
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Ensure pgvector extension exists before migration
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
