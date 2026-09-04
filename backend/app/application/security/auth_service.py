"""
Auth Service — FASE 13

Authentication, Session Management, RBAC, Tenant Context.
Authority: IDENTITY + POLICY + DOMAIN + DATABASE.
Never trust: frontend, LLM, Agent, Workflow, WhatsApp.
"""

import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import threading

from app.domain.security.models import (
    User, UserStatus, Session, SessionStatus, Tenant, TenantMembership,
    Role, SystemRole, AuditRecord, AuditAction, TenantContext,
    hash_password, verify_password, generate_token, needs_rehash,
    ROLE_PERMISSIONS, RateLimiter,
)
from app.core.config import settings


class AuthService:
    """Core authentication and authorization service.
    
    Supports two modes:
    - DB mode: when db session is provided, uses SQLAlchemy repositories
    - In-memory mode: fallback for tests and backward compatibility
    """

    SESSION_TTL_MINUTES = 60
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15
    MAX_SESSIONS_PER_USER = 5

    def __init__(self, db=None):
        self._db = db
        self._use_db = db is not None

        # In-memory fallback (always initialized for backward compat)
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

        # Default admin user (password from environment)
        admin_role = [r for r in self._roles.values() if r.system_role == SystemRole.ADMIN][0]
        admin = User(
            id="admin-001",
            username="admin",
            email="admin@gasflow.local",
            display_name="Administrator",
            password_hash=hash_password(settings.admin_password),
            status=UserStatus.ACTIVE,
        )
        self._users[admin.id] = admin
        self._users_by_username["admin"] = admin.id
        self._memberships.append(TenantMembership(
            user_id=admin.id, tenant_id="default", role_id=admin_role.id,
        ))

        # Persist to DB if available
        if self._use_db:
            self._persist_defaults_to_db()

    # ── DB Persistence Helpers ──────────────────────────

    def _persist_defaults_to_db(self):
        """Persist default tenant, roles, and admin user to DB."""
        from app.infrastructure.repositories.auth_repository import (
            SQLAlchemyTenantRepository, SQLAlchemyRoleRepository,
            SQLAlchemyUserRepository, SQLAlchemyMembershipRepository,
        )
        tenant_repo = SQLAlchemyTenantRepository(self._db)
        role_repo = SQLAlchemyRoleRepository(self._db)
        user_repo = SQLAlchemyUserRepository(self._db)
        membership_repo = SQLAlchemyMembershipRepository(self._db)

        # Persist default tenant
        if not tenant_repo.get_by_tenant_id("default"):
            tenant_repo.create("default", "GasFlow")

        # Persist default roles
        for sys_role in SystemRole:
            if not role_repo.get_by_name(sys_role.value):
                role_repo.create(
                    role_id=str(uuid.uuid4()),
                    name=sys_role.value,
                    system_role=sys_role.value,
                    permissions=ROLE_PERMISSIONS.get(sys_role, []),
                )

        # Persist default admin user
        if not user_repo.get_by_username("admin"):
            admin_role = role_repo.get_by_name("ADMIN")
            if admin_role:
                user_repo.create(
                    user_id="admin-001",
                    username="admin",
                    email="admin@gasflow.local",
                    display_name="Administrator",
                    password_hash=hash_password(settings.admin_password),
                )
                membership_repo.create("admin-001", "default", admin_role.id)

    def _get_user_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemyUserRepository
        return SQLAlchemyUserRepository(self._db)

    def _get_session_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemySessionRepository
        return SQLAlchemySessionRepository(self._db)

    def _get_tenant_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemyTenantRepository
        return SQLAlchemyTenantRepository(self._db)

    def _get_role_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemyRoleRepository
        return SQLAlchemyRoleRepository(self._db)

    def _get_membership_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemyMembershipRepository
        return SQLAlchemyMembershipRepository(self._db)

    def _get_audit_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemyAuditRepository
        return SQLAlchemyAuditRepository(self._db)

    def _db_user_to_domain(self, model) -> User:
        """Convert AuthUserModel to domain User."""
        return User(
            id=model.id,
            username=model.username,
            email=model.email,
            display_name=model.display_name,
            password_hash=model.password_hash,
            status=UserStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
            failed_login_attempts=model.failed_login_attempts,
            locked_until=model.locked_until,
        )

    def _db_session_to_domain(self, model) -> Session:
        """Convert AuthSessionModel to domain Session."""
        return Session(
            id=model.id,
            user_id=model.user_id,
            tenant_id=model.tenant_id,
            token=model.token,
            status=SessionStatus(model.status),
            created_at=model.created_at,
            expires_at=model.expires_at,
            last_seen_at=model.last_seen_at,
            revoked_at=model.revoked_at,
            ip_address=model.ip_address,
            user_agent=model.user_agent,
        )

    def _db_role_to_domain(self, model) -> Role:
        """Convert AuthRoleModel to domain Role."""
        return Role(
            id=model.id,
            name=model.name,
            system_role=SystemRole(model.system_role),
            permissions=model.permissions or [],
            created_at=model.created_at,
        )

    def _db_membership_to_domain(self, model) -> TenantMembership:
        """Convert AuthMembershipModel to domain TenantMembership."""
        return TenantMembership(
            id=model.id,
            user_id=model.user_id,
            tenant_id=model.tenant_id,
            role_id=model.role_id,
            created_at=model.created_at,
        )

    def _db_tenant_to_domain(self, model) -> Tenant:
        """Convert AuthTenantModel to domain Tenant."""
        return Tenant(
            id=model.tenant_id,
            name=model.name,
            status=model.status,
            created_at=model.created_at,
        )

    def _get_role(self, role_id: str) -> Optional[Role]:
        """Get role by ID from DB or in-memory."""
        if self._use_db:
            role_model = self._get_role_repo().get_by_id(role_id)
            return self._db_role_to_domain(role_model) if role_model else None
        return self._roles.get(role_id)

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
        if self._use_db:
            user_repo = self._get_user_repo()
            user_model = user_repo.get_by_username(username)
            user = self._db_user_to_domain(user_model) if user_model else None
        else:
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
            # Persist failed attempts to DB
            if self._use_db:
                self._get_user_repo().update(user.id,
                    failed_login_attempts=user.failed_login_attempts,
                    status=user.status.value,
                    locked_until=user.locked_until,
                )
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
        role = self._get_role(membership.role_id) if membership else None
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

        if self._use_db:
            session_repo = self._get_session_repo()
            session_repo.enforce_max_sessions(user.id, self.MAX_SESSIONS_PER_USER)
            session_repo.create(
                session_id=session.id,
                user_id=user.id,
                tenant_id=tenant_id,
                token=token,
                expires_at=session.expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            # Update user's failed attempts
            self._get_user_repo().update(user.id,
                failed_login_attempts=0,
                locked_until=None,
                password_hash=user.password_hash,
            )
        else:
            with self._lock:
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
        if self._use_db:
            session_repo = self._get_session_repo()
            session_model = session_repo.get_by_token(token)
            if not session_model:
                return False
            session_repo.revoke(session_model.id)
            self._audit(session_model.user_id, session_model.tenant_id,
                        AuditAction.SESSION_REVOKED.value, result="SUCCESS")
            return True
        else:
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

        if self._use_db:
            session_repo = self._get_session_repo()
            session_model = session_repo.get_by_token(token)
            if not session_model:
                return None
            # Check expiry
            if session_model.expires_at and datetime.utcnow() > session_model.expires_at:
                return None

            user_repo = self._get_user_repo()
            user_model = user_repo.get_by_id(session_model.user_id)
            if not user_model:
                return None
            user = self._db_user_to_domain(user_model)
            if not user.is_active:
                return None

            # Get role and permissions
            membership = self._get_membership(user.id, session_model.tenant_id)
            role = self._get_role(membership.role_id) if membership else None
            system_role = role.system_role if role else SystemRole.OPERATOR
            permissions = set(role.permissions) if role else set()

            # Update last seen
            session_repo.update_last_seen(session_model.id)

            return TenantContext(
                user_id=user.id,
                tenant_id=session_model.tenant_id,
                role=system_role,
                permissions=permissions,
                session_id=session_model.id,
            )
        else:
            session_id = self._sessions_by_token.get(token)
            if not session_id:
                return None
            session = self._sessions.get(session_id)
            if not session or not session.is_valid:
                return None
            user = self._users.get(session.user_id)
            if not user or not user.is_active:
                return None
            membership = self._get_membership(user.id, session.tenant_id)
            role = self._get_role(membership.role_id) if membership else None
            system_role = role.system_role if role else SystemRole.OPERATOR
            permissions = set(role.permissions) if role else set()
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
        if self._use_db:
            user_repo = self._get_user_repo()
            if user_repo.get_by_username(username):
                return {"success": False, "error": "Username already exists"}
            role_repo = self._get_role_repo()
            role = role_repo.get_by_name(role_name)
            if not role:
                return {"success": False, "error": f"Role '{role_name}' not found"}
            import uuid
            user_id = str(uuid.uuid4())
            user_repo.create(
                user_id=user_id,
                username=username,
                email=email,
                display_name=display_name or username,
                password_hash=hash_password(password),
            )
            self._get_membership_repo().create(user_id, tenant_id, role.id)
            self._audit(user_id, tenant_id, AuditAction.USER_CREATED.value, result="SUCCESS")
            return {"success": True, "user_id": user_id}
        else:
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
        if self._use_db:
            user_repo = self._get_user_repo()
            user_model = user_repo.get_by_id(user_id)
            if not user_model:
                return {"success": False, "error": "User not found"}
            if not verify_password(old_password, user_model.password_hash):
                return {"success": False, "error": "Current password is incorrect"}
            user_repo.update(user_id, password_hash=hash_password(new_password))
            self._audit(user_id, "default", AuditAction.PASSWORD_CHANGED.value, result="SUCCESS")
            return {"success": True}
        else:
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
        role = self._get_role(membership.role_id) if membership else None
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
        if self._use_db:
            self._get_audit_repo().create(
                actor_id=actor_id,
                tenant_id=tenant_id,
                action=action,
                result=result,
                resource=resource,
                resource_id=resource_id,
                ip_address=ip,
                details=details,
            )
        else:
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
        if self._use_db:
            models = self._get_audit_repo().list_for_tenant(tenant_id or "", limit)
            return [AuditRecord(
                id=m.id, actor_id=m.actor_id, tenant_id=m.tenant_id,
                action=m.action, resource=m.resource, result=m.result,
                timestamp=m.timestamp, ip_address=m.ip_address,
                details=m.details or {},
            ) for m in models]
        with self._lock:
            log = self._audit_log
            if tenant_id:
                log = [r for r in log if r.tenant_id == tenant_id]
            return log[-limit:]

    # ── Helpers ──────────────────────────────────────────

    def _get_membership(self, user_id: str, tenant_id: Optional[str] = None) -> Optional[TenantMembership]:
        if self._use_db:
            membership_repo = self._get_membership_repo()
            if tenant_id:
                model = membership_repo.get(user_id, tenant_id)
            else:
                model = membership_repo.get_first_for_user(user_id)
            return self._db_membership_to_domain(model) if model else None
        else:
            if tenant_id:
                for m in self._memberships:
                    if m.user_id == user_id and m.tenant_id == tenant_id:
                        return m
                return None
            for m in self._memberships:
                if m.user_id == user_id:
                    return m
            return None

    def get_user(self, user_id: str) -> Optional[User]:
        if self._use_db:
            user_model = self._get_user_repo().get_by_id(user_id)
            return self._db_user_to_domain(user_model) if user_model else None
        return self._users.get(user_id)

    def get_users(self, tenant_id: str = "default") -> List[User]:
        if self._use_db:
            models = self._get_user_repo().list_by_tenant(tenant_id)
            return [self._db_user_to_domain(m) for m in models]
        member_ids = {m.user_id for m in self._memberships if m.tenant_id == tenant_id}
        return [u for uid, u in self._users.items() if uid in member_ids]

    def get_roles(self) -> List[Role]:
        if self._use_db:
            models = self._get_role_repo().list_all()
            return [self._db_role_to_domain(m) for m in models]
        return list(self._roles.values())

    def create_tenant(self, tenant_id: str, name: str, creator_user_id: str = "") -> Dict[str, Any]:
        """Create a new tenant and optionally add creator as ADMIN."""
        if self._use_db:
            tenant_repo = self._get_tenant_repo()
            if tenant_repo.get_by_tenant_id(tenant_id):
                return {"success": False, "error": f"Tenant '{tenant_id}' already exists"}
            tenant_repo.create(tenant_id, name)
            # If creator provided, add them as ADMIN to this tenant
            if creator_user_id:
                role_repo = self._get_role_repo()
                admin_role = role_repo.get_by_name("ADMIN")
                if admin_role:
                    self._get_membership_repo().create(creator_user_id, tenant_id, admin_role.id)
            self._audit(creator_user_id or "system", tenant_id,
                        AuditAction.TENANT_CREATED.value, result="SUCCESS")
            return {"success": True, "tenant_id": tenant_id}
        else:
            if tenant_id in self._tenants:
                return {"success": False, "error": f"Tenant '{tenant_id}' already exists"}
            tenant = Tenant(id=tenant_id, name=name)
            self._tenants[tenant_id] = tenant
            if creator_user_id:
                user = self._users.get(creator_user_id)
                if user:
                    admin_role = next(
                        (r for r in self._roles.values() if r.system_role == SystemRole.ADMIN), None
                    )
                    if admin_role:
                        self._memberships.append(TenantMembership(
                            user_id=creator_user_id, tenant_id=tenant_id, role_id=admin_role.id,
                        ))
            self._audit(creator_user_id or "system", tenant_id,
                        AuditAction.TENANT_CREATED.value, result="SUCCESS")
            return {"success": True, "tenant_id": tenant_id}

    def get_tenants(self) -> List[Tenant]:
        """List all tenants."""
        if self._use_db:
            models = self._get_tenant_repo().list_all()
            return [self._db_tenant_to_domain(m) for m in models]
        return list(self._tenants.values())

    def get_active_sessions(self, user_id: str) -> List[Session]:
        if self._use_db:
            models = self._get_session_repo().list_active_for_user(user_id)
            return [self._db_session_to_domain(m) for m in models]
        return [s for s in self._sessions.values()
                if s.user_id == user_id and s.status == SessionStatus.ACTIVE]

    def revoke_all_sessions(self, user_id: str) -> int:
        if self._use_db:
            return self._get_session_repo().revoke_all_for_user(user_id)
        count = 0
        for s in self._sessions.values():
            if s.user_id == user_id and s.status == SessionStatus.ACTIVE:
                s.revoke()
                count += 1
        return count

    def expire_old_sessions(self) -> int:
        if self._use_db:
            return self._get_session_repo().expire_old()
        count = 0
        for s in self._sessions.values():
            if s.status == SessionStatus.ACTIVE and s.expires_at and datetime.utcnow() > s.expires_at:
                s.status = SessionStatus.EXPIRED
                count += 1
        return count
