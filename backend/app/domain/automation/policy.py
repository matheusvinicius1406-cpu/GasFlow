"""
Policy & Approval Engine — FASE 12

PolicyEngine: authorization, risk assessment, limits, approval requirements.
ApprovalEngine: one-time, bound, expiring approvals.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid
import hashlib


# ── Risk Levels ─────────────────────────────────────────


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ── Action Policy ───────────────────────────────────────


@dataclass
class ActionPolicy:
    """Policy for a specific action type."""

    action: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    requires_confirmation: bool = False
    allowed_roles: List[str] = field(default_factory=list)
    max_amount: Optional[float] = None  # For financial actions
    allowed_hours_start: Optional[int] = None  # 0-23
    allowed_hours_end: Optional[int] = None
    description: str = ""


# ── Policy Engine ───────────────────────────────────────


class PolicyEngine:
    """Central policy engine for authorization and risk assessment."""

    def __init__(self):
        self._policies: Dict[str, ActionPolicy] = {}
        self._kill_switch = False
        self._disabled_actions: List[str] = []

    def register_policy(self, policy: ActionPolicy):
        self._policies[policy.action] = policy

    def get_policy(self, action: str) -> Optional[ActionPolicy]:
        return self._policies.get(action)

    def check_permission(self, action: str, role: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Check if an action is permitted.
        Returns: {"allowed": bool, "requires_approval": bool, "risk_level": str, "reason": str}
        """
        if self._kill_switch:
            return {
                "allowed": False,
                "requires_approval": False,
                "risk_level": "BLOCKED",
                "reason": "Kill switch is active — all automations paused",
            }

        if action in self._disabled_actions:
            return {
                "allowed": False,
                "requires_approval": False,
                "risk_level": "BLOCKED",
                "reason": f"Action '{action}' is disabled",
            }

        policy = self._policies.get(action)
        if not policy:
            return {
                "allowed": False,
                "requires_approval": False,
                "risk_level": "UNKNOWN",
                "reason": f"No policy defined for action '{action}'",
            }

        if policy.allowed_roles and role not in policy.allowed_roles:
            return {
                "allowed": False,
                "requires_approval": False,
                "risk_level": policy.risk_level.value,
                "reason": f"Role '{role}' not permitted for action '{action}'",
            }

        # Check time restrictions
        if policy.allowed_hours_start is not None and policy.allowed_hours_end is not None:
            hour = datetime.utcnow().hour
            if not (policy.allowed_hours_start <= hour <= policy.allowed_hours_end):
                return {
                    "allowed": False,
                    "requires_approval": False,
                    "risk_level": policy.risk_level.value,
                    "reason": f"Action '{action}' not allowed at current hour ({hour})",
                }

        # Check amount limits
        if policy.max_amount and context:
            amount = context.get("amount", 0)
            if isinstance(amount, (int, float)) and amount > policy.max_amount:
                return {
                    "allowed": False,
                    "requires_approval": True,
                    "risk_level": policy.risk_level.value,
                    "reason": f"Amount {amount} exceeds limit {policy.max_amount}",
                }

        return {
            "allowed": True,
            "requires_approval": policy.requires_approval,
            "risk_level": policy.risk_level.value,
            "reason": "OK",
        }

    def activate_kill_switch(self):
        self._kill_switch = True

    def deactivate_kill_switch(self):
        self._kill_switch = False

    @property
    def is_kill_switch_active(self) -> bool:
        return self._kill_switch

    def disable_action(self, action: str):
        if action not in self._disabled_actions:
            self._disabled_actions.append(action)

    def enable_action(self, action: str):
        if action in self._disabled_actions:
            self._disabled_actions.remove(action)


# ── Approval ────────────────────────────────────────────


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Approval:
    """One-time, bound, expiring approval for an action."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: str = ""
    arguments_hash: str = ""  # Hash of action arguments for binding
    actor: str = ""  # Who requested
    workflow_id: Optional[str] = None
    run_id: Optional[str] = None
    step_id: Optional[str] = None
    risk_level: str = "LOW"
    reason: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejected_at: Optional[datetime] = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return self.status == ApprovalStatus.APPROVED and not self.is_expired


class ApprovalEngine:
    """Manages approval lifecycle."""

    DEFAULT_TTL_MINUTES = 60

    def __init__(self, ttl_minutes: int = DEFAULT_TTL_MINUTES):
        self._approvals: Dict[str, Approval] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
        self._lock = __import__("threading").Lock()

    def create_approval(
        self,
        action: str,
        arguments: Dict[str, Any],
        actor: str,
        risk_level: str = "LOW",
        reason: str = "",
        workflow_id: Optional[str] = None,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> Approval:
        """Create a new approval request."""
        args_hash = hashlib.md5(str(sorted(arguments.items())).encode()).hexdigest()[:16]

        approval = Approval(
            action=action,
            arguments_hash=args_hash,
            actor=actor,
            workflow_id=workflow_id,
            run_id=run_id,
            step_id=step_id,
            risk_level=risk_level,
            reason=reason,
            expires_at=datetime.utcnow() + self._ttl,
        )
        with self._lock:
            self._approvals[approval.id] = approval
        return approval

    def approve(self, approval_id: str, approved_by: str) -> bool:
        """Approve an approval request. One-time use."""
        with self._lock:
            approval = self._approvals.get(approval_id)
            if not approval:
                return False
            if approval.status != ApprovalStatus.PENDING:
                return False
            if approval.is_expired:
                approval.status = ApprovalStatus.EXPIRED
                return False
            approval.status = ApprovalStatus.APPROVED
            approval.approved_at = datetime.utcnow()
            approval.approved_by = approved_by
            return True

    def reject(self, approval_id: str, _rejected_by: str = "") -> bool:
        # _rejected_by: parte do contrato de auditoria; ainda não registrado.
        """Reject an approval request."""
        with self._lock:
            approval = self._approvals.get(approval_id)
            if not approval:
                return False
            if approval.status != ApprovalStatus.PENDING:
                return False
            approval.status = ApprovalStatus.REJECTED
            approval.rejected_at = datetime.utcnow()
            return True

    def is_valid(self, approval_id: str) -> bool:
        """Check if an approval is valid (approved and not expired)."""
        with self._lock:
            approval = self._approvals.get(approval_id)
            if not approval:
                return False
            return approval.is_valid

    def get_pending(self) -> List[Approval]:
        with self._lock:
            return [a for a in self._approvals.values() if a.status == ApprovalStatus.PENDING and not a.is_expired]

    def get_all(self) -> List[Approval]:
        with self._lock:
            return list(self._approvals.values())

    def expire_old(self) -> int:
        """Expire old approvals. Returns count of expired."""
        count = 0
        with self._lock:
            for approval in self._approvals.values():
                if approval.status == ApprovalStatus.PENDING and approval.is_expired:
                    approval.status = ApprovalStatus.EXPIRED
                    count += 1
        return count
