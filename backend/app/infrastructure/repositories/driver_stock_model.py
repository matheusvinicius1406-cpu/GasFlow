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
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Index, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class DriverStockModel(Base):
    """Estoque carregado pelo entregador (1 linha por entregador/produto)."""

    __tablename__ = "driver_stock"

    __table_args__ = (
        UniqueConstraint("tenant_id", "driver_id", "product_codigo", name="uq_driver_stock_driver_product"),
        Index("ix_driver_stock_tenant_driver", "tenant_id", "driver_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, default="default", nullable=False, index=True)
    driver_id = Column(String(36), nullable=False, index=True)  # codigo do DeliveryDriverModel
    product_codigo = Column(String(20), nullable=False)

    # Empréstimo temporário — NÃO debita a base (C1).
    full_tanks_loaded = Column(Integer, nullable=False, default=0)
    # Vazios devolvidos pelo entregador (troca na porta do cliente).
    empty_tanks_returned = Column(Integer, nullable=False, default=0)

    # Bloqueio de novas cargas (divergência fora da tolerância).
    blocked = Column(Boolean, nullable=False, default=False)
    blocked_reason = Column(String(200), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DriverStockEventModel(Base):
    """Evento de estoque do entregador: LOADING | DELIVERY | DAMAGE | RETURN | RECONCILE.

    Audit append-only; cada linha carrega os saldos após o evento
    (balance_after) para reconstituir o turno sem recomputar.
    """

    __tablename__ = "driver_stock_events"

    __table_args__ = (Index("ix_driver_stock_events_driver", "tenant_id", "driver_id", "created_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, default="default", nullable=False, index=True)
    driver_id = Column(String(36), nullable=False)
    product_codigo = Column(String(20), nullable=False)

    event_type = Column(String(20), nullable=False)  # LOADING|DELIVERY|DAMAGE|RETURN|RECONCILE
    quantity = Column(Integer, nullable=False, default=0)  # sempre >= 0; o sinal é do tipo
    reason = Column(String(200), nullable=True)  # obrigatório em DAMAGE
    reference_type = Column(String(30), nullable=True)  # ex.: DELIVERY
    reference_id = Column(String(36), nullable=True)  # ex.: delivery_id
    details = Column(JSON, nullable=True)

    balance_after_loaded = Column(Integer, nullable=False, default=0)
    balance_after_empty = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
