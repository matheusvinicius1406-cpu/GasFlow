"""Testes de alinhamento entre as migrations Alembic e os models SQLAlchemy.

Garante que:
1. `alembic upgrade head` funciona a partir de um banco vazio (SQLite);
2. o schema produzido pelas migrations é idêntico ao schema dos models
   (Base.metadata) — mesma fonte usada por init_db()/create_all em runtime.

Se um model for alterado/adicionado sem a migration correspondente,
este teste falha e aponta a divergência.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Tabela de bookkeeping do próprio Alembic, ignorada na comparação.
_ALEMBIC_VERSION_TABLE = "alembic_version"


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    """Aplica `alembic upgrade head` num banco SQLite temporário.

    Escopo de módulo: o upgrade roda UMA vez e os testes compartilham
    o schema migrado (a DDL do schema completo é cara nesta máquina).
    """
    import os

    db_path = tmp_path_factory.mktemp("migrated") / "migrated.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    # Sobrescreve temporariamente o DATABASE_URL (o env.py do alembic
    # lê o valor em tempo de execução) e restaura ao final do módulo.
    backup = {k: os.environ.get(k) for k in ("DATABASE_URL", "ADMIN_PASSWORD", "ENVIRONMENT")}
    os.environ["DATABASE_URL"] = db_url
    os.environ["ADMIN_PASSWORD"] = "test_password_123"
    os.environ["ENVIRONMENT"] = "test"
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(ALEMBIC_INI))
        command.upgrade(cfg, "head")
    finally:
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return db_url


def _model_schema():
    """Schema declarado pelos models (mesma fonte do init_db/create_all)."""
    from app.infrastructure.database.init_db import Base

    schema = {}
    for name, table in Base.metadata.tables.items():
        schema[name] = {
            "columns": {c.name: c for c in table.columns},
            "pk": {c.name for c in table.primary_key.columns},
        }
    return schema


def _db_schema(db_url):
    engine = create_engine(db_url)
    inspector = inspect(engine)
    schema = {}
    for name in inspector.get_table_names():
        if name == _ALEMBIC_VERSION_TABLE:
            continue
        columns = {c["name"]: c for c in inspector.get_columns(name)}
        schema[name] = {
            "columns": columns,
            "pk": set(inspector.get_pk_constraint(name).get("constrained_columns") or []),
        }
    engine.dispose()
    return schema


def test_migrations_upgrade_creates_fresh_schema(migrated_db):
    """upgrade head a partir do zero deve criar as tabelas dos models."""
    engine = create_engine(migrated_db)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {_ALEMBIC_VERSION_TABLE}
    engine.dispose()

    from app.infrastructure.database.init_db import Base

    assert tables == set(Base.metadata.tables.keys())


def test_migrations_schema_matches_models(migrated_db):
    """Schema migrado == schema dos models (tabelas, colunas, PK, nullable)."""
    models = _model_schema()
    db = _db_schema(migrated_db)

    divergencias = []

    # Tabelas órfãs (no DB mas fora dos models)
    for table in sorted(set(db) - set(models)):
        divergencias.append(f"tabela orfã no DB (sem model): {table}")
    # Tabelas faltando (no model mas fora do DB migrado)
    for table in sorted(set(models) - set(db)):
        divergencias.append(f"tabela faltando na migration: {table}")

    for table in sorted(set(models) & set(db)):
        m, d = models[table], db[table]
        if m["pk"] != d["pk"]:
            divergencias.append(
                f"{table}: PK diverge (models={sorted(m['pk'])}, db={sorted(d['pk'])})"
            )
        if set(m["columns"]) != set(d["columns"]):
            divergencias.append(
                f"{table}: colunas divergem "
                f"(models={sorted(set(m['columns']) - set(d['columns']))}, "
                f"db={sorted(set(d['columns']) - set(m['columns']))})"
            )
        for col in sorted(set(m["columns"]) & set(d["columns"])):
            if m["columns"][col].nullable != d["columns"][col]["nullable"]:
                divergencias.append(
                    f"{table}.{col}: nullable diverge "
                    f"(model={m['columns'][col].nullable}, db={d['columns'][col]['nullable']})"
                )

    assert not divergencias, "Migrations desalinhadas dos models:\n" + "\n".join(divergencias)
