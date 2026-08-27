"""
Agent Runtime — FASE 12

AgentDefinition, AgentRun, AgentStep with planning, permissions, and risk ceiling.
Agents NEVER access DB directly — only through tools → use cases → domain.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid


# ── Agent States ────────────────────────────────────────

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class AgentScope(str, Enum):
    CUSTOMER_AGENT = "CUSTOMER_AGENT"
    SALES_AGENT = "SALES_AGENT"
    INVENTORY_AGENT = "INVENTORY_AGENT"
    FINANCE_AGENT = "FINANCE_AGENT"
    SUPPORT_AGENT = "SUPPORT_AGENT"


# ── Agent Definition ────────────────────────────────────

@dataclass
class AgentDefinition:
    """Agent blueprint — defines capabilities and limits."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    scope: AgentScope = AgentScope.SUPPORT_AGENT
    version: int = 1
    enabled: bool = True

    # Permissions
    allowed_tools: List[str] = field(default_factory=list)
    risk_ceiling: str = "MEDIUM"  # MAX risk level this agent can perform
    max_steps: int = 10
    max_replans: int = 2

    # Policy
    requires_approval_above: str = "MEDIUM"  # Risk levels above this need approval
    allowed_roles: List[str] = field(default_factory=lambda: ["OPERATOR"])

    # Limits
    max_tool_calls_per_run: int = 20
    max_tokens_per_run: int = 10000

    created_at: datetime = field(default_factory=datetime.utcnow)


# ── Agent Run ───────────────────────────────────────────

@dataclass
class AgentRun:
    """Instance of an agent execution."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    agent_version: int = 1
    status: AgentStatus = AgentStatus.IDLE
    goal: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    trigger_event_id: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    tool_calls_count: int = 0
    replans_count: int = 0

    def start(self):
        self.status = AgentStatus.PLANNING
        self.started_at = datetime.utcnow()

    def begin_execution(self):
        self.status = AgentStatus.EXECUTING

    def complete(self, result: Optional[Dict[str, Any]] = None):
        self.status = AgentStatus.COMPLETED
        self.finished_at = datetime.utcnow()
        self.result = result

    def fail(self, error: str = ""):
        self.status = AgentStatus.FAILED
        self.finished_at = datetime.utcnow()
        self.error = error

    def stop(self):
        self.status = AgentStatus.STOPPED
        self.finished_at = datetime.utcnow()


# ── Agent Step ──────────────────────────────────────────

@dataclass
class AgentStep:
    """Single step in an agent execution."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""
    step_number: int = 0
    description: str = ""
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def start(self):
        self.status = "RUNNING"
        self.started_at = datetime.utcnow()

    def complete(self, result: Optional[Dict[str, Any]] = None):
        self.status = "COMPLETED"
        self.finished_at = datetime.utcnow()
        self.result = result

    def fail(self, error: str = ""):
        self.status = "FAILED"
        self.finished_at = datetime.utcnow()
        self.error = error


# ── Agent Scope Definitions ─────────────────────────────

AGENT_SCOPE_CONFIGS = {
    AgentScope.CUSTOMER_AGENT: {
        "allowed_tools": ["get_customer", "search_customers", "get_customer_360", "get_order"],
        "risk_ceiling": "LOW",
        "description": "Customer lookup and 360 view",
    },
    AgentScope.SALES_AGENT: {
        "allowed_tools": ["get_customer", "search_customers", "get_customer_360",
                          "get_inventory", "search_products", "get_order", "create_order"],
        "risk_ceiling": "MEDIUM",
        "description": "Sales assistance and order creation",
    },
    AgentScope.INVENTORY_AGENT: {
        "allowed_tools": ["get_inventory", "get_low_stock", "get_inventory_summary", "search_products"],
        "risk_ceiling": "LOW",
        "description": "Inventory monitoring and alerts",
    },
    AgentScope.FINANCE_AGENT: {
        "allowed_tools": ["get_payments", "get_receivables", "get_financial_summary", "get_sales_summary"],
        "risk_ceiling": "LOW",
        "description": "Financial reporting and monitoring",
    },
    AgentScope.SUPPORT_AGENT: {
        "allowed_tools": ["get_customer", "get_order", "get_inventory", "get_payments"],
        "risk_ceiling": "LOW",
        "description": "Customer support assistance",
    },
}
