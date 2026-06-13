from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime

from app.database.base import Base


class DeliveryDriver(Base):
    __tablename__ = "delivery_drivers"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=False)
    placa = Column(String, nullable=True)

    ativo = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)