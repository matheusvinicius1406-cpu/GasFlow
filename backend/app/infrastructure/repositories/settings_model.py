"""
SystemSetting SQLAlchemy Model — Quadro de Configurações Centralizado.

Chave primária é a própria chave de configuração (ex.: "site_name").
value é JSON para suportar string, bool, número, lista ou objeto.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class SystemSettingModel(Base):
    __tablename__ = "system_settings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # ex: "whatsapp_auto_reply"
    # general, whatsapp, notifications, integrations, operations, appearance
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
