"""
WhatsApp Automation SQLAlchemy Models — FASE 14

Tables:
- automation_rules: defines automation rules
- automation_executions: tracks each execution

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class AutomationRuleModel(Base):
    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, default="")
    trigger_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # REORDER_OPPORTUNITY, SEGMENT_MEMBERSHIP, MANUAL, SCHEDULED
    status: Mapped[Optional[str]] = mapped_column(String, default="DRAFT")

    # Trigger conditions
    segment_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_filter: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Message template
    message_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    account_id: Mapped[Optional[str]] = mapped_column(String, default="primary")

    # Policies
    max_messages_per_day: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    cooldown_days: Mapped[Optional[int]] = mapped_column(Integer, default=7)
    requires_approval: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)

    # Metrics
    total_executions: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    successful_sends: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    failed_sends: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    opted_out_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AutomationExecutionModel(Base):
    __tablename__ = "automation_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_codigo: Mapped[str] = mapped_column(String, nullable=False)
    customer_nome: Mapped[Optional[str]] = mapped_column(String, default="")
    customer_phone: Mapped[Optional[str]] = mapped_column(String, default="")
    message_text: Mapped[Optional[str]] = mapped_column(Text, default="")
    status: Mapped[Optional[str]] = mapped_column(String, default="PENDING")
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    trigger_context: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
