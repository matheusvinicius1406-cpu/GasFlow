"""
Product SQLAlchemy Model — Modelo de persistência do Produto.

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`) — atributos de instância tipam
como o tipo real em vez de `Column[...]`, sem mudar o schema (a nullability da
anotação reproduz a do modelo legado/Alembic).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ProductModel(Base):
    __tablename__ = "products"

    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_product_tenant_codigo"),)

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[Optional[str]] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    preco: Mapped[float] = mapped_column(Float, nullable=False)
    # Pagamento no cartão (opcional por produto): preços 1x e 2x. NULL = não
    # habilitado no cartão; preenchidos = valores praticados em cada parcela.
    cartao_habilitado: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    preco_cartao_1x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    preco_cartao_2x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estoque: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    ativo: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
