"""Regressão: migrations no boot do exe empacotado (Desktop).

Cobre `run_migrations()` nos três estados de banco que o Desktop encontra:
  1. DB novo (vazio)         → cadeia completa cria tudo + alembic_version
  2. DB legado create_all    → stamp head (preserva dados) e segue versionado
  3. DB já versionado        → upgrade idempotente

E valida que o schema migrado contém as tabelas de runtime (fonte: models).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from desktop_entry import run_migrations  # noqa: E402


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _runtime_tables() -> set[str]:
    from app.infrastructure.database.init_db import Base

    return set(Base.metadata.tables.keys())


@pytest.fixture()
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{(tmp_path / 'gasflow.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def test_fresh_db_full_chain(db_url: str) -> None:
    """DB novo: upgrade head cria todas as tabelas + alembic_version."""
    run_migrations()

    tables = _tables(db_url)
    assert "alembic_version" in tables
    missing = _runtime_tables() - tables
    assert not missing, f"tabelas faltando após migration: {sorted(missing)}"


def test_legacy_create_all_db_is_stamped_not_rebuilt(db_url: str) -> None:
    """DB legado (create_all, sem alembic_version): stamp head preserva dados.

    Reproduz o fluxo do Desktop real: schema criado pelo init_db() antigo,
    depois o exe passa a rodar migrations no boot.
    """
    # 1. Cria o schema legado exatamente como o app faz (create_all) e
    #    insere um produto para provar que nada é recriado/apagado.
    from app.infrastructure.database.init_db import Base

    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO products (tenant_id, codigo, nome, tipo, preco, estoque, ativo)"
                " VALUES ('default', 'P13', 'Botijão 13kg', 'GLP', 120.0, 10, 1)"
            )
        )
    engine.dispose()

    assert "alembic_version" not in _tables(db_url)

    # 2. Boot do exe: deve stampar (não recriar) e seguir versionado.
    run_migrations()

    tables = _tables(db_url)
    assert "alembic_version" in tables

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT estoque FROM products WHERE codigo = 'P13'")).scalar_one()
    finally:
        engine.dispose()
    assert row == 10, "stamp destruiu dados do banco legado"


def test_versioned_db_upgrade_is_idempotent(db_url: str) -> None:
    """DB já versionado: rodar de novo é no-op e não perde o versionamento."""
    run_migrations()
    run_migrations()

    assert "alembic_version" in _tables(db_url)


def test_runs_without_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem DATABASE_URL: cai no default `sqlite:///./gasflow.db` (cwd)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    run_migrations()

    assert "alembic_version" in _tables(f"sqlite:///{(tmp_path / 'gasflow.db').as_posix()}")


def test_bundle_dir_contains_alembic_ini() -> None:
    """O bundle apontado por _bundle_dir() tem ini + versions (empacotado e dev)."""
    from desktop_entry import _bundle_dir

    bundle = Path(_bundle_dir())
    assert (bundle / "alembic.ini").is_file()
    versions = bundle / "migrations" / "versions"
    assert versions.is_dir()
    assert any(versions.glob("*.py")), "nenhuma migration em versions/"

    # Em dev o bundle é o próprio backend/; empacotado é <_MEIPASS>/migrations_bundle.
    if getattr(sys, "_MEIPASS", None):
        assert bundle == Path(sys._MEIPASS) / "migrations_bundle"  # noqa: SLF001
    else:
        assert bundle == BACKEND_DIR


def test_migration_failure_does_not_crash_boot(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Falha de migração não derruba o boot: main() loga e segue pro uvicorn."""
    import desktop_entry

    booted: dict[str, object] = {}

    def _boom() -> None:
        raise RuntimeError("alembic explodiu")

    def _fake_uvicorn(app: object, host: str, port: int) -> None:
        booted["app"] = app
        booted["host"] = host
        booted["port"] = port

    monkeypatch.setattr(desktop_entry, "run_migrations", _boom)
    monkeypatch.setattr(desktop_entry.uvicorn, "run", _fake_uvicorn)

    desktop_entry.main(["--host", "127.0.0.1", "--port", "9999"])

    # Boot seguiu apesar da falha de migração e chegou ao uvicorn.
    assert booted["host"] == "127.0.0.1"
    assert booted["port"] == 9999
    assert booted["app"] is not None
