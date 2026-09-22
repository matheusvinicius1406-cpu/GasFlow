"""
DeliveryDriver SQLAlchemy Model — Modelo de persistência do Entregador.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class DeliveryDriverModel(Base):
    __tablename__ = "delivery_drivers"

    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_driver_tenant_codigo"),)

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, index=True)
    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=False)
    placa = Column(String, nullable=True)
    ativo = Column(Boolean, default=True)  # equivalente a `is_active`
    document = Column(String, nullable=True)  # CPF/CNH — nullable
    username = Column(String, nullable=True, unique=False)
    password_hash = Column(String, nullable=True)
    status = Column(String, default="AVAILABLE")
    vehicle_id = Column(String, nullable=True)
    # Revogação de link público (Parte 1, fix 3/4): o token embute a epoch
    # vigente; incrementar aqui invalida de uma vez todos os links emitidos.
    tracking_epoch = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
