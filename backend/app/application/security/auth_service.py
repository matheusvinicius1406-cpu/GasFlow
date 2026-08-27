"""
Auth Service — FASE 13

Authentication, Session Management, RBAC, Tenant Context.
Authority: IDENTITY + POLICY + DOMAIN + DATABASE.
Never trust: frontend, LLM, Agent, Workflow, WhatsApp.
"""

import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import threading

from app.domain.security.models import (
    User, UserStatus, Session, SessionStatus, Tenant, TenantMembership,
    Role, SystemRole, AuditRecord, AuditAction, TenantContext,
    hash_password, verify_password, generate_token, needs_rehash,
    ROLE_PERMISSIONS, RateLimiter,
)


class AuthService:
    """Core authentication and authorization service."""

    SESSION_TTL_MINUTES = 60
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15
    MAX_SESSIONS_PER_USER = 5

    def __init__(self):
        self._users: Dict[str, User] = {}  # id -> User
        self._users_by_username: Dict[str, str] = {}  # username -> id
        self._sessions: Dict[str, Session] = {}  # id -> Session
        self._sessions_by_token: Dict[str, str] = {}  # token -> session_id
        self._tenants: Dict[str, Tenant] = {}
        self._memberships: List[TenantMembership] = []
        self._roles: Dict[str, Role] = {}
        self._audit_log: List[AuditRecord] = []
        self._rate_limiter = RateLimiter()
        self._lock = threading.Lock()

        # Initialize defaults
        self._init_defaults()

    def _init_defaults(self):
        """Create default tenant, roles, and admin user."""
        # Default tenant
        tenant = Tenant(id="default", name="GasFlow")
        self._tenants["default"] = tenant

        # Default roles
        for sys_role in SystemRole:
            role = Role(
                name=sys_role.value,
                system_role=sys_role,
                permissions=ROLE_PERMISSIONS.get(sys_role, []),
            )
            self._roles[role.id] = role

        # Default admin user
        admin_role = [r for r in self._roles.values() if r.system_role == SystemRole.ADMIN][0]
        admin = User(
            id="admin-001",
            username="admin",
            email="admin@gasflow.local",
            display_name="Administrator",
            password_hash=hash_password("admin123"),
            status=UserStatus.ACTIVE,
        )
        self._users[admin.id] = admin
        self._users_by_username["admin"] = admin.id
        self._memberships.append(TenantMembership(
            user_id=admin.id, tenant_id="default", role_id=admin_role.id,
        ))

    # ── Authentication ───────────────────────────────────

    def login(self, username: str, password: str, ip_address: str = "",
              user_agent: str = "") -> Dict[str, Any]:
        """Authenticate user and create session.
        Generic error messages prevent user enumeration."""
        GENERIC_ERROR = "Invalid credentials."

        # Rate limit check
        if not self._rate_limiter.check(f"login:{username}", 5, 300):
            self._audit(username, "default", AuditAction.AUTH_FAILURE.value, result="RATE_LIMITED",
                        ip=ip_address)
            return {"success": False, "error": "Too many login attempts. Try again later."}

        # Find user
        user_id = self._users_by_username.get(username)
        user = self._users.get(user_id) if user_id else None

        if not user:
            self._audit(username or "unknown", "default", AuditAction.AUTH_FAILURE.value,
                        result="USER_NOT_FOUND", ip=ip_address)
            # Constant-time: run bcrypt to prevent timing attacks
            import bcrypt as _bcrypt
            _bcrypt.hashpw(b"dummy", _bcrypt.gensalt())
            return {"success": False, "error": GENERIC_ERROR}

        # Check status — same error message
        if user.status == UserStatus.DISABLED:
            return {"success": False, "error": GENERIC_ERROR}
        if user.is_locked:
            return {"success": False, "error": "Account is temporarily locked. Try again later."}

        # Verify password
        if not verify_password(password, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.MAX_FAILED_ATTEMPTS:
                user.status = UserStatus.LOCKED
                user.locked_until = datetime.utcnow() + timedelta(minutes=self.LOCKOUT_MINUTES)
                self._audit(user.id, "default", AuditAction.AUTH_LOCKOUT.value, result="LOCKED",
                            ip=ip_address)
            self._audit(user.id, "default", AuditAction.AUTH_FAILURE.value, result="WRONG_PASSWORD",
                        ip=ip_address)
            return {"success": False, "error": GENERIC_ERROR}

        # Reset failed attempts
        user.failed_login_attempts = 0
        user.locked_until = None

        # Rehash password if using legacy format
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        # Get tenant and role
        membership = self._get_membership(user.id)
        tenant_id = membership.tenant_id if membership else "default"
        role = self._roles.get(membership.role_id) if membership else None
        system_role = role.system_role if role else SystemRole.OPERATOR
        permissions = set(role.permissions) if role else set()

        # Create session
        token = generate_token(user.id, tenant_id)
        session = Session(
            user_id=user.id,
            tenant_id=tenant_id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(minutes=self.SESSION_TTL_MINUTES),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        with self._lock:
            # Enforce max sessions
            user_sessions = [s for s in self._sessions.values()
                             if s.user_id == user.id and s.status == SessionStatus.ACTIVE]
            if len(user_sessions) >= self.MAX_SESSIONS_PER_USER:
                oldest = user_sessions[0]
                oldest.revoke()

            self._sessions[session.id] = session
            self._sessions_by_token[token] = session.id

        self._audit(user.id, tenant_id, AuditAction.AUTH_SUCCESS.value, result="SUCCESS",
                    ip=ip_address)

        return {
            "success": True,
            "token": token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
            },
            "tenant_id": tenant_id,
            "role": system_role.value,
            "expires_at": session.expires_at.isoformat(),
        }

    def logout(self, token: str) -> bool:
        """Revoke a session."""
        session_id = self._sessions_by_token.get(token)
        if not session_id:
            return False
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.revoke()
        self._audit(session.user_id, session.tenant_id, AuditAction.SESSION_REVOKED.value,
                    result="SUCCESS")
        return True

    def validate_token(self, token: str) -> Optional[TenantContext]:
        """Validate token and return tenant context."""
        if not token:
            return None

        session_id = self._sessions_by_token.get(token)
        if not session_id:
            return None

        session = self._sessions.get(session_id)
        if not session or not session.is_valid:
            return None

        user = self._users.get(session.user_id)
        if not user or not user.is_active:
            return None

        # Get role and permissions
        membership = self._get_membership(user.id, session.tenant_id)
        role = self._roles.get(membership.role_id) if membership else None
        system_role = role.system_role if role else SystemRole.OPERATOR
        permissions = set(role.permissions) if role else set()

        # Update last seen
        session.last_seen_at = datetime.utcnow()

        return TenantContext(
            user_id=user.id,
            tenant_id=session.tenant_id,
            role=system_role,
            permissions=permissions,
            session_id=session.id,
        )

    # ── RBAC ─────────────────────────────────────────────

    def check_permission(self, ctx: TenantContext, permission: str) -> bool:
        """Check if context has permission."""
        if not ctx.is_authenticated:
            return False
        return ctx.has_permission(permission)

    def check_resource_access(self, ctx: TenantContext, resource_tenant_id: str) -> bool:
        """Check if context can access a tenant-scoped resource."""
        if not ctx.is_authenticated:
            return False
        return ctx.tenant_id == resource_tenant_id

    # ── User Management ──────────────────────────────────

    def create_user(self, username: str, email: str, password: str,
                    display_name: str = "", role_name: str = "OPERATOR",
                    tenant_id: str = "default") -> Dict[str, Any]:
        """Create a new user."""
        if username in self._users_by_username:
            return {"success": False, "error": "Username already exists"}

        role = next((r for r in self._roles.values() if r.name == role_name), None)
        if not role:
            return {"success": False, "error": f"Role '{role_name}' not found"}

        user = User(
            username=username,
            email=email,
            display_name=display_name or username,
            password_hash=hash_password(password),
        )
        with self._lock:
            self._users[user.id] = user
            self._users_by_username[username] = user.id
            self._memberships.append(TenantMembership(
                user_id=user.id, tenant_id=tenant_id, role_id=role.id,
            ))

        self._audit(user.id, tenant_id, AuditAction.USER_CREATED.value, result="SUCCESS")
        return {"success": True, "user_id": user.id}

    def change_password(self, user_id: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """Change user password. Rehashes to bcrypt."""
        user = self._users.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        if not verify_password(old_password, user.password_hash):
            return {"success": False, "error": "Current password is incorrect"}
        user.password_hash = hash_password(new_password)
        self._audit(user_id, "default", AuditAction.PASSWORD_CHANGED.value, result="SUCCESS")
        return {"success": True}

    def get_user_context(self, user_id: str, tenant_id: str = "default") -> Optional[TenantContext]:
        """Get tenant context for a user."""
        user = self._users.get(user_id)
        if not user or not user.is_active:
            return None
        membership = self._get_membership(user_id, tenant_id)
        role = self._roles.get(membership.role_id) if membership else None
        return TenantContext(
            user_id=user.id,
            tenant_id=tenant_id,
            role=role.system_role if role else SystemRole.OPERATOR,
            permissions=set(role.permissions) if role else set(),
        )

    # ── Audit ────────────────────────────────────────────

    def _audit(self, actor_id: str, tenant_id: str, action: str,
               result: str = "SUCCESS", resource: str = "", resource_id: str = "",
               ip: str = "", details: Optional[Dict] = None):
        record = AuditRecord(
            actor_id=actor_id,
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            result=result,
            ip_address=ip,
            details=details or {},
        )
        with self._lock:
            self._audit_log.append(record)

    def get_audit_log(self, tenant_id: Optional[str] = None, limit: int = 50) -> List[AuditRecord]:
        with self._lock:
            log = self._audit_log
            if tenant_id:
                log = [r for r in log if r.tenant_id == tenant_id]
            return log[-limit:]

    # ── Helpers ──────────────────────────────────────────

    def _get_membership(self, user_id: str, tenant_id: str = "default") -> Optional[TenantMembership]:
        for m in self._memberships:
            if m.user_id == user_id and m.tenant_id == tenant_id:
                return m
        return None

    def get_user(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def get_users(self, tenant_id: str = "default") -> List[User]:
        member_ids = {m.user_id for m in self._memberships if m.tenant_id == tenant_id}
        return [u for uid, u in self._users.items() if uid in member_ids]

    def get_roles(self) -> List[Role]:
        return list(self._roles.values())

    def get_active_sessions(self, user_id: str) -> List[Session]:
        return [s for s in self._sessions.values()
                if s.user_id == user_id and s.status == SessionStatus.ACTIVE]

    def revoke_all_sessions(self, user_id: str) -> int:
        count = 0
        for s in self._sessions.values():
            if s.user_id == user_id and s.status == SessionStatus.ACTIVE:
                s.revoke()
                count += 1
        return count

    def expire_old_sessions(self) -> int:
        count = 0
        for s in self._sessions.values():
            if s.status == SessionStatus.ACTIVE and s.expires_at and datetime.utcnow() > s.expires_at:
                s.status = SessionStatus.EXPIRED
                count += 1
        return count
