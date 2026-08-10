from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("company_id", "codigo", name="uq_clients_company_codigo"),)

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(ForeignKey("companies.id"), index=True, nullable=False)

    codigo = Column(String, index=True)

    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=False, index=True)

    telefone_secundario = Column(String, nullable=True)

    rua = Column(String, nullable=False)
    numero = Column(String, nullable=False)

    complemento = Column(String, nullable=True)
    referencia = Column(String, nullable=True)

    bairro = Column(String, nullable=False)

    observacoes = Column(String, nullable=True)

    ativo = Column(Boolean, default=True, nullable=False)

    orders = relationship("Order", back_populates="client")
