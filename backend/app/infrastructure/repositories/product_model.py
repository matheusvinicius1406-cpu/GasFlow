"""
Product SQLAlchemy Model — Modelo de persistência do Produto.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class ProductModel(Base):
    __tablename__ = "products"

    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_product_tenant_codigo"),
    )

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, index=True)
    nome = Column(String, nullable=False)
    tipo = Column(String, nullable=False)
    preco = Column(Float, nullable=False)
    estoque = Column(Integer, default=0)
    ativo = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
