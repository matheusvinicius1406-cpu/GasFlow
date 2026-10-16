"""
Client SQLAlchemy Model — Modelo de persistência do Cliente.

Mapeia a entidade de domínio Client para tabela no banco de dados.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ClientModel(Base):
    __tablename__ = "clients"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[Optional[str]] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    telefone: Mapped[str] = mapped_column(String, nullable=False)
    telefone_secundario: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rua: Mapped[str] = mapped_column(String, nullable=False)
    numero: Mapped[str] = mapped_column(String, nullable=False)
    complemento: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    referencia: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bairro: Mapped[str] = mapped_column(String, nullable=False)
    observacoes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ativo: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)

    # CRM fields
    tipo: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # CONSUMER, RESTAURANT, COMPANY, etc.
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Integração WhatsApp (sync/enriquecimento/reativação)
    has_name: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # nome veio do contato do WA
    is_whatsapp: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=True)
    last_interaction_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # OPTED_IN, OPTED_OUT, BLOCKED (espelho do serviço)
    marketing_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # ── Geocoding do renomeador de contatos (.vcf — ADR-0001 / Fase 2 §7) ──
    cidade: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ViaCEP/geocoding exige município
    uf: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Nome bruto da importação (com o código legado) — rastreabilidade. `nome`
    # passa a ser só nome de pessoa.
    nome_importado: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cep: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)  # 00000-000
    entre_ruas: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "Rua A e Rua B" (best-effort)
    geocode_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # OK, NAO_ENCONTRADO, PENDENTE
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_client_tenant_codigo"),
        UniqueConstraint("tenant_id", "telefone", name="uq_client_tenant_telefone"),
        Index("ix_clients_telefone", "telefone"),
        Index("ix_clients_tipo", "tipo"),
        Index("ix_clients_ativo", "ativo"),
        Index("ix_clients_email", "email"),
        Index("ix_clients_last_interaction", "last_interaction_at"),
        Index("ix_clients_marketing_status", "marketing_status"),
        Index("ix_clients_geocode_status", "geocode_status"),
    )
