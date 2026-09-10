"""
Security Domain Models — FASE 13

Identity, Authentication, Authorization, Multi-Tenancy, Audit.
Authority lives in: IDENTITY + POLICY + DOMAIN + DATABASE.
Never in frontend, LLM, Agent, Workflow, or WhatsApp.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import uuid
import hashlib
import secrets
import bcrypt


# ── User ────────────────────────────────────────────────


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"


@dataclass
class User:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    email: str = ""
    display_name: str = ""
    password_hash: str = ""
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None

    @property
    def is_locked(self) -> bool:
        if self.locked_until and datetime.utcnow() < self.locked_until:
            return True
        return False

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE and not self.is_locked


# ── Session ─────────────────────────────────────────────


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    tenant_id: str = ""
    token: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    ip_address: str = ""
    user_agent: str = ""

    @property
    def is_valid(self) -> bool:
        if self.status != SessionStatus.ACTIVE:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    def revoke(self):
        self.status = SessionStatus.REVOKED
        self.revoked_at = datetime.utcnow()


# ── Tenant ──────────────────────────────────────────────


@dataclass
class Tenant:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    status: str = "ACTIVE"
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TenantMembership:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    tenant_id: str = ""
    role_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


# ── Role ────────────────────────────────────────────────


class SystemRole(str, Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    OPERATOR = "OPERATOR"
    DRIVER = "DRIVER"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"


@dataclass
class Role:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    system_role: SystemRole = SystemRole.OPERATOR
    permissions: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


# ── Permission ──────────────────────────────────────────


@dataclass
class Permission:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource: str = ""  # customer, order, inventory, etc.
    action: str = ""  # read, write, create, update, delete, approve
    description: str = ""

    @property
    def codename(self) -> str:
        return f"{self.resource}.{self.action}"


# ── Audit ───────────────────────────────────────────────


class AuditAction(str, Enum):
    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAILURE = "AUTH_FAILURE"
    AUTH_LOCKOUT = "AUTH_LOCKOUT"
    ACCESS_DENIED = "ACCESS_DENIED"
    ROLE_CHANGED = "ROLE_CHANGED"
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"
    SENSITIVE_ACTION = "SENSITIVE_ACTION"
    APPROVAL_CREATED = "APPROVAL_CREATED"
    APPROVAL_USED = "APPROVAL_USED"
    SESSION_REVOKED = "SESSION_REVOKED"
    USER_CREATED = "USER_CREATED"
    USER_DISABLED = "USER_DISABLED"
    TENANT_CREATED = "TENANT_CREATED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    RESOURCE_ACCESSED = "RESOURCE_ACCESSED"
    RESOURCE_MODIFIED = "RESOURCE_MODIFIED"
    WORKFLOW_EXECUTED = "WORKFLOW_EXECUTED"
    AGENT_EXECUTED = "AGENT_EXECUTED"


@dataclass
class AuditRecord:
    """Immutable audit record — append-only."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actor_id: str = ""
    actor_type: str = "USER"  # USER, AGENT, WORKFLOW, SYSTEM
    tenant_id: str = ""
    action: str = ""
    resource: str = ""
    resource_id: str = ""
    result: str = ""  # SUCCESS, DENIED, ERROR
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ip_address: str = ""
    user_agent: str = ""
    correlation_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# ── Tenant Context ──────────────────────────────────────


@dataclass
class TenantContext:
    """Request-scoped tenant context — never global mutable."""

    user_id: str = ""
    tenant_id: str = ""
    role: SystemRole = SystemRole.OPERATOR
    permissions: Set[str] = field(default_factory=set)
    session_id: str = ""

    @property
    def is_authenticated(self) -> bool:
        return bool(self.user_id)

    def has_permission(self, permission: str) -> bool:
        if "admin.*" in self.permissions:
            return True
        if permission in self.permissions:
            return True
        # Wildcard support: "order.*" concede "order.read" (e subníveis);
        # "admin.*" concede tudo. Antes havia só match exato + admin.*,
        # o que tornava permissões curinga dos roles inoperantes.
        prefix = permission.rsplit(".", 1)[0] if "." in permission else ""
        while prefix:
            if f"{prefix}.*" in self.permissions:
                return True
            prefix = prefix.rsplit(".", 1)[0] if "." in prefix else ""
        return False

    def has_any_permission(self, *perms: str) -> bool:
        return any(self.has_permission(p) for p in perms)


# ── Default Permissions ─────────────────────────────────

DEFAULT_PERMISSIONS = [
    # Customer
    ("customer", "read"),
    ("customer", "write"),
    ("customer", "create"),
    # Order
    ("order", "read"),
    ("order", "create"),
    ("order", "update"),
    ("order", "cancel"),
    # Product
    ("product", "read"),
    ("product", "write"),
    ("product", "create"),
    # Inventory
    ("inventory", "read"),
    ("inventory", "adjust"),
    # Finance
    ("finance", "read"),
    ("finance", "receive"),
    ("finance", "refund"),
    # WhatsApp
    ("whatsapp", "read"),
    ("whatsapp", "send"),
    ("whatsapp", "takeover"),
    # Conversation
    ("conversation", "read"),
    ("conversation", "takeover"),
    # Workflow
    ("workflow", "read"),
    ("workflow", "execute"),
    # Agent
    ("agent", "read"),
    ("agent", "execute"),
    # Automation
    ("automation", "read"),
    ("automation", "pause"),
    # User Management
    ("user", "read"),
    ("user", "create"),
    ("user", "update"),
    # Settings (quadro de configurações)
    ("settings", "read"),
    ("settings", "write"),
    # Coupons (promoções e cupons)
    ("coupon", "read"),
    ("coupon", "write"),
    # Integrations (sites de revendas — agente de ancoragem)
    ("integration", "read"),
    ("integration", "write"),
    # Admin
    ("admin", "*"),
]


# ── Default Role Permissions ────────────────────────────

ROLE_PERMISSIONS = {
    SystemRole.ADMIN: ["admin.*"],
    SystemRole.MANAGER: [
        "customer.*",
        "order.*",
        "product.*",
        "inventory.*",
        "finance.*",
        "whatsapp.*",
        "conversation.*",
        "workflow.*",
        "agent.*",
        "automation.*",
        "user.read",
        "settings.read",
        "coupon.*",
        "integration.*",
    ],
    SystemRole.OPERATOR: [
        "customer.read",
        "customer.write",
        "order.read",
        "order.create",
        "order.update",
        "product.read",
        "inventory.read",
        "finance.read",
        "whatsapp.read",
        "whatsapp.send",
        "whatsapp.takeover",
        "conversation.read",
        "conversation.takeover",
        "coupon.read",
        "settings.read",
    ],
    SystemRole.DRIVER: [
        "customer.read",
        "order.read",
        "delivery.read.assigned",
        "delivery.accept",
        "delivery.start",
        "delivery.arrive",
        "delivery.complete",
        "delivery.fail",
        "route.read.assigned",
        "location.write.self",
        "proof.write.assigned",
    ],
    SystemRole.CUSTOMER: [
        "order.read",
        "product.read",
    ],
    SystemRole.SYSTEM: ["admin.*"],
}


# ── Password Security ───────────────────────────────────


def hash_password(password: str) -> str:
    """Hash password using bcrypt.
    Returns bcrypt hash string.
    Detects legacy SHA-256 hashes (contain ':') and rehashes transparently."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return f"bcrypt:{hashed.decode('utf-8')}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash. Supports bcrypt and legacy SHA-256."""
    if password_hash.startswith("bcrypt:"):
        actual_hash = password_hash[7:]  # Remove 'bcrypt:' prefix
        return bcrypt.checkpw(password.encode("utf-8"), actual_hash.encode("utf-8"))
    # Legacy SHA-256 migration path
    if ":" in password_hash:
        salt, hashed = password_hash.split(":", 1)
        return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest() == hashed
    return False


def needs_rehash(password_hash: str) -> bool:
    """Check if password hash needs to be upgraded to bcrypt."""
    return not password_hash.startswith("bcrypt:")


# ── Token Generation ────────────────────────────────────


def generate_token(user_id: str, tenant_id: str, _expires_minutes: int = 60) -> str:
    # _expires_minutes: reservado para tokens com TTL próprio (hoje o token
    # não carrega expiração embutida).
    """Generate a cryptographically secure session token."""
    random_part = secrets.token_hex(32)  # 256 bits of entropy
    payload = f"{user_id}:{tenant_id}:{random_part}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ── Rate Limiting ───────────────────────────────────────


class RateLimiter:
    """In-memory rate limiter."""

    def __init__(self):
        self._buckets: Dict[str, List[float]] = {}
        self._lock = __import__("threading").Lock()

    def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Returns True if request is allowed."""
        now = __import__("time").time()
        with self._lock:
            bucket = self._buckets.get(key, [])
            cutoff = now - window_seconds
            bucket = [t for t in bucket if t > cutoff]
            if len(bucket) >= max_requests:
                self._buckets[key] = bucket
                return False
            bucket.append(now)
            self._buckets[key] = bucket
            return True

    def reset(self, key: str):
        with self._lock:
            self._buckets.pop(key, None)
