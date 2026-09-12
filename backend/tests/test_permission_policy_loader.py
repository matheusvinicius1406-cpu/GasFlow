"""Testes do PermissionPolicyLoader (3.2) — permissões do DB.

Cenários: role do DB, overrides (grant/revoke), wildcards, cache com
invalidação e fallback para o código quando o DB não tem catálogo.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.security.permission_policy_loader import (  # noqa: E402
    PermissionPolicyLoader,
)
from app.infrastructure.database.rbac_seed import PERMISSIONS  # noqa: E402


def _make_db(tmp_path: Path):
    """Banco com schema mínimo de RBAC + roles/permissões seedadas."""
    from app.infrastructure.database.rbac_seed import seed_rbac

    db = tmp_path / "policy.db"
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE permissions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, code VARCHAR(100) NOT NULL UNIQUE, "
                "description VARCHAR(200) NOT NULL, module VARCHAR(50) NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE role_permissions ("
                "role_id VARCHAR(36) NOT NULL, permission_id INTEGER NOT NULL, "
                "PRIMARY KEY (role_id, permission_id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE user_permissions_override ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id VARCHAR(36) NOT NULL, "
                "permission_id INTEGER NOT NULL, granted BOOLEAN NOT NULL, "
                "created_by VARCHAR(36), created_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE auth_roles ("
                "id VARCHAR(36) PRIMARY KEY, name VARCHAR(50) NOT NULL UNIQUE, "
                "system_role VARCHAR(30) NOT NULL, permissions JSON NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
        seed_rbac(conn)
    return engine


def _role_id(engine, name: str) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM auth_roles WHERE name = :n"), {"n": name}).scalar_one()


@pytest.fixture()
def db(tmp_path: Path):
    engine = _make_db(tmp_path)
    yield engine
    engine.dispose()


@pytest.fixture()
def loader(db):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db)
    return PermissionPolicyLoader(session_factory=factory, ttl_seconds=60)


def test_operator_permissions_from_db(loader, db) -> None:
    """Role OPERATOR → permissões exatamente as da matriz do DB."""
    role_id = _role_id(db, "OPERATOR")

    perms = loader.load_for_user("user-1", role_id)

    assert "order.create" in perms
    assert "inventory.read" in perms
    assert "user.create" not in perms  # OPERATOR não gerencia usuários


def test_override_granted_false_removes(loader, db) -> None:
    """Override granted=false remove permissão concedida pelo role."""
    role_id = _role_id(db, "OPERATOR")
    with db.begin() as conn:
        pid = conn.execute(text("SELECT id FROM permissions WHERE code = 'order.create'")).scalar_one()
        conn.execute(
            text(
                "INSERT INTO user_permissions_override (user_id, permission_id, granted, created_at) "
                "VALUES ('u1', :pid, 0, datetime('now'))"
            ),
            {"pid": pid},
        )

    perms = loader.load_for_user("u1", role_id)

    assert "order.create" not in perms
    assert "inventory.read" in perms  # demais preservadas


def test_override_granted_true_adds(loader, db) -> None:
    """Override granted=true concede permissão que o role não tem."""
    role_id = _role_id(db, "VIEWER")
    with db.begin() as conn:
        pid = conn.execute(text("SELECT id FROM permissions WHERE code = 'finance.export_pdf'")).scalar_one()
        conn.execute(
            text(
                "INSERT INTO user_permissions_override (user_id, permission_id, granted, created_at) "
                "VALUES ('u2', :pid, 1, datetime('now'))"
            ),
            {"pid": pid},
        )

    perms = loader.load_for_user("u2", role_id)

    assert "finance.export_pdf" in perms
    assert "order.create" not in perms  # VIEWER continua sem o resto


def test_wildcard_admin_star(loader, db) -> None:
    """Role ADMIN (admin.*) resolve para todas as permissões do catálogo."""
    role_id = _role_id(db, "ADMIN")

    perms = loader.load_for_user("admin-1", role_id)

    assert len(perms) >= len(PERMISSIONS)  # curinga expandido + curinga em si
    assert "inventory.adjust" in perms
    assert "fiscal.issue_nfce" in perms


def test_wildcard_module_star(loader, db) -> None:
    """MANAGER (inventory.*) resolve para todo o módulo inventory."""
    role_id = _role_id(db, "MANAGER")

    perms = loader.load_for_user("mgr-1", role_id)

    assert "inventory.read" in perms
    assert "inventory.adjust" in perms
    assert "inventory.snapshot" in perms
    assert "user.create" not in perms  # fora do módulo


def test_cache_hit_and_invalidation(loader, db, monkeypatch: pytest.MonkeyPatch) -> None:
    """1ª chamada carrega; 2ª usa cache; invalidação força reload."""
    role_id = _role_id(db, "OPERATOR")
    calls = {"n": 0}
    real_session = loader._session

    def counting_session():
        calls["n"] += 1
        return real_session()

    monkeypatch.setattr(loader, "_session", counting_session)

    loader.load_for_user("u9", role_id)
    loader.load_for_user("u9", role_id)
    assert calls["n"] == 1  # 2ª veio do cache

    loader.invalidate_all()  # evento permissions.changed
    loader.load_for_user("u9", role_id)
    assert calls["n"] == 2  # recarregou do DB


def test_fallback_when_db_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DB sem catálogo → permissões do dict ROLE_PERMISSIONS (pré-P0)."""
    from app.domain.security.models import ROLE_PERMISSIONS, SystemRole

    # Cria role legacy com system_role=OPERATOR e matriz VAZIA.
    engine = _make_db(tmp_path)
    role_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM role_permissions WHERE role_id = :rid"),
            {"rid": role_id},
        )
        conn.execute(
            text(
                "INSERT INTO auth_roles (id, name, system_role, permissions, created_at) "
                "VALUES (:rid, 'LEGACY', 'OPERATOR', :perms, datetime('now'))"
            ),
            {"rid": role_id, "perms": json.dumps([])},
        )
    engine.dispose()

    from sqlalchemy.orm import sessionmaker

    db2 = tmp_path / "policy.db"
    factory = sessionmaker(bind=create_engine(f"sqlite:///{db2.as_posix()}"))
    loader2 = PermissionPolicyLoader(session_factory=factory, ttl_seconds=60)

    perms = loader2.load_for_user("legacy-1", role_id)

    expected = set(ROLE_PERMISSIONS[SystemRole.OPERATOR])
    assert perms == expected
