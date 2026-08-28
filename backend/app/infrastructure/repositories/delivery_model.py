"""
DeliveryDriver SQLAlchemy Model — Modelo de persistência do Entregador.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class DeliveryDriverModel(Base):
    __tablename__ = "delivery_drivers"

    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_driver_tenant_codigo"),
    )

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, index=True)
    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=False)
    placa = Column(String, nullable=True)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
