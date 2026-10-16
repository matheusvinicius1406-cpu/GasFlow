"""
DeliveryDriver SQLAlchemy Model — Modelo de persistência do Entregador.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class DeliveryDriverModel(Base):
    __tablename__ = "delivery_drivers"

    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_driver_tenant_codigo"),)

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[Optional[str]] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    telefone: Mapped[str] = mapped_column(String, nullable=False)
    placa: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ativo: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)  # equivalente a `is_active`
    document: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # CPF/CNH — nullable
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, default="AVAILABLE")
    vehicle_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Revogação de link público (Parte 1, fix 3/4): o token embute a epoch
    # vigente; incrementar aqui invalida de uma vez todos os links emitidos.
    tracking_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
