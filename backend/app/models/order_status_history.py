from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class OrderStatusHistory(Base, TimestampMixin):
    """Registro imutável de cada mudança de status de um pedido."""

    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(ForeignKey("orders.id"), index=True, nullable=False)

    # from_status None = criação do pedido.
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)

    # Usuário que fez a mudança (quando disponível).
    changed_by_user_id = Column(ForeignKey("users.id"), nullable=True)

    order = relationship("Order", back_populates="status_history")
