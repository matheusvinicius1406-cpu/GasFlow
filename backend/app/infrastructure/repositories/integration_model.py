"""
Integration SQLAlchemy Models — Integração com sites de revendas.

- integrations: cadastro do site da revenda (URL, auth, seletores, agendamento).
- imported_orders: pedido extraído do site + resultado do processamento.
- sync_logs: histórico de execuções de sincronização.

Credenciais (auth_config) são armazenadas de forma reversível apenas porque o
agente precisa reutilizá-las para autenticar no site — é a mesma classe de dado
de um cofre de integração; nunca são retornadas pelas APIs (redacted).

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

import secrets
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class IntegrationModel(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # URL do site da revenda
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Autenticação no site: none | basic | token | cookie
    auth_type: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    auth_config: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # credenciais — nunca expostas via API

    # Token de serviço para o agente chamar /integrations/import
    import_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Mapeamento semântico → seletor CSS (vazio = detecção automática)
    field_mapping: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Seletores estruturais (vazio = detecção automática)
    selectors: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Caminho da página de pedidos (ex.: /pedidos). Agente tenta candidatos.
    orders_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Frequência de sincronização (cron simplificado: intervalo em minutos)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # success | error | partial

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def generate_import_token() -> str:
        return secrets.token_urlsafe(32)


class ImportedOrderModel(Base):
    __tablename__ = "imported_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    integration_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    order_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending | success | error
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    gasflow_order_codigo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SyncLogModel(Base):
    __tablename__ = "sync_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    integration_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | error | partial
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual | scheduler | agent
    total_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_details: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
