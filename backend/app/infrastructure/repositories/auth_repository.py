"""
Auth Persistence Repository — SQLAlchemy implementation.

Replaces in-memory AuthService storage with database persistence.
Single source of truth for users, sessions, tenants, roles, and audit.

Repository pattern:
- SQLAlchemyUserRepository: user CRUD
- SQLAlchemySessionRepository: session CRUD
- SQLAlchemyTenantRepository: tenant CRUD
- SQLAlchemyRoleRepository: role CRUD
- SQLAlchemyMembershipRepository: membership CRUD
- SQLAlchemyAuditRepository: audit log
"""

from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from app.infrastructure.repositories.auth_model import (
    AuthUserModel, AuthSessionModel, AuthTenantModel,
    AuthRoleModel, AuthMembershipModel, AuthAuditModel
)


class SQLAlchemyUserRepository:
    """Repository for auth users — replaces in-memory _users dict."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[AuthUserModel]:
        return self.db.query(AuthUserModel).filter(AuthUserModel.id == user_id).first()

    def get_by_username(self, username: str) -> Optional[AuthUserModel]:
        return self.db.query(AuthUserModel).filter(AuthUserModel.username == username).first()

    def create(self, user_id: str, username: str, email: str = "",
               display_name: str = "", password_hash: str = "",
               status: str = "ACTIVE") -> AuthUserModel:
        model = AuthUserModel(
            id=user_id,
            username=username,
            email=email,
            display_name=display_name or username,
            password_hash=password_hash,
            status=status,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def update(self, user_id: str, **kwargs) -> Optional[AuthUserModel]:
        model = self.get_by_id(user_id)
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        model.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return model

    def list_by_tenant(self, tenant_id: str) -> List[AuthUserModel]:
        """List users belonging to a tenant via memberships."""
        from sqlalchemy import select
        membership_user_ids = select(AuthMembershipModel.user_id).where(
            AuthMembershipModel.tenant_id == tenant_id
        )
        return self.db.query(AuthUserModel).filter(
            AuthUserModel.id.in_(membership_user_ids)
        ).all()

    def list_all(self) -> List[AuthUserModel]:
        return self.db.query(AuthUserModel).all()


class SQLAlchemySessionRepository:
    """Repository for auth sessions — replaces in-memory _sessions dict."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_token(self, token: str) -> Optional[AuthSessionModel]:
        return self.db.query(AuthSessionModel).filter(
            AuthSessionModel.token == token,
            AuthSessionModel.status == "ACTIVE",
        ).first()

    def get_by_id(self, session_id: str) -> Optional[AuthSessionModel]:
        return self.db.query(AuthSessionModel).filter(
            AuthSessionModel.id == session_id
        ).first()

    def create(self, session_id: str, user_id: str, tenant_id: str,
               token: str, expires_at: Optional[datetime] = None,
               ip_address: str = "", user_agent: str = "") -> AuthSessionModel:
        model = AuthSessionModel(
            id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            token=token,
            status="ACTIVE",
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def revoke(self, session_id: str) -> bool:
        model = self.get_by_id(session_id)
        if not model:
            return False
        model.status = "REVOKED"
        model.revoked_at = datetime.utcnow()
        self.db.commit()
        return True

    def revoke_by_token(self, token: str) -> bool:
        model = self.db.query(AuthSessionModel).filter(
            AuthSessionModel.token == token
        ).first()
        if not model:
            return False
        model.status = "REVOKED"
        model.revoked_at = datetime.utcnow()
        self.db.commit()
        return True

    def revoke_all_for_user(self, user_id: str) -> int:
        count = self.db.query(AuthSessionModel).filter(
            AuthSessionModel.user_id == user_id,
            AuthSessionModel.status == "ACTIVE",
        ).update({"status": "REVOKED", "revoked_at": datetime.utcnow()})
        self.db.commit()
        return count

    def list_active_for_user(self, user_id: str) -> List[AuthSessionModel]:
        return self.db.query(AuthSessionModel).filter(
            AuthSessionModel.user_id == user_id,
            AuthSessionModel.status == "ACTIVE",
        ).all()

    def expire_old(self) -> int:
        now = datetime.utcnow()
        count = self.db.query(AuthSessionModel).filter(
            AuthSessionModel.status == "ACTIVE",
            AuthSessionModel.expires_at < now,
        ).update({"status": "EXPIRED"})
        self.db.commit()
        return count

    def update_last_seen(self, session_id: str):
        model = self.get_by_id(session_id)
        if model:
            model.last_seen_at = datetime.utcnow()
            self.db.commit()

    def enforce_max_sessions(self, user_id: str, max_sessions: int = 5) -> int:
        """Revoke oldest sessions if user exceeds max."""
        active = self.list_active_for_user(user_id)
        revoked = 0
        if len(active) >= max_sessions:
            # Revoke oldest
            oldest = sorted(active, key=lambda s: s.created_at or datetime.min)
            for s in oldest[:len(active) - max_sessions + 1]:
                s.status = "REVOKED"
                s.revoked_at = datetime.utcnow()
                revoked += 1
            self.db.commit()
        return revoked


class SQLAlchemyTenantRepository:
    """Repository for auth tenants — replaces in-memory _tenants dict."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_tenant_id(self, tenant_id: str) -> Optional[AuthTenantModel]:
        return self.db.query(AuthTenantModel).filter(
            AuthTenantModel.tenant_id == tenant_id
        ).first()

    def create(self, tenant_id: str, name: str) -> AuthTenantModel:
        model = AuthTenantModel(
            id=tenant_id,
            tenant_id=tenant_id,
            name=name,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def list_all(self) -> List[AuthTenantModel]:
        return self.db.query(AuthTenantModel).all()


class SQLAlchemyRoleRepository:
    """Repository for auth roles — replaces in-memory _roles dict."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, role_id: str) -> Optional[AuthRoleModel]:
        return self.db.query(AuthRoleModel).filter(AuthRoleModel.id == role_id).first()

    def get_by_name(self, name: str) -> Optional[AuthRoleModel]:
        return self.db.query(AuthRoleModel).filter(AuthRoleModel.name == name).first()

    def create(self, role_id: str, name: str, system_role: str,
               permissions: List[str] = None) -> AuthRoleModel:
        model = AuthRoleModel(
            id=role_id,
            name=name,
            system_role=system_role,
            permissions=permissions or [],
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def list_all(self) -> List[AuthRoleModel]:
        return self.db.query(AuthRoleModel).all()


class SQLAlchemyMembershipRepository:
    """Repository for auth memberships — replaces in-memory _memberships list."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: str, tenant_id: str) -> Optional[AuthMembershipModel]:
        return self.db.query(AuthMembershipModel).filter(
            AuthMembershipModel.user_id == user_id,
            AuthMembershipModel.tenant_id == tenant_id,
        ).first()

    def get_first_for_user(self, user_id: str) -> Optional[AuthMembershipModel]:
        return self.db.query(AuthMembershipModel).filter(
            AuthMembershipModel.user_id == user_id,
        ).first()

    def create(self, user_id: str, tenant_id: str, role_id: str) -> AuthMembershipModel:
        import uuid as _uuid
        model = AuthMembershipModel(
            id=str(_uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            role_id=role_id,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def list_for_tenant(self, tenant_id: str) -> List[AuthMembershipModel]:
        return self.db.query(AuthMembershipModel).filter(
            AuthMembershipModel.tenant_id == tenant_id
        ).all()


class SQLAlchemyAuditRepository:
    """Repository for auth audit log — replaces in-memory _audit_log list."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, actor_id: str, tenant_id: str, action: str,
               result: str = "SUCCESS", resource: str = "",
               resource_id: str = "", ip_address: str = "",
               user_agent: str = "", correlation_id: Optional[str] = None,
               details: Optional[Dict] = None) -> AuthAuditModel:
        import uuid
        model = AuthAuditModel(
            id=str(uuid.uuid4()),
            actor_id=actor_id,
            tenant_id=tenant_id,
            action=action,
            result=result,
            resource=resource,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
            details=details or {},
        )
        self.db.add(model)
        self.db.commit()
        return model

    def list_for_tenant(self, tenant_id: str, limit: int = 50) -> List[AuthAuditModel]:
        return self.db.query(AuthAuditModel).filter(
            AuthAuditModel.tenant_id == tenant_id
        ).order_by(AuthAuditModel.timestamp.desc()).limit(limit).all()
