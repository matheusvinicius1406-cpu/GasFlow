"""
Client SQLAlchemy Model — Modelo de persistência do Cliente.

Mapeia a entidade de domínio Client para tabela no banco de dados.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class ClientModel(Base):
    __tablename__ = "clients"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, index=True)
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

    # CRM fields
    tipo = Column(String, nullable=True)  # CONSUMER, RESTAURANT, COMPANY, etc.
    email = Column(String, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_client_tenant_codigo"),
        UniqueConstraint("tenant_id", "telefone", name="uq_client_tenant_telefone"),
        Index("ix_clients_telefone", "telefone"),
        Index("ix_clients_tipo", "tipo"),
        Index("ix_clients_ativo", "ativo"),
        Index("ix_clients_email", "email"),
    )
