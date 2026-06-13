from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from datetime import datetime

from app.database.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

    nome = Column(String, nullable=False)
    tipo = Column(String, nullable=False)

    preco = Column(Float, nullable=False)
    estoque = Column(Integer, default=0)

    ativo = Column(Boolean, default=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)