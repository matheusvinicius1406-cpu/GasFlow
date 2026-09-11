"""
Migration leve de schema (SQLite) — regressão do bug do app Desktop.

O banco do app instalado foi criado por uma versão antiga do backend:
`create_all()` não adiciona colunas em tabelas já existentes, então
`clients` ficou sem has_name/is_whatsapp/last_interaction_at/last_sync_at/
marketing_status → `no such column` em toda a aba Clientes, sync-batch,
reativação e tools de IA (89 ocorrências no log do app).

init_db._ensure_sqlite_columns() deve completar o schema sem perder dados.
"""

import os
import sqlite3
import tempfile

import pytest


def _create_old_clients_db(path: str) -> None:
    """Schema exatamente como estava no banco do app instalado (07/09)."""
    c = sqlite3.connect(path)
    c.execute(
        """CREATE TABLE clients (
        tenant_id TEXT, id INTEGER PRIMARY KEY, codigo TEXT,
        nome TEXT NOT NULL, telefone TEXT NOT NULL, telefone_secundario TEXT,
        rua TEXT NOT NULL, numero TEXT NOT NULL, complemento TEXT,
        referencia TEXT, bairro TEXT NOT NULL, observacoes TEXT,
        ativo BOOLEAN, tipo TEXT, email TEXT,
        updated_at TIMESTAMP, created_at TIMESTAMP)"""
    )
    c.execute(
        "INSERT INTO clients (tenant_id, codigo, nome, telefone, rua, numero, bairro, ativo)"
        " VALUES ('default','000001','Cliente Antigo','11999990000','Rua','1','Centro',1)"
    )
    c.commit()
    c.close()


@pytest.fixture()
def old_schema_db(monkeypatch):
    tmp = tempfile.mktemp(suffix=".db")
    _create_old_clients_db(tmp)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp}")
    monkeypatch.setenv("ADMIN_PASSWORD", "x-test-only")

    # O engine global é criado no import com o DATABASE_URL da sessão de
    # testes — apontamos o módulo init_db para um engine dedicado ao arquivo.
    from sqlalchemy import create_engine

    from app.infrastructure.database import init_db as init_db_module

    test_engine = create_engine(f"sqlite:///{tmp}")
    monkeypatch.setattr(init_db_module, "engine", test_engine)
    yield tmp
    test_engine.dispose()
    if os.path.exists(tmp):
        os.remove(tmp)


def test_ensure_sqlite_columns_completes_old_schema(old_schema_db):
    from sqlalchemy import text

    from app.infrastructure.database import init_db as init_db_module

    engine = init_db_module.engine
    # Engine aponta para o arquivo do teste (env acima)
    with engine.connect() as conn:
        before = {r[1] for r in conn.execute(text('PRAGMA table_info("clients")'))}
    assert "has_name" not in before

    init_db_module._ensure_sqlite_columns()

    with engine.connect() as conn:
        after = {r[1] for r in conn.execute(text('PRAGMA table_info("clients")'))}
        rows = conn.execute(text("SELECT nome, telefone, has_name FROM clients")).fetchall()

    missing = {"has_name", "is_whatsapp", "last_interaction_at", "last_sync_at", "marketing_status"}
    assert missing.issubset(after)
    # dado antigo preservado
    assert rows == [("Cliente Antigo", "11999990000", None)]


def test_ensure_sqlite_columns_is_idempotent(old_schema_db):
    from app.infrastructure.database import init_db as init_db_module

    init_db_module._ensure_sqlite_columns()
    # segunda passada não pode falhar nem duplicar colunas
    init_db_module._ensure_sqlite_columns()


def test_init_db_end_to_end_on_old_database(old_schema_db):
    """Boot completo: create_all + migration → INSERT com colunas novas funciona."""
    from app.infrastructure.database.init_db import init_db

    init_db()

    c = sqlite3.connect(old_schema_db)
    c.execute(
        "INSERT INTO clients (tenant_id, codigo, nome, telefone, rua, numero, bairro,"
        " ativo, has_name, is_whatsapp, marketing_status)"
        " VALUES ('default','000002','Novo','11999990001','Rua','2','B',1,1,1,'OPTED_IN')"
    )
    c.commit()
    total = c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    c.close()
    assert total == 2


def test_schema_version_recorded_and_idempotent(old_schema_db):
    """_schema_version: 1 linha, idempotente, reflete SCHEMA_VERSION atual."""
    from app.infrastructure.database import init_db as init_db_module

    init_db_module.init_db()
    init_db_module.init_db()  # segunda passada: upsert sem duplicar

    c = sqlite3.connect(old_schema_db)
    rows = c.execute("SELECT id, version FROM _schema_version").fetchall()
    c.close()
    assert rows == [(1, init_db_module.SCHEMA_VERSION)]


def test_backup_created_before_first_migration(old_schema_db):
    """A.3: primeiro boot num banco antigo grava backup antes de migrar."""
    from pathlib import Path

    from app.infrastructure.database import init_db as init_db_module

    init_db_module.init_db()

    backups_dir = Path(old_schema_db + ".backups")
    assert backups_dir.is_dir()
    backups = list(backups_dir.glob("*.db"))
    assert len(backups) == 1

    # O backup contém o dado ORIGINAL (a migration não tocou nele)
    bc = sqlite3.connect(backups[0])
    cols = {r[1] for r in bc.execute("PRAGMA table_info('clients')").fetchall()}
    nome = bc.execute("SELECT nome FROM clients").fetchone()[0]
    bc.close()
    assert "has_name" not in cols  # schema antigo, pré-migration
    assert nome == "Cliente Antigo"


def test_backup_not_duplicated_when_schema_is_current(old_schema_db):
    """A.3: banco já na versão atual → init_db NÃO cria backup novo."""
    from pathlib import Path

    from app.infrastructure.database import init_db as init_db_module

    init_db_module.init_db()  # migra + backupeia + versiona
    init_db_module.init_db()  # segunda passada: nada pendente

    backups = list(Path(old_schema_db + ".backups").glob("*.db"))
    assert len(backups) == 1  # só o da primeira passada
