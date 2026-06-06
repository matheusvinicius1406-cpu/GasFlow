from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String

from app.database.base import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

    nome = Column(String, nullable=False)

    telefone = Column(String, nullable=False)
    telefone_secundario = Column(String, nullable=True)

    rua = Column(String, nullable=False)
    numero = Column(String, nullable=False)

    complemento = Column(String, nullable=True)
    referencia = Column(String, nullable=True)

    bairro = Column(String, nullable=False)

    observacoes = Column(String, nullable=True)

    ativo = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )