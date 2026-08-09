from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

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
