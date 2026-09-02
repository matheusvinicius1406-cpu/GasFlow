"""
WhatsApp Automation SQLAlchemy Models — FASE 14

Tables:
- automation_rules: defines automation rules
- automation_executions: tracks each execution
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from datetime import datetime
from app.infrastructure.database.base import Base


class AutomationRuleModel(Base):
    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, default="default", index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    trigger_type = Column(String, nullable=False)  # REORDER_OPPORTUNITY, SEGMENT_MEMBERSHIP, MANUAL, SCHEDULED
    status = Column(String, default="DRAFT")

    # Trigger conditions
    segment_id = Column(Integer, nullable=True)
    min_score = Column(Float, nullable=True)
    confidence_filter = Column(String, nullable=True)

    # Message template
    message_template = Column(Text, nullable=False, default="")
    account_id = Column(String, default="primary")

    # Policies
    max_messages_per_day = Column(Integer, default=1)
    cooldown_days = Column(Integer, default=7)
    requires_approval = Column(Boolean, default=True)

    # Metrics
    total_executions = Column(Integer, default=0)
    successful_sends = Column(Integer, default=0)
    failed_sends = Column(Integer, default=0)
    opted_out_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AutomationExecutionModel(Base):
    __tablename__ = "automation_executions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, default="default", index=True)
    rule_id = Column(Integer, nullable=False, index=True)
    customer_codigo = Column(String, nullable=False)
    customer_nome = Column(String, default="")
    customer_phone = Column(String, default="")
    message_text = Column(Text, default="")
    status = Column(String, default="PENDING")
    error_message = Column(String, nullable=True)
    conversation_id = Column(Integer, nullable=True)

    triggered_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    trigger_context = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
