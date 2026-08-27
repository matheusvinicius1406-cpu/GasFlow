"""
Trigger & Condition Engine — FASE 12

Triggers: event-based, schedule-based, manual, webhook.
Conditions: deterministic, no eval/exec.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import re


# ── Trigger ─────────────────────────────────────────────

class TriggerType(str, Enum):
    EVENT_TRIGGER = "EVENT_TRIGGER"
    SCHEDULE_TRIGGER = "SCHEDULE_TRIGGER"
    MANUAL_TRIGGER = "MANUAL_TRIGGER"
    WEBHOOK_TRIGGER = "WEBHOOK_TRIGGER"


@dataclass
class Trigger:
    """Workflow trigger definition."""
    id: str = ""
    trigger_type: TriggerType = TriggerType.EVENT_TRIGGER
    event_type: Optional[str] = None  # EventType value for event triggers
    schedule: Optional[str] = None  # Cron expression for schedule triggers
    conditions: List[str] = field(default_factory=list)  # Condition expressions
    enabled: bool = True
    workflow_id: Optional[str] = None


# ── Condition Engine ────────────────────────────────────

class ConditionOperator(str, Enum):
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    EQ = "eq"
    NE = "ne"
    CONTAINS = "contains"
    IN = "in"


@dataclass
class Condition:
    """Deterministic condition — no LLM, no eval."""
    field: str = ""
    operator: ConditionOperator = ConditionOperator.EQ
    value: Any = None


def evaluate_condition(condition: Condition, context: Dict[str, Any]) -> bool:
    """
    Evaluate a condition against context data.
    Deterministic — no LLM, no eval, no arbitrary code.
    """
    # Navigate nested fields with dot notation
    parts = condition.field.split(".")
    current = context
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return False

    if current is None:
        return False

    try:
        val = condition.value
        # Type coercion for comparison
        if isinstance(current, (int, float)) and isinstance(val, str):
            val = float(val)
        elif isinstance(current, str) and isinstance(val, (int, float)):
            current = str(current)

        op = condition.operator
        if op == ConditionOperator.LT:
            return current < val
        elif op == ConditionOperator.LE:
            return current <= val
        elif op == ConditionOperator.GT:
            return current > val
        elif op == ConditionOperator.GE:
            return current >= val
        elif op == ConditionOperator.EQ:
            return current == val
        elif op == ConditionOperator.NE:
            return current != val
        elif op == ConditionOperator.CONTAINS:
            return str(val) in str(current)
        elif op == ConditionOperator.IN:
            return current in val if isinstance(val, (list, set, dict)) else False
    except (TypeError, ValueError):
        return False

    return False


def evaluate_conditions(conditions: List[Condition], context: Dict[str, Any]) -> bool:
    """All conditions must be true (AND logic)."""
    return all(evaluate_condition(c, context) for c in conditions)
