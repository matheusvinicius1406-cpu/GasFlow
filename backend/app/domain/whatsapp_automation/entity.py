"""
WhatsApp Automation Domain — FASE 14

Connects CRM intelligence (segments, reorder) to WhatsApp messaging.
Deterministic, auditable, tenant-scoped.

Architecture:
- AutomationRule: defines trigger + conditions + message template
- AutomationExecution: tracks each execution attempt
- AutomationTrigger: what causes the automation to fire
- AutomationAction: what happens when triggered
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class AutomationTriggerType(str, Enum):
    """What triggers the automation."""
    REORDER_OPPORTUNITY = "REORDER_OPPORTUNITY"  # Customer has reorder potential
    SEGMENT_MEMBERSHIP = "SEGMENT_MEMBERSHIP"    # Customer belongs to a segment
    MANUAL = "MANUAL"                            # Operator manually triggers
    SCHEDULED = "SCHEDULED"                      # Time-based trigger


class AutomationStatus(str, Enum):
    """Automation rule lifecycle."""
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class ExecutionStatus(str, Enum):
    """Status of a single execution."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    OPTED_OUT = "OPTED_OUT"


@dataclass
class AutomationRule:
    """A rule that defines when and how to send WhatsApp messages."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    trigger_type: AutomationTriggerType = AutomationTriggerType.MANUAL
    status: AutomationStatus = AutomationStatus.DRAFT

    # Trigger conditions
    segment_id: Optional[int] = None  # For SEGMENT_MEMBERSHIP trigger
    min_score: Optional[float] = None  # For REORDER_OPPORTUNITY trigger
    confidence_filter: Optional[str] = None  # HIGH, MEDIUM, LOW

    # Message template
    message_template: str = ""  # Supports {{customer_name}}, {{product}}, etc.
    account_id: str = "primary"  # Which WhatsApp account to use

    # Policies
    max_messages_per_day: int = 1
    cooldown_days: int = 7
    requires_approval: bool = True

    # Metadata
    total_executions: int = 0
    successful_sends: int = 0
    failed_sends: int = 0
    opted_out_count: int = 0

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        now = datetime.utcnow()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_type": self.trigger_type.value,
            "status": self.status.value,
            "segment_id": self.segment_id,
            "min_score": self.min_score,
            "confidence_filter": self.confidence_filter,
            "message_template": self.message_template,
            "account_id": self.account_id,
            "max_messages_per_day": self.max_messages_per_day,
            "cooldown_days": self.cooldown_days,
            "requires_approval": self.requires_approval,
            "total_executions": self.total_executions,
            "successful_sends": self.successful_sends,
            "failed_sends": self.failed_sends,
            "opted_out_count": self.opted_out_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class AutomationExecution:
    """Tracks a single execution of an automation rule."""
    id: Optional[int] = None
    rule_id: int = 0
    customer_codigo: str = ""
    customer_nome: str = ""
    customer_phone: str = ""
    message_text: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    error_message: Optional[str] = None
    conversation_id: Optional[int] = None

    triggered_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    # Context that triggered this execution
    trigger_context: Optional[Dict[str, Any]] = None  # e.g., reorder score, segment name

    created_at: Optional[datetime] = None

    def __post_init__(self):
        now = datetime.utcnow()
        if self.triggered_at is None:
            self.triggered_at = now
        if self.created_at is None:
            self.created_at = now

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "customer_codigo": self.customer_codigo,
            "customer_nome": self.customer_nome,
            "customer_phone": self.customer_phone,
            "message_text": self.message_text,
            "status": self.status.value,
            "error_message": self.error_message,
            "conversation_id": self.conversation_id,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "trigger_context": self.trigger_context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class AutomationMetrics:
    """Aggregate metrics for automation executions."""
    total_rules: int = 0
    active_rules: int = 0
    total_executions: int = 0
    pending: int = 0
    sent: int = 0
    delivered: int = 0
    failed: int = 0
    opted_out: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_rules": self.total_rules,
            "active_rules": self.active_rules,
            "total_executions": self.total_executions,
            "pending": self.pending,
            "sent": self.sent,
            "delivered": self.delivered,
            "failed": self.failed,
            "opted_out": self.opted_out,
            "success_rate": self.success_rate,
        }
