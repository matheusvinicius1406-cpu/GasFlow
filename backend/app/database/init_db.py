"""Criação de schema.

Em desenvolvimento/testes com SQLite usamos `create_all` por conveniência.
Em produção (PostgreSQL) o schema é gerenciado por migrations do Alembic:

    alembic upgrade head
"""

from app.database.base import Base
from app.database.connection import engine

# Importa os modelos para registrá-los no metadata antes do create_all.
from app.models.client import Client  # noqa: F401
from app.models.delivery_driver import DeliveryDriver  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.product import Product  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
