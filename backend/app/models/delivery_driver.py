from sqlalchemy import Boolean, Column, Integer, String

from app.database.base import Base
from app.models.mixins import TimestampMixin


class DeliveryDriver(Base, TimestampMixin):
    __tablename__ = "delivery_drivers"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=False)
    placa = Column(String, nullable=True)

    ativo = Column(Boolean, default=True, nullable=False)
