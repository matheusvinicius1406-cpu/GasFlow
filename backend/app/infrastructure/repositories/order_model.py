"""
Order SQLAlchemy Model — Modelo de persistência do Pedido.

FASE 3.2: Numeric(10,2) para campos financeiros (precisão de centavos).
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey
from datetime import datetime
from app.infrastructure.database.base import Base


class OrderModel(Base):
    __tablename__ = "orders"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, unique=True, index=True)
    client_codigo = Column(String, ForeignKey("clients.codigo"), index=True)

    # Valores — Numeric para precisão financeira
    subtotal = Column(Numeric(10, 2), default=0.0, nullable=False)
    delivery_fee = Column(Numeric(10, 2), default=0.0, nullable=False)
    discount = Column(Numeric(10, 2), default=0.0, nullable=False)
    total = Column(Numeric(10, 2), default=0.0, nullable=False)

    # Pagamento
    payment_method = Column(String, nullable=True)
    payment_status = Column(String, default="PENDING", nullable=False)

    # Entrega
    address_snapshot = Column(String, nullable=False)
    delivery_driver_codigo = Column(String, nullable=True)

    # Status
    status = Column(String, default="PENDING", nullable=False)

    # Metadados
    source = Column(String, default="MANUAL", nullable=False)
    notes = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
