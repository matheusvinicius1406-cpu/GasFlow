"""Alembic environment — GasFlow.

O schema é definido pelos models SQLAlchemy (Base.metadata). O env.py
importa o init_db para registrar TODAS as tabelas usadas em runtime
(39 tabelas) e resolve a URL a partir da mesma variável do app
(DATABASE_URL), evitando divergência entre o app e as migrations.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Garante import de `app` independente do cwd (CLI, Docker, testes).
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Registra todos os models no Base.metadata (fonte única do schema).
# Import do init_db dispara o registro das 39 tabelas usadas em runtime.
from app.infrastructure.database.init_db import Base  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Mesma resolução do app (connection.py)."""
    return os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script, sem conexão)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (conexão real)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
