"""
Auth Service — FASE 13

Authentication, Session Management, RBAC, Tenant Context.
Authority: IDENTITY + POLICY + DOMAIN + DATABASE.
Never trust: frontend, LLM, Agent, Workflow, WhatsApp.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("gasflow.security")
from datetime import datetime, timedelta
import threading
import functools

from app.domain.security.models import (
    User,
    UserStatus,
    Session,
    SessionStatus,
    Tenant,
    TenantMembership,
    Role,
    SystemRole,
    AuditRecord,
    AuditAction,
    TenantContext,
    hash_password,
    verify_password,
    generate_token,
    needs_rehash,
    ROLE_PERMISSIONS,
    RateLimiter,
)
from app.application.security import operator_token
from app.core.config import settings


def _db_synchronized(fn):
    """Serialize DB-touching operations on the shared singleton session.

    The service is instantiated once per process (get_auth_service) and holds
    a single SQLAlchemy Session. FastAPI serves requests from a threadpool
    (plus the async WebSocket loop), so concurrent requests otherwise run
    queries/commits on the same Session from different threads — SQLAlchemy
    Sessions are not thread-safe and interleaved transactions corrupt the
    internal transaction state (e.g. raises "session is in 'prepared' state",
    returning 500 for every subsequent request). Holding a lock per operation
    and rolling back on error keeps the shared session consistent.
    """

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            try:
                return fn(self, *args, **kwargs)
            except Exception:
                if self._use_db:
                    try:
                        self._db.rollback()
                    except Exception:
                        # Rollback de limpeza falhou — registra e propaga o erro original.
                        logger.debug("auth.session.rollback_failed", exc_info=True)
                raise

    return wrapper


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
        # RLock: _db_synchronized decorates the public methods; in-memory paths
        # also take self._lock internally, so reentrancy must be allowed.
        self._lock = threading.RLock()

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
        self._memberships.append(
            TenantMembership(
                user_id=admin.id,
                tenant_id="default",
                role_id=admin_role.id,
            )
        )

        # Persist to DB if available
        if self._use_db:
            self._persist_defaults_to_db()

    # ── DB Persistence Helpers ──────────────────────────

    def _persist_defaults_to_db(self):
        """Persist default tenant, roles, and admin user to DB."""
        from app.infrastructure.repositories.auth_repository import (
            SQLAlchemyTenantRepository,
            SQLAlchemyRoleRepository,
            SQLAlchemyUserRepository,
            SQLAlchemyMembershipRepository,
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
        else:
            # ADMIN_PASSWORD é autoritativa a cada boot: se a senha do env
            # mudou (ex.: GasFlow Desktop regenerando settings.json), sincroniza
            # o hash persistido — sem isso o login ignora a nova senha.
            admin_user = user_repo.get_by_username("admin")
            if admin_user and not verify_password(settings.admin_password, admin_user.password_hash):
                admin_user.password_hash = hash_password(settings.admin_password)
                self._db.commit()

    def _get_user_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemyUserRepository

        return SQLAlchemyUserRepository(self._db)

    def _get_session_repo(self):
        from app.infrastructure.repositories.auth_repository import SQLAlchemySessionRepository

        return SQLAlchemySessionRepository(self._db)

    def _resolve_access_token(self, token: str) -> Optional[str]:
        """Traduz um access JWT do operador para o token da sessão (B5).

        Devolve ``None`` para JWT inválido/expirado ou quando a sessão que ele
        referencia não existe mais (revogada, expirada, usuário removido). Para
        token opaco — legado, ou do desktop single-machine — devolve o próprio
        token, então o caminho anterior continua valendo até ele expirar.

        Existir um único ponto de tradução é proposital: sem ele, `validate_token`
        e `logout` ganhariam duas implementações paralelas de validação de sessão.
        """
        if not token or not operator_token.looks_like_jwt(token):
            return token
        try:
            payload = operator_token.verify_access_token(token)
        except operator_token.TokenError:
            return None
        session_id = str(payload.get("sid") or "")
        if not session_id:
            return None
        if self._use_db:
            session_model = self._get_session_repo().get_by_id(session_id)
            return session_model.token if session_model else None
        session = self._sessions.get(session_id)
        return session.token if session else None

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
            must_change_password=bool(getattr(model, "must_change_password", False)),
            driver_id=getattr(model, "driver_id", None),
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

    @_db_synchronized
    def login(
        self,
        username: str,
        password: str,
        ip_address: str = "",
        user_agent: str = "",
        platform: str = operator_token.PLATFORM_DESKTOP,
    ) -> Dict[str, Any]:
        """Authenticate user and create session.
        Generic error messages prevent user enumeration."""
        GENERIC_ERROR = "Invalid credentials."

        # Rate limit check
        if not self._rate_limiter.check(f"login:{username}", 5, 300):
            self._audit(username, "default", AuditAction.AUTH_FAILURE.value, result="RATE_LIMITED", ip=ip_address)
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
            self._audit(
                username or "unknown", "default", AuditAction.AUTH_FAILURE.value, result="USER_NOT_FOUND", ip=ip_address
            )
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
                self._audit(user.id, "default", AuditAction.AUTH_LOCKOUT.value, result="LOCKED", ip=ip_address)
            self._audit(user.id, "default", AuditAction.AUTH_FAILURE.value, result="WRONG_PASSWORD", ip=ip_address)
            # Persist failed attempts to DB
            if self._use_db:
                self._get_user_repo().update(
                    user.id,
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
            self._get_user_repo().update(
                user.id,
                failed_login_attempts=0,
                locked_until=None,
                password_hash=user.password_hash,
            )
        else:
            with self._lock:
                user_sessions = [
                    s for s in self._sessions.values() if s.user_id == user.id and s.status == SessionStatus.ACTIVE
                ]
                if len(user_sessions) >= self.MAX_SESSIONS_PER_USER:
                    oldest = user_sessions[0]
                    oldest.revoke()
                self._sessions[session.id] = session
                self._sessions_by_token[token] = session.id

        # B5: emite o par access (JWT curto, preso ao `sid`) + refresh rotativo.
        # O token opaco continua sendo gravado na sessão: ele é o `sid` e segue
        # como caminho de compatibilidade de quem já tinha token.
        refresh_token = operator_token.generate_refresh_token()
        if self._use_db:
            self._get_session_repo().set_refresh(
                session.id,
                operator_token.hash_refresh_token(refresh_token),
                operator_token.refresh_expiry(),
            )
        access_token = operator_token.issue_access_token(
            user_id=user.id,
            tenant_id=tenant_id,
            session_id=session.id,
            role=system_role.value,
            platform=platform if platform in operator_token.VALID_PLATFORMS else operator_token.PLATFORM_DESKTOP,
        )

        self._audit(user.id, tenant_id, AuditAction.AUTH_SUCCESS.value, result="SUCCESS", ip=ip_address)

        return {
            "success": True,
            "token": token,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": operator_token.ACCESS_TTL_MINUTES * 60,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                # P0: cliente usa para forçar a troca de senha no próximo acesso
                "must_change_password": bool(user.must_change_password),
            },
            "tenant_id": tenant_id,
            "role": system_role.value,
            "expires_at": session.expires_at.isoformat(),
        }

    @_db_synchronized
    def refresh_session(self, refresh_token: str, *, ip_address: str = "") -> Optional[Dict[str, Any]]:
        """Rotaciona o par access+refresh do operador (B5).

        Devolve ``None`` para refresh desconhecido, de sessão não ativa ou
        expirado. Reuso de um refresh já rotacionado **revoga a sessão**: um
        token trocado só reaparece se vazou, e nesse caso a família inteira
        morre — mesmo sinal que o fluxo do app do entregador já detecta.
        """
        if not refresh_token or not self._use_db:
            # Sem DB não existe família de refresh para rotacionar.
            return None
        repo = self._get_session_repo()
        presented_hash = operator_token.hash_refresh_token(refresh_token)
        session_model, is_reuse = repo.find_by_refresh_hash(presented_hash)
        if not session_model:
            return None
        if is_reuse:
            repo.revoke(session_model.id)
            logger.warning("refresh.reuse — sessão %s revogada", session_model.id)
            self._audit(
                session_model.user_id,
                session_model.tenant_id,
                AuditAction.SESSION_REVOKED.value,
                result="REFRESH_REUSE",
                ip=ip_address,
            )
            return None
        if session_model.status != "ACTIVE":
            return None
        if not session_model.expires_at or datetime.utcnow() > session_model.expires_at:
            return None
        if session_model.refresh_expires_at and datetime.utcnow() > session_model.refresh_expires_at:
            return None

        user_model = self._get_user_repo().get_by_id(session_model.user_id)
        if not user_model:
            return None
        user = self._db_user_to_domain(user_model)
        if not user.is_active:
            return None

        membership = self._get_membership(user.id, session_model.tenant_id)
        role = self._get_role(membership.role_id) if membership else None
        system_role = role.system_role if role else SystemRole.OPERATOR

        new_refresh = operator_token.generate_refresh_token()
        repo.rotate_refresh(
            session_model.id,
            presented_hash,
            operator_token.hash_refresh_token(new_refresh),
            operator_token.refresh_expiry(),
        )
        access_token = operator_token.issue_access_token(
            user_id=user.id,
            tenant_id=session_model.tenant_id,
            session_id=session_model.id,
            role=system_role.value,
            platform=operator_token.PLATFORM_DESKTOP,
        )
        self._audit(
            user.id,
            session_model.tenant_id,
            AuditAction.AUTH_SUCCESS.value,
            result="REFRESH",
            ip=ip_address,
        )
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_type": "Bearer",
            "expires_in": operator_token.ACCESS_TTL_MINUTES * 60,
            "tenant_id": session_model.tenant_id,
            "role": system_role.value,
        }

    @_db_synchronized
    def logout(self, token: str) -> bool:
        """Revoke a session. Aceita o access JWT ou o token opaco da sessão."""
        token = self._resolve_access_token(token)
        if not token:
            return False
        if self._use_db:
            session_repo = self._get_session_repo()
            session_model = session_repo.get_by_token(token)
            if not session_model:
                return False
            session_repo.revoke(session_model.id)
            self._audit(
                session_model.user_id, session_model.tenant_id, AuditAction.SESSION_REVOKED.value, result="SUCCESS"
            )
            return True
        else:
            session_id = self._sessions_by_token.get(token)
            if not session_id:
                return False
            session = self._sessions.get(session_id)
            if not session:
                return False
            session.revoke()
            self._audit(session.user_id, session.tenant_id, AuditAction.SESSION_REVOKED.value, result="SUCCESS")
            return True

    @_db_synchronized
    def validate_token(self, token: str) -> Optional[TenantContext]:
        """Validate token and return tenant context.

        Aceita o access JWT do operador (B5) **ou** o token opaco de sessão.
        Nos dois casos a linha da sessão é a fonte de verdade, então revogar
        sessão corta o acesso na hora — sem esperar o JWT expirar.
        """
        if not token:
            return None

        token = self._resolve_access_token(token)
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
            # P0 3.2: permissões do DB (catálogo + matriz + overrides) com
            # fallback para o JSON/dict legado quando o DB não tem catálogo.
            try:
                from app.application.security.permission_policy_loader import get_policy_loader

                permissions = get_policy_loader().load_for_user(user.id, membership.role_id if membership else None)
            except Exception:
                logger.exception("policy.loader.unavailable — usando permissões do role JSON")
                permissions = set(role.permissions) if role else set()

            # Update last seen
            session_repo.update_last_seen(session_model.id)

            return TenantContext(
                user_id=user.id,
                tenant_id=session_model.tenant_id,
                role=system_role,
                permissions=permissions,
                session_id=session_model.id,
                must_change_password=bool(getattr(user, "must_change_password", False)),
                driver_id=getattr(user_model, "driver_id", None),
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
                must_change_password=bool(getattr(user, "must_change_password", False)),
                driver_id=getattr(user, "driver_id", None),
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

    @_db_synchronized
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        display_name: str = "",
        role_name: str = "OPERATOR",
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
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
                self._memberships.append(
                    TenantMembership(
                        user_id=user.id,
                        tenant_id=tenant_id,
                        role_id=role.id,
                    )
                )
            self._audit(user.id, tenant_id, AuditAction.USER_CREATED.value, result="SUCCESS")
            return {"success": True, "user_id": user.id}

    @_db_synchronized
    def change_password(
        self, user_id: str, old_password: str, new_password: str, *, clear_must_change: bool = False
    ) -> Dict[str, Any]:
        """Change user password. Rehashes to bcrypt.

        clear_must_change=True (fluxo P0 3.8): troca obrigatória pós-reset —
        limpa must_change_password para que o próximo login/`/auth/me` não
        force novamente a troca.
        """
        if self._use_db:
            user_repo = self._get_user_repo()
            user_model = user_repo.get_by_id(user_id)
            if not user_model:
                return {"success": False, "error": "User not found"}
            if not verify_password(old_password, user_model.password_hash):
                return {"success": False, "error": "Current password is incorrect"}
            user_repo.update(
                user_id,
                password_hash=hash_password(new_password),
                **({"must_change_password": False} if clear_must_change else {}),
            )
            self._audit(user_id, "default", AuditAction.PASSWORD_CHANGED.value, result="SUCCESS")
            return {"success": True}
        else:
            user = self._users.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            if not verify_password(old_password, user.password_hash):
                return {"success": False, "error": "Current password is incorrect"}
            user.password_hash = hash_password(new_password)
            if clear_must_change:
                user.must_change_password = False
            self._audit(user_id, "default", AuditAction.PASSWORD_CHANGED.value, result="SUCCESS")
            return {"success": True}

    @_db_synchronized
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

    def _audit(
        self,
        actor_id: str,
        tenant_id: str,
        action: str,
        result: str = "SUCCESS",
        resource: str = "",
        resource_id: str = "",
        ip: str = "",
        details: Optional[Dict] = None,
    ):
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

    @_db_synchronized
    def get_audit_log(self, tenant_id: Optional[str] = None, limit: int = 50) -> List[AuditRecord]:
        if self._use_db:
            models = self._get_audit_repo().list_for_tenant(tenant_id or "", limit)
            return [
                AuditRecord(
                    id=m.id,
                    actor_id=m.actor_id,
                    tenant_id=m.tenant_id,
                    action=m.action,
                    resource=m.resource,
                    result=m.result,
                    timestamp=m.timestamp,
                    ip_address=m.ip_address,
                    details=m.details or {},
                )
                for m in models
            ]
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

    @_db_synchronized
    def get_user(self, user_id: str) -> Optional[User]:
        if self._use_db:
            user_model = self._get_user_repo().get_by_id(user_id)
            return self._db_user_to_domain(user_model) if user_model else None
        return self._users.get(user_id)

    @_db_synchronized
    def get_users(self, tenant_id: str = "default") -> List[User]:
        if self._use_db:
            models = self._get_user_repo().list_by_tenant(tenant_id)
            return [self._db_user_to_domain(m) for m in models]
        member_ids = {m.user_id for m in self._memberships if m.tenant_id == tenant_id}
        return [u for uid, u in self._users.items() if uid in member_ids]

    @_db_synchronized
    def get_roles(self) -> List[Role]:
        if self._use_db:
            models = self._get_role_repo().list_all()
            return [self._db_role_to_domain(m) for m in models]
        return list(self._roles.values())

    @_db_synchronized
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
            self._audit(creator_user_id or "system", tenant_id, AuditAction.TENANT_CREATED.value, result="SUCCESS")
            return {"success": True, "tenant_id": tenant_id}
        else:
            if tenant_id in self._tenants:
                return {"success": False, "error": f"Tenant '{tenant_id}' already exists"}
            tenant = Tenant(id=tenant_id, name=name)
            self._tenants[tenant_id] = tenant
            if creator_user_id:
                user = self._users.get(creator_user_id)
                if user:
                    admin_role = next((r for r in self._roles.values() if r.system_role == SystemRole.ADMIN), None)
                    if admin_role:
                        self._memberships.append(
                            TenantMembership(
                                user_id=creator_user_id,
                                tenant_id=tenant_id,
                                role_id=admin_role.id,
                            )
                        )
            self._audit(creator_user_id or "system", tenant_id, AuditAction.TENANT_CREATED.value, result="SUCCESS")
            return {"success": True, "tenant_id": tenant_id}

    @_db_synchronized
    def get_tenants(self) -> List[Tenant]:
        """List all tenants."""
        if self._use_db:
            models = self._get_tenant_repo().list_all()
            return [self._db_tenant_to_domain(m) for m in models]
        return list(self._tenants.values())

    @_db_synchronized
    def get_active_sessions(self, user_id: str) -> List[Session]:
        if self._use_db:
            models = self._get_session_repo().list_active_for_user(user_id)
            return [self._db_session_to_domain(m) for m in models]
        return [s for s in self._sessions.values() if s.user_id == user_id and s.status == SessionStatus.ACTIVE]

    @_db_synchronized
    def revoke_all_sessions(self, user_id: str) -> int:
        if self._use_db:
            return self._get_session_repo().revoke_all_for_user(user_id)
        count = 0
        for s in self._sessions.values():
            if s.user_id == user_id and s.status == SessionStatus.ACTIVE:
                s.revoke()
                count += 1
        return count

    @_db_synchronized
    def expire_old_sessions(self) -> int:
        if self._use_db:
            return self._get_session_repo().expire_old()
        count = 0
        for s in self._sessions.values():
            if s.status == SessionStatus.ACTIVE and s.expires_at and datetime.utcnow() > s.expires_at:
                s.status = SessionStatus.EXPIRED
                count += 1
        return count
