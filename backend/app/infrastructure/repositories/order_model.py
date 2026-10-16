"""
Order SQLAlchemy Model — Modelo de persistência do Pedido.

FASE 3.2: Numeric(10,2) para campos financeiros (precisão de centavos).
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): atributos de instância tipam como
o tipo real; a nullability da anotação reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class OrderModel(Base):
    __tablename__ = "orders"

    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_order_tenant_codigo"),)

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[Optional[str]] = mapped_column(String, index=True)
    client_codigo: Mapped[Optional[str]] = mapped_column(String, index=True)

    # Valores — Numeric para precisão financeira
    subtotal: Mapped[Any] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    delivery_fee: Mapped[Any] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    discount: Mapped[Any] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    total: Mapped[Any] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)

    # Pagamento
    payment_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payment_status: Mapped[str] = mapped_column(String, default="PENDING", nullable=False)

    # Entrega
    address_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    delivery_driver_codigo: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String, default="PENDING", nullable=False)

    # Metadados
    source: Mapped[str] = mapped_column(String, default="MANUAL", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
