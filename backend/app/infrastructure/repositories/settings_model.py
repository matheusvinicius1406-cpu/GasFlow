"""
SystemSetting SQLAlchemy Model — Quadro de Configurações Centralizado.

Chave primária é a própria chave de configuração (ex.: "site_name").
value é JSON para suportar string, bool, número, lista ou objeto.
"""

from sqlalchemy import Column, String, JSON, DateTime, Boolean
from datetime import datetime
from app.infrastructure.database.base import Base


class SystemSettingModel(Base):
    __tablename__ = "system_settings"

    id = Column(String(64), primary_key=True)  # ex: "whatsapp_auto_reply"
    category = Column(
        String(32), nullable=False, index=True
    )  # general, whatsapp, notifications, integrations, operations, appearance
    value = Column(JSON, nullable=False)
    description = Column(String(255), nullable=True)
    is_editable = Column(Boolean, default=True, nullable=False)
    updated_by = Column(String(36), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
