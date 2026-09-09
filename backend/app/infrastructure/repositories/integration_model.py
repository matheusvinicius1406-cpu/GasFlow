"""
Integration SQLAlchemy Models — Integração com sites de revendas.

- integrations: cadastro do site da revenda (URL, auth, seletores, agendamento).
- imported_orders: pedido extraído do site + resultado do processamento.
- sync_logs: histórico de execuções de sincronização.

Credenciais (auth_config) são armazenadas de forma reversível apenas porque o
agente precisa reutilizá-las para autenticar no site — é a mesma classe de dado
de um cofre de integração; nunca são retornadas pelas APIs (redacted).
"""

import secrets
from sqlalchemy import Column, String, JSON, DateTime, Integer, Boolean
from datetime import datetime
from app.infrastructure.database.base import Base


class IntegrationModel(Base):
    __tablename__ = "integrations"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)

    # URL do site da revenda
    base_url = Column(String(500), nullable=False)

    # Autenticação no site: none | basic | token | cookie
    auth_type = Column(String(20), default="none", nullable=False)
    auth_config = Column(JSON, nullable=True)  # credenciais — nunca expostas via API

    # Token de serviço para o agente chamar /integrations/import
    import_token = Column(String(64), nullable=False, unique=True)

    # Mapeamento semântico → seletor CSS (vazio = detecção automática)
    field_mapping = Column(JSON, nullable=True)
    # Seletores estruturais (vazio = detecção automática)
    selectors = Column(JSON, nullable=True)

    # Caminho da página de pedidos (ex.: /pedidos). Agente tenta candidatos.
    orders_path = Column(String(200), nullable=True)

    # Frequência de sincronização (cron simplificado: intervalo em minutos)
    sync_interval_minutes = Column(Integer, default=5, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(20), nullable=True)  # success | error | partial

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def generate_import_token() -> str:
        return secrets.token_urlsafe(32)


class ImportedOrderModel(Base):
    __tablename__ = "imported_orders"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", index=True, nullable=False)
    integration_id = Column(String(36), index=True, nullable=False)

    external_id = Column(String(100), nullable=False, index=True)
    external_data = Column(JSON, nullable=True)

    order_data = Column(JSON, nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending | success | error
    error_message = Column(String(500), nullable=True)
    processed_at = Column(DateTime, nullable=True)

    gasflow_order_codigo = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SyncLogModel(Base):
    __tablename__ = "sync_logs"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", index=True, nullable=False)
    integration_id = Column(String(36), index=True, nullable=False)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)  # success | error | partial
    trigger = Column(String(20), default="manual", nullable=False)  # manual | scheduler | agent
    total_found = Column(Integer, default=0, nullable=False)
    total_imported = Column(Integer, default=0, nullable=False)
    total_errors = Column(Integer, default=0, nullable=False)
    error_details = Column(JSON, nullable=True)
