from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.base import Base


class OrderItem(Base):
    """Item de um pedido: um produto, quantidade e preço no momento da venda."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(ForeignKey("orders.id"), index=True, nullable=False)
    product_id = Column(ForeignKey("products.id"), index=True, nullable=True)

    # Snapshots do produto no momento da venda (histórico estável).
    product_codigo = Column(String, nullable=False)
    product_nome = Column(String, nullable=False)

    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")
