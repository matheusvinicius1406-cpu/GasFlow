from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint

from app.database.base import Base
from app.models.mixins import TimestampMixin


class DeliveryDriver(Base, TimestampMixin):
    __tablename__ = "delivery_drivers"
    __table_args__ = (
        UniqueConstraint("company_id", "codigo", name="uq_drivers_company_codigo"),
    )

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(ForeignKey("companies.id"), index=True, nullable=False)

    codigo = Column(String, index=True)

    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=False)
    placa = Column(String, nullable=True)

    ativo = Column(Boolean, default=True, nullable=False)
