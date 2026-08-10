from sqlalchemy import Boolean, Column, Integer, String

from app.database.base import Base
from app.models.mixins import TimestampMixin


class Company(Base, TimestampMixin):
    """Empresa (depósito). Raiz do isolamento multi-tenant.

    Todo dado de negócio (clientes, pedidos, produtos, entregadores) pertence
    a uma empresa via `company_id`.
    """

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)

    codigo = Column(String, unique=True, index=True)

    nome = Column(String, nullable=False)
    cnpj = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    responsavel = Column(String, nullable=True)

    # Plano de assinatura (SaaS): FREE / PRO / etc.
    plano = Column(String, default="FREE", nullable=False)

    ativo = Column(Boolean, default=True, nullable=False)
