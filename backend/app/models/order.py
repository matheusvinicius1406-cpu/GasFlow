from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime

from app.database.base import Base
import enum


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

    client_codigo = Column(String, index=True)

    product = Column(String)  # GAS / WATER
    quantity = Column(Integer, default=1)

    value = Column(Float, default=0.0)

    address_snapshot = Column(String)

    #  IMPORTANTE: string simples (mais estável)
    status = Column(String, default=OrderStatus.PENDING.value)

    payment_method = Column(String, nullable=True)

    delivery_driver_codigo = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)