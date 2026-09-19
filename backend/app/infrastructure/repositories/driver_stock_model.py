"""
DriverStock SQLAlchemy Model — F7: estoque carregado pelo entregador.

Modelo do spec (§3.3.1, decisão C1):
- full_tanks_loaded: cheios que o entregador LEVOU (empréstimo temporário).
  NÃO debita a base — o débito da base acontece uma única vez na entrega
  (deliver_stock_atomic). Conta dupla é bug.
- empty_tanks_returned: vazios devolvidos pelo entregador (rastreamento
  paralelo para a reconciliação de fim de turno).
- blocked: bloqueio de novas cargas até reconciliação manual quando a
  divergência do turno excede a tolerância (driver.stock.tolerance).

Movimentos de carga/avaria/reconciliação vivem em driver_stock_events
(audit por evento — mesmo espírito de stock_movements da base).

F9.1: modelo em estilo SQLAlchemy 2.0 tipado (Mapped[...]) — atributos
instanciados em Python (ex.: row.full_tanks_loaded = 5) tipam como int/str
em vez de Column[int], sem ignore no serviço.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class DriverStockModel(Base):
    """Estoque carregado pelo entregador (1 linha por entregador/produto)."""

    __tablename__ = "driver_stock"

    __table_args__ = (
        UniqueConstraint("tenant_id", "driver_id", "product_codigo", name="uq_driver_stock_driver_product"),
        Index("ix_driver_stock_tenant_driver", "tenant_id", "driver_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", nullable=False, index=True)
    driver_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # codigo do DeliveryDriverModel
    product_codigo: Mapped[str] = mapped_column(String(20), nullable=False)

    # Empréstimo temporário — NÃO debita a base (C1).
    full_tanks_loaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Vazios devolvidos pelo entregador (troca na porta do cliente).
    empty_tanks_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Bloqueio de novas cargas (divergência fora da tolerância).
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DriverStockEventModel(Base):
    """Evento de estoque do entregador: LOADING | DELIVERY | DAMAGE | RETURN | RECONCILE.

    Audit append-only; cada linha carrega os saldos após o evento
    (balance_after) para reconstituir o turno sem recomputar.
    """

    __tablename__ = "driver_stock_events"

    __table_args__ = (Index("ix_driver_stock_events_driver", "tenant_id", "driver_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", nullable=False, index=True)
    driver_id: Mapped[str] = mapped_column(String(36), nullable=False)
    product_codigo: Mapped[str] = mapped_column(String(20), nullable=False)

    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # LOADING|DELIVERY|DAMAGE|RETURN|RECONCILE
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # sempre >= 0; o sinal é do tipo
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # obrigatório em DAMAGE
    reference_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # ex.: DELIVERY
    reference_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # ex.: delivery_id
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    balance_after_loaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balance_after_empty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
