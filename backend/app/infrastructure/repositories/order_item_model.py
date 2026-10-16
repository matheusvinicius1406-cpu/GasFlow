"""
OrderItem SQLAlchemy Model — Modelo de persistência do Item do Pedido.

FASE 3.2: Numeric(10,2) para campos financeiros.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): atributos de instância tipam como
o tipo real; a nullability da anotação reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class OrderItemModel(Base):
    __tablename__ = "order_items"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_codigo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    product_codigo: Mapped[str] = mapped_column(String, nullable=False)
    product_nome: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)  # Preço congelado
    subtotal: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
