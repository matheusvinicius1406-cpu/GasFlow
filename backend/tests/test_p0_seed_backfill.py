"""Regressão: seed RBAC + backfill cheios/vazios (P0, Fase 2).

Cobre os dois caminhos que devem popular o catálogo/matriz/roles:
1. Migration (e4f7a9b1c3d5) em banco novo versionado;
2. Boot (init_db) em banco legado create_all — onde a migration não roda.

E valida o backfill aditivo do estoque (Decisão A): quantity_full = quantity
na primeira inicialização, sem sobrescrever estado já detalhado.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def legacy_db_url(tmp_path: Path) -> str:
    """Banco legado: schema criado por create_all (como Desktops instalados)."""
    from app.infrastructure.database.init_db import Base

    db = tmp_path / "legacy.db"
    url = f"sqlite:///{db.as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


def _counts(url: str) -> dict[str, int]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {
                "permissions": conn.execute(text("SELECT count(*) FROM permissions")).scalar_one(),
                "role_permissions": conn.execute(text("SELECT count(*) FROM role_permissions")).scalar_one(),
                "roles": conn.execute(
                    text(
                        "SELECT count(*) FROM auth_roles WHERE name IN ('ADMIN','MANAGER','OPERATOR','DRIVER','VIEWER','CUSTOMER','SYSTEM')"
                    )
                ).scalar_one(),
            }
    finally:
        engine.dispose()


def test_migration_seeds_rbac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Caminho 1: upgrade head em banco novo → seed aplicado pela migration."""
    import os

    db = tmp_path / "migrated.db"
    backup = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    try:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    finally:
        if backup is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = backup

    counts = _counts(f"sqlite:///{db.as_posix()}")
    assert counts["permissions"] >= 45  # catálogo completo (49 códigos)
    assert counts["roles"] == 7
    assert counts["role_permissions"] >= 30


def test_init_db_seeds_legacy_db(legacy_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Caminho 2: init_db em banco legado create_all → seed aplicado no boot."""
    from app.infrastructure.database import init_db as init_db_module

    # Censo pré-seed: banco legado não tem catálogo.
    assert _counts(legacy_db_url)["permissions"] == 0

    engine_backup = init_db_module.engine
    init_db_module.engine = create_engine(legacy_db_url)
    try:
        init_db_module.init_db()
    finally:
        init_db_module.engine = engine_backup

    counts = _counts(legacy_db_url)
    assert counts["permissions"] >= 45
    assert counts["roles"] == 7

    # Idempotência: segunda rodada não duplica.
    init_db_module.engine = create_engine(legacy_db_url)
    try:
        init_db_module.init_db()
    finally:
        init_db_module.engine = engine_backup
    assert _counts(legacy_db_url) == counts


def test_backfill_stock_full_empty(tmp_path: Path) -> None:
    """Decisão A: primeiro boot alinha full=quantity; estado detalhado preservado."""
    from app.infrastructure.database import init_db as init_db_module

    db = tmp_path / "stock.db"
    url = f"sqlite:///{db.as_posix()}"

    # Banco "antigo": inventory com o schema PRÉ-P0 (sem full/empty).
    raw = create_engine(url)
    with raw.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE inventory ("
                "tenant_id VARCHAR(100), id INTEGER PRIMARY KEY, "
                "product_codigo VARCHAR(100) NOT NULL, quantity INTEGER NOT NULL, "
                "minimum_quantity INTEGER NOT NULL, maximum_quantity INTEGER, "
                "updated_at DATETIME, "
                "CONSTRAINT uq_inv_old UNIQUE (tenant_id, product_codigo))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO inventory (tenant_id, product_codigo, quantity, minimum_quantity) "
                "VALUES ('default','P13',42,5)"
            )
        )
    raw.dispose()

    # Boot: create_all não altera tabela existente; _ensure_sqlite_columns
    # adiciona as colunas novas e o backfill alinha full ao total.
    engine_backup = init_db_module.engine
    init_db_module.engine = create_engine(url)
    try:
        init_db_module.init_db()
        engine = init_db_module.engine
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT quantity, quantity_full, quantity_empty FROM inventory WHERE product_codigo='P13'")
            ).fetchone()
        assert row == (42, 42, 0)

        # Estado já detalhado NÃO é sobrescrito em boots seguintes.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE inventory SET quantity=40, quantity_full=25, quantity_empty=15 WHERE product_codigo='P13'")
            )
        init_db_module.init_db()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT quantity, quantity_full, quantity_empty FROM inventory WHERE product_codigo='P13'")
            ).fetchone()
        assert row == (40, 25, 15)
    finally:
        init_db_module.engine.dispose()
        init_db_module.engine = engine_backup
