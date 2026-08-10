import enum

from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("company_id", "codigo", name="uq_orders_company_codigo"),)

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(ForeignKey("companies.id"), index=True, nullable=False)

    codigo = Column(String, index=True)

    # Chaves estrangeiras reais (integridade referencial).
    client_id = Column(ForeignKey("clients.id"), index=True, nullable=True)
    product_id = Column(ForeignKey("products.id"), index=True, nullable=True)
    delivery_driver_id = Column(ForeignKey("delivery_drivers.id"), index=True, nullable=True)

    # Códigos de negócio (legíveis / estáveis) mantidos para a API.
    client_codigo = Column(String, index=True)
    product = Column(String)  # código do produto
    delivery_driver_codigo = Column(String, nullable=True)

    quantity = Column(Integer, default=1, nullable=False)
    value = Column(Float, default=0.0, nullable=False)

    address_snapshot = Column(String)

    # String simples (mais estável que Enum nativo entre bancos).
    status = Column(String, default=OrderStatus.PENDING.value, nullable=False, index=True)

    payment_method = Column(String, nullable=True)

    client = relationship("Client", back_populates="orders")
    product_ref = relationship("Product")
    driver = relationship("DeliveryDriver")
