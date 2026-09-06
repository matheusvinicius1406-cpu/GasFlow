"""
Workflow Engine — FASE 12

WorkflowDefinition, WorkflowRun, WorkflowStep with state machines.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid


# ── States ──────────────────────────────────────────────


class WorkflowStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ── Workflow Definition ─────────────────────────────────


@dataclass
class WorkflowStepDef:
    """Single step definition in a workflow."""

    id: str = ""
    name: str = ""
    action_type: str = ""  # tool_call, condition_check, approval_request, notification
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None  # Simple condition expression
    requires_approval: bool = False
    risk_level: str = "LOW"
    max_retries: int = 0
    next_step_on_success: Optional[str] = None
    next_step_on_failure: Optional[str] = None


@dataclass
class WorkflowDefinition:
    """Workflow definition — the blueprint."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: int = 1
    status: WorkflowStatus = WorkflowStatus.DRAFT
    trigger_type: str = "EVENT_TRIGGER"  # EVENT_TRIGGER, SCHEDULE_TRIGGER, MANUAL_TRIGGER
    trigger_event: Optional[str] = None  # EventType value
    schedule: Optional[str] = None  # Cron-like expression
    steps: List[WorkflowStepDef] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def first_step_id(self) -> Optional[str]:
        return self.steps[0].id if self.steps else None

    def get_step(self, step_id: str) -> Optional[WorkflowStepDef]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None


# ── Workflow Run ────────────────────────────────────────


@dataclass
class WorkflowRun:
    """Instance of a running/completed workflow."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    workflow_version: int = 1
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    current_step_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    trigger_event_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def start(self):
        self.status = WorkflowStatus.ACTIVE
        self.started_at = datetime.utcnow()

    def complete(self):
        self.status = WorkflowStatus.COMPLETED
        self.finished_at = datetime.utcnow()

    def fail(self, error: str = ""):
        self.status = WorkflowStatus.FAILED
        self.finished_at = datetime.utcnow()
        self.error = error

    def cancel(self):
        self.status = WorkflowStatus.CANCELLED
        self.finished_at = datetime.utcnow()


# ── Workflow Step Run ───────────────────────────────────


@dataclass
class WorkflowStepRun:
    """Instance of a running/completed workflow step."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""
    step_id: str = ""
    step_name: str = ""
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    approval_id: Optional[str] = None

    def start(self):
        self.status = StepStatus.RUNNING
        self.started_at = datetime.utcnow()

    def complete(self, result: Optional[Dict[str, Any]] = None):
        self.status = StepStatus.COMPLETED
        self.finished_at = datetime.utcnow()
        self.result = result

    def fail(self, error: str = ""):
        self.status = StepStatus.FAILED
        self.finished_at = datetime.utcnow()
        self.error = error

    def skip(self):
        self.status = StepStatus.SKIPPED
        self.finished_at = datetime.utcnow()

    def wait_approval(self, approval_id: str):
        self.status = StepStatus.WAITING_APPROVAL
        self.approval_id = approval_id
