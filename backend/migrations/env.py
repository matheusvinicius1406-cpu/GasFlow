"""
Alembic Environment Configuration for GasFlow

Reads DATABASE_URL from environment (same as the app) and imports all models
for autogenerate support.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import Base and all models so Alembic can detect them
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.financial_models import (
    PaymentModel, ReceivableModel, ExpenseModel,
    CashMovementModel, FinancialLedgerModel
)
from app.infrastructure.ai.models import ConversationModel, AIMessageModel, AIAuditLogModel

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment if available
database_url = os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")
config.set_main_option("sqlalchemy.url", database_url)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# All models registered in Base.metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
