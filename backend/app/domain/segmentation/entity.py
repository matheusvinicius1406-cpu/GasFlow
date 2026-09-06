"""
CRM Segmentation Domain — FASE 13.1

Deterministic, auditable customer segmentation based on real data.
Rules are evaluated against actual customer metrics from orders, payments, and inventory.

Architecture:
- Segment: named collection of rules
- SegmentRule: individual condition (field + operator + value)
- Rule evaluation is deterministic and auditable
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Any


class RuleField(str, Enum):
    """Fields that can be used in segmentation rules."""

    TOTAL_ORDERS = "total_orders"
    TOTAL_SPENT = "total_spent"
    AVERAGE_TICKET = "average_ticket"
    DAYS_SINCE_LAST_ORDER = "days_since_last_order"
    CLIENT_TYPE = "client_type"
    IS_ACTIVE = "is_active"
    HAS_EMAIL = "has_email"
    FAVORITE_PRODUCT = "favorite_product"
    ORDER_FREQUENCY = "order_frequency"  # orders per month
    PAYMENT_STATUS = "payment_status"  # has pending payments


class RuleOperator(str, Enum):
    """Operators for rule comparison."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_OR_EQUAL = "less_or_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


class SegmentStatus(str, Enum):
    """Segment lifecycle status."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass
class SegmentRule:
    """A single condition for customer segmentation."""

    field: RuleField
    operator: RuleOperator
    value: Any = None  # String, number, or boolean depending on field

    def __post_init__(self):
        # Validate field and operator are valid enum values
        if not isinstance(self.field, RuleField):
            try:
                self.field = RuleField(self.field)
            except (ValueError, KeyError):
                raise ValueError(f"Invalid rule field: {self.field}")
        if not isinstance(self.operator, RuleOperator):
            try:
                self.operator = RuleOperator(self.operator)
            except (ValueError, KeyError):
                raise ValueError(f"Invalid rule operator: {self.operator}")

    def evaluate(self, customer_metrics: dict) -> bool:
        """Evaluate this rule against customer metrics.

        Returns True if the customer matches this rule.
        """
        field_value = customer_metrics.get(self.field.value)

        # Handle None/missing values
        if field_value is None:
            if self.operator in (RuleOperator.IS_FALSE,):
                return True
            if self.operator in (RuleOperator.IS_TRUE,):
                return False
            return False

        # Boolean fields
        if self.field in (RuleField.IS_ACTIVE, RuleField.HAS_EMAIL):
            bool_val = bool(field_value)
            if self.operator == RuleOperator.IS_TRUE:
                return bool_val
            if self.operator == RuleOperator.IS_FALSE:
                return not bool_val
            return False

        # String fields
        if self.field in (RuleField.CLIENT_TYPE, RuleField.FAVORITE_PRODUCT, RuleField.PAYMENT_STATUS):
            str_val = str(field_value).upper()
            target = str(self.value).upper() if self.value else ""
            if self.operator == RuleOperator.EQUALS:
                return str_val == target
            if self.operator == RuleOperator.NOT_EQUALS:
                return str_val != target
            if self.operator == RuleOperator.CONTAINS:
                return target in str_val
            if self.operator == RuleOperator.NOT_CONTAINS:
                return target not in str_val
            return False

        # Numeric fields
        try:
            num_val = float(field_value)
            target = float(self.value) if self.value is not None else 0
        except (ValueError, TypeError):
            return False

        if self.operator == RuleOperator.EQUALS:
            return num_val == target
        if self.operator == RuleOperator.NOT_EQUALS:
            return num_val != target
        if self.operator == RuleOperator.GREATER_THAN:
            return num_val > target
        if self.operator == RuleOperator.LESS_THAN:
            return num_val < target
        if self.operator == RuleOperator.GREATER_OR_EQUAL:
            return num_val >= target
        if self.operator == RuleOperator.LESS_OR_EQUAL:
            return num_val <= target

        return False

    def to_dict(self) -> dict:
        return {
            "field": self.field.value,
            "operator": self.operator.value,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentRule":
        return cls(
            field=RuleField(data["field"]),
            operator=RuleOperator(data["operator"]),
            value=data.get("value"),
        )


@dataclass
class Segment:
    """A named customer segment with rules."""

    id: Optional[int] = None
    name: str = ""
    description: str = ""
    rules: List[SegmentRule] = field(default_factory=list)
    rule_logic: str = "AND"  # AND or OR
    status: SegmentStatus = SegmentStatus.DRAFT
    member_count: int = 0
    last_evaluated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        now = datetime.utcnow()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    def evaluate_customer(self, customer_metrics: dict) -> bool:
        """Evaluate all rules against a customer's metrics.

        Uses AND or OR logic based on rule_logic.
        """
        if not self.rules:
            return False

        results = [rule.evaluate(customer_metrics) for rule in self.rules]

        if self.rule_logic == "AND":
            return all(results)
        else:  # OR
            return any(results)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rules": [r.to_dict() for r in self.rules],
            "rule_logic": self.rule_logic,
            "status": self.status.value,
            "member_count": self.member_count,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
