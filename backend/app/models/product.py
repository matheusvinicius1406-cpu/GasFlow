from sqlalchemy import Boolean, Column, Float, Integer, String

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

    nome = Column(String, nullable=False)
    tipo = Column(String, nullable=False)

    preco = Column(Float, nullable=False)
    estoque = Column(Integer, default=0, nullable=False)

    ativo = Column(Boolean, default=True, nullable=False)
