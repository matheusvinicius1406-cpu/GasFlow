"""
OrderItem SQLAlchemy Model — Modelo de persistência do Item do Pedido.

FASE 3.2: Numeric(10,2) para campos financeiros.
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey
from datetime import datetime
from app.infrastructure.database.base import Base


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_codigo = Column(String, ForeignKey("orders.codigo"), nullable=False, index=True)
    product_codigo = Column(String, nullable=False)
    product_nome = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)  # Preço congelado
    subtotal = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
