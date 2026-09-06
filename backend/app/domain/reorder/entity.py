"""
Reorder Intelligence Domain — FASE 13.2

Deterministic, auditable reorder prediction based on real purchase history.
No LLM dependency — pure data-driven scoring.

Architecture:
- ReorderOpportunity: prediction for a single customer
- ReorderStatus: classification of reorder urgency
- ConfidenceLevel: statistical confidence in the prediction
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List


class ReorderStatus(str, Enum):
    """Classification of reorder urgency based on timing."""

    READY = "READY"  # Customer is near expected reorder date
    DUE = "DUE"  # Customer is within expected window
    OVERDUE = "OVERDUE"  # Customer passed the expected window
    DORMANT = "DORMANT"  # Customer far beyond expected pattern


class ConfidenceLevel(str, Enum):
    """Statistical confidence in the reorder prediction."""

    LOW = "LOW"  # Insufficient data (< 3 orders or high variance)
    MEDIUM = "MEDIUM"  # Moderate data (3-5 orders, some variance)
    HIGH = "HIGH"  # Strong pattern (6+ orders, consistent intervals)


@dataclass
class ReorderOpportunity:
    """A single reorder prediction for a customer."""

    customer_codigo: str
    customer_nome: str
    total_orders: int
    total_spent: float
    average_ticket: float
    days_since_last_order: Optional[int]
    last_order_date: Optional[datetime]
    expected_reorder_date: Optional[datetime]
    expected_interval_days: Optional[float]
    reorder_score: float  # 0-100
    confidence: ConfidenceLevel
    status: ReorderStatus
    recommended_product: Optional[str] = None
    days_overdue: Optional[int] = None
    avg_days_between_orders: Optional[float] = None
    order_dates: List[str] = field(default_factory=list)  # ISO dates
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "customer_codigo": self.customer_codigo,
            "customer_nome": self.customer_nome,
            "total_orders": self.total_orders,
            "total_spent": self.total_spent,
            "average_ticket": self.average_ticket,
            "days_since_last_order": self.days_since_last_order,
            "last_order_date": self.last_order_date.isoformat() if self.last_order_date else None,
            "expected_reorder_date": self.expected_reorder_date.isoformat() if self.expected_reorder_date else None,
            "expected_interval_days": self.expected_interval_days,
            "reorder_score": self.reorder_score,
            "confidence": self.confidence.value,
            "status": self.status.value,
            "recommended_product": self.recommended_product,
            "days_overdue": self.days_overdue,
            "avg_days_between_orders": self.avg_days_between_orders,
            "order_dates": self.order_dates,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class ReorderSummary:
    """Aggregate summary of all reorder opportunities."""

    total_customers: int
    ready_count: int
    due_count: int
    overdue_count: int
    dormant_count: int
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    opportunities: List[ReorderOpportunity] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_customers": self.total_customers,
            "ready_count": self.ready_count,
            "due_count": self.due_count,
            "overdue_count": self.overdue_count,
            "dormant_count": self.dormant_count,
            "high_confidence_count": self.high_confidence_count,
            "medium_confidence_count": self.medium_confidence_count,
            "low_confidence_count": self.low_confidence_count,
            "opportunities": [o.to_dict() for o in self.opportunities],
        }
