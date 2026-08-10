import enum

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class StockMovementType(str, enum.Enum):
    SALE = "SALE"  # saída por venda (pedido)
    RESTOCK = "RESTOCK"  # entrada por cancelamento de pedido
    ADJUSTMENT = "ADJUSTMENT"  # ajuste manual de estoque


class StockMovement(Base, TimestampMixin):
    """Auditoria de toda alteração de estoque (entrada/saída)."""

    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(ForeignKey("companies.id"), index=True, nullable=False)
    product_id = Column(ForeignKey("products.id"), index=True, nullable=False)
    order_id = Column(ForeignKey("orders.id"), index=True, nullable=True)

    tipo = Column(String, nullable=False)

    # Delta aplicado ao estoque (negativo = saída, positivo = entrada).
    quantity = Column(Integer, nullable=False)
    # Estoque resultante após o movimento (facilita auditoria).
    estoque_after = Column(Integer, nullable=False)

    product = relationship("Product")
