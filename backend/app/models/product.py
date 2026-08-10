from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, UniqueConstraint

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("company_id", "codigo", name="uq_products_company_codigo"),
    )

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(ForeignKey("companies.id"), index=True, nullable=False)

    codigo = Column(String, index=True)

    nome = Column(String, nullable=False)
    tipo = Column(String, nullable=False)

    preco = Column(Float, nullable=False)
    estoque = Column(Integer, default=0, nullable=False)

    ativo = Column(Boolean, default=True, nullable=False)
