"""A3 — bootstrap de banco vazio pelo Alembic no boot do backend.

Cobre o caminho que faltava: um banco novo (dev/uvicorn direto) passa a
nascer das migrations (`alembic_version` gravado), e não de `create_all` sem
versão — que era a causa do drift de 2026-10-09.

Os testes do projeto continuam no `create_all` efêmero (conftest desliga o
bootstrap por `GASFLOW_INIT_DB_ALEMBIC=0`).
"""

import os

from sqlalchemy import create_engine, inspect, text

# A tabela de bookkeeping do próprio Alembic.
_ALEMBIC_VERSION_TABLE = "alembic_version"


def test_alembic_boot_disabled_in_tests(monkeypatch):
    """Ambiente de teste mantém o create_all (efêmero) — sem migrar a cada run."""
    from app.infrastructure.database import init_db

    monkeypatch.delenv("GASFLOW_INIT_DB_ALEMBIC", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert init_db._alembic_boot_enabled() is False


def test_alembic_boot_enabled_in_development(monkeypatch):
    from app.infrastructure.database import init_db

    monkeypatch.delenv("GASFLOW_INIT_DB_ALEMBIC", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert init_db._alembic_boot_enabled() is True


def test_alembic_boot_flag_disables(monkeypatch):
    from app.infrastructure.database import init_db

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GASFLOW_INIT_DB_ALEMBIC", "0")
    assert init_db._alembic_boot_enabled() is False


def test_run_alembic_upgrade_creates_fresh_schema(tmp_path):
    """Banco vazio → upgrade head cria as tabelas dos models + alembic_version."""
    from app.infrastructure.database import init_db

    db_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    assert init_db._run_alembic_upgrade(db_url) is True

    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert _ALEMBIC_VERSION_TABLE in tables, "alembic_version não foi gravado"
        # O schema migrado precisa cobrir as tabelas dos models.
        missing = set(init_db.Base.metadata.tables) - tables
        assert not missing, f"tabelas sem migration: {sorted(missing)}"

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version, "alembic_version vazio"
    finally:
        engine.dispose()


def test_run_alembic_upgrade_restores_env(tmp_path, monkeypatch):
    """O DATABASE_URL do processo não pode vazar a URL temporária."""
    from app.infrastructure.database import init_db

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./nao-deve-mudar.db")
    db_url = f"sqlite:///{(tmp_path / 'fresh2.db').as_posix()}"
    init_db._run_alembic_upgrade(db_url)
    assert os.environ["DATABASE_URL"] == "sqlite:///./nao-deve-mudar.db"


def test_return_false_without_alembic_ini(tmp_path):
    """Sem alembic.ini na raiz indicada, devolve False (boot cai no create_all)."""
    from app.infrastructure.database import init_db

    vazio = tmp_path / "sem_alembic"
    vazio.mkdir()
    assert init_db._run_alembic_upgrade("sqlite:///:memory:", backend_dir=vazio) is False
