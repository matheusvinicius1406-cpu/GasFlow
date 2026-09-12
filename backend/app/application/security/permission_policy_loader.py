"""PermissionPolicyLoader — permissões do DB, não do dict em código (3.2).

Fonte da verdade (P0 RBAC):
- `permissions` JOIN `role_permissions` (role do usuário)
- `user_permissions_override` (granted=True adiciona, granted=False remove)
- Wildcards resolvidos: `admin.*` → todas; `inventory.*` → módulo inteiro

Compatibilidade (fallback): DB sem permissões → `ROLE_PERMISSIONS` do código
(comportamento pré-P0). Invalidação por evento `permissions.changed`.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Optional

from sqlalchemy import text

from app.infrastructure.database.permission_cache import TTLCache

logger = logging.getLogger("gasflow.security.policy_loader")

CACHE_TTL_SECONDS = 60.0
_ALL_PERMISSIONS_SQL = "SELECT code FROM permissions"


def _load_all_permission_codes(conn) -> set[str]:
    rows = conn.execute(text(_ALL_PERMISSIONS_SQL)).fetchall()
    return {row.code for row in rows}


def _expand_wildcard(wildcard: str, all_codes: set[str]) -> set[str]:
    """`admin.*` → todas; `inventory.*` → tudo do módulo inventory."""
    resource = wildcard[:-2]  # remove '.*'
    if resource == "admin":
        return set(all_codes)  # acesso total
    return {code for code in all_codes if code.split(".")[0] == resource}


class PermissionPolicyLoader:
    """Resolve o set de permissões de um usuário a partir do DB.

    Thread-safe; cache TTL com single-flight; invalidação explícita via
    `invalidate_user`/`invalidate_all` (evento `permissions.changed`).
    """

    def __init__(self, session_factory=None, ttl_seconds: float = CACHE_TTL_SECONDS):
        # session_factory: callable -> Session (SessionLocal). Injetável p/ testes.
        self._session_factory = session_factory
        self._ttl = ttl_seconds
        self._cache = TTLCache()
        self._lock = threading.Lock()

    # ── API principal ────────────────────────────────────────

    def load_for_user(self, user_id: str, role_id: Optional[str]) -> set[str]:
        """Permissões efetivas do usuário (role ∓ overrides), com cache."""
        key = f"user:{user_id}"
        return set(self._cache.get_or_load(key, lambda: self._resolve(user_id, role_id), self._ttl))

    def load_for_role(self, role_id: str) -> set[str]:
        """Permissões do role (sem overrides) — usado em telas de roles."""
        key = f"role:{role_id}"

        def _load() -> set[str]:
            with self._lock:
                session = self._session()
                try:
                    codes = self._resolve_role(session, role_id)
                    if not codes:
                        return self._fallback_from_code(role_id)
                    return self._expand(session, codes)
                except Exception:
                    logger.exception("policy.role.load.failed — usando fallback do código")
                    return self._fallback_from_code(role_id)
                finally:
                    session.close()

        return set(self._cache.get_or_load(key, _load, self._ttl))

    def invalidate_user(self, user_id: str) -> None:
        self._cache.invalidate(f"user:{user_id}")

    def invalidate_all(self) -> None:
        """Evento `permissions.changed`: qualquer edição de role/permissão."""
        self._cache.clear()

    # ── Resolução ────────────────────────────────────────────

    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from app.infrastructure.database.init_db import engine

        from sqlalchemy.orm import Session as DBSession

        return DBSession(bind=engine)

    def _resolve(self, user_id: str, role_id: Optional[str]) -> set[str]:
        with self._lock:
            session = self._session()
            try:
                perms = self._resolve_role(session, role_id) if role_id else set()
                if not perms:
                    # Fallback: DB sem catálogo/role (pré-seed) → comportamento antigo.
                    return self._fallback_from_code(role_id)
                perms = self._expand(session, perms)
                return self._apply_overrides(session, user_id, perms)
            except Exception:
                logger.exception("policy.load.failed — usando fallback do código")
                return self._fallback_from_code(role_id)
            finally:
                session.close()

    def _expand(self, session, codes: set[str]) -> set[str]:
        """Expande wildcards para códigos concretos do catálogo.

        Mantém o código curinga no set (TenantContext.has_permission já o
        interpreta) E adiciona os concretos — cobre checagens exatas e
        preserva códigos específicos fora do catálogo (ex.:
        delivery.read.assigned do DRIVER).
        """
        wildcards = {c for c in codes if c.endswith(".*")}
        if not wildcards:
            return codes
        all_codes = self._all_codes(session)
        if not all_codes:
            return codes
        expanded = set(codes)
        for wildcard in wildcards:
            expanded |= _expand_wildcard(wildcard, all_codes)
        return expanded

    def _resolve_role(self, session, role_id: Optional[str]) -> set[str]:
        """Permissões normalizadas do role; vazio → JSON legacy do auth_roles."""
        if not role_id:
            return set()

        rows = session.execute(
            text(
                "SELECT p.code FROM role_permissions rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :role_id"
            ),
            {"role_id": role_id},
        ).fetchall()
        codes = {row.code for row in rows}
        if codes:
            return codes

        # Legacy: role sem linhas na matriz → usa o JSON (fonte pré-P0).
        # O driver pode devolver o JSON como string — parse antes de set().
        row = session.execute(
            text("SELECT permissions FROM auth_roles WHERE id = :role_id"),
            {"role_id": role_id},
        ).fetchone()
        if row and row.permissions:
            raw = row.permissions
            if isinstance(raw, str):
                raw = json.loads(raw)
            return set(raw)
        return set()

    def _apply_overrides(self, session, user_id: str, perms: set[str]) -> set[str]:
        has_overrides = session.execute(
            text("SELECT 1 FROM user_permissions_override WHERE user_id = :uid LIMIT 1"),
            {"uid": user_id},
        ).fetchone()
        if not has_overrides:
            return perms

        effective = set(perms)
        rows = session.execute(
            text(
                "SELECT p.code, o.granted FROM user_permissions_override o "
                "JOIN permissions p ON p.id = o.permission_id "
                "WHERE o.user_id = :uid"
            ),
            {"uid": user_id},
        ).fetchall()
        for row in rows:
            if row.granted:
                effective.add(row.code)
            else:
                effective.discard(row.code)
        return effective

    def _fallback_from_code(self, role_id: Optional[str]) -> set[str]:
        """DB vazio (pré-seed) → dict ROLE_PERMISSIONS (comportamento pré-P0)."""
        from app.infrastructure.database.init_db import engine  # noqa: F401

        from app.domain.security.models import SystemRole, ROLE_PERMISSIONS

        if not role_id:
            return set()
        session = self._session()
        try:
            row = session.execute(
                text("SELECT system_role FROM auth_roles WHERE id = :role_id"),
                {"role_id": role_id},
            ).fetchone()
        finally:
            session.close()
        if not row:
            return set()
        try:
            system_role = SystemRole(row.system_role)
        except ValueError:
            return set()
        return set(ROLE_PERMISSIONS.get(system_role, []))

    def _all_codes(self, session) -> set[str]:
        try:
            return _load_all_permission_codes(session)
        except Exception:
            return set()


# ── Singleton ────────────────────────────────────────────

_policy_loader: Optional[PermissionPolicyLoader] = None


def get_policy_loader() -> PermissionPolicyLoader:
    """Instância única por processo (cache compartilhado)."""
    global _policy_loader
    if _policy_loader is None:
        _policy_loader = PermissionPolicyLoader()
    return _policy_loader
