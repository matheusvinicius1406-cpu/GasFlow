"""Seleção de migrações leves pelo dialeto real (R-1 do relatório LAB-01→LAB-05).

Em SQLite (app Desktop) a cadeia de migrações leves roda inteira, como
sempre. Em PostgreSQL ela é omitida: `PRAGMA table_info` (_ensure_sqlite_columns)
e `AUTOINCREMENT` (_seed_rbac_if_needed) são sintaxe SQLite, e a reorg
one-shot (_reorg_cleanup) não cabe num banco gerido pelo Alembic.

Antes da correção, o PRAGMA derrubava a cadeia inteira com
`ERROR: schema migration leve falhou` a cada boot em PostgreSQL — mesmo com o
banco já em `alembic head` — e deixava `_schema_version`/backfill/seed sem
executar, sem que ninguém percebesse.
"""

import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url

# Ordem exata da cadeia em init_db() — a seleção por dialeto deve preservá-la.
LIGHT_STEPS = [
    "_backup_before_migration",
    "_ensure_sqlite_columns",
    "_ensure_schema_version",
    "_backfill_stock_full_empty",
    "_revert_premature_stock_debits",
    "_reorg_cleanup",
    "_seed_rbac_if_needed",
]

POSTGRES_DSN = "postgresql+psycopg2://gasflow_lab:***@postgres:5432/gasflow_lab"


class _PostgresStubEngine:
    """Engine falso com URL de PostgreSQL real: qualquer conexão falha o teste."""

    def __init__(self) -> None:
        self.url = make_url(POSTGRES_DSN)
        self.connect_calls = 0

    def connect(self):  # pragma: no cover — só roda se a correção regredir
        self.connect_calls += 1
        raise AssertionError("não deve conectar: cadeia SQLite pulada em PostgreSQL")

    def begin(self):  # pragma: no cover
        self.connect_calls += 1
        raise AssertionError("não deve abrir transação em PostgreSQL")


class _CountingEngine:
    """Delega ao engine real, contando conexões (prova de que o caminho executou)."""

    def __init__(self, real) -> None:
        self._real = real
        self.url = real.url
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        return self._real.connect()

    def begin(self):
        self.connect_calls += 1
        return self._real.begin()


@pytest.fixture()
def calls(monkeypatch):
    """Espiona _bootstrap_schema e a cadeia leve sem tocar em banco algum."""
    from app.infrastructure.database import init_db as init_db_module

    recorded: list[str] = []
    monkeypatch.setattr(init_db_module, "_bootstrap_schema", lambda: recorded.append("_bootstrap_schema"))
    for name in LIGHT_STEPS:
        monkeypatch.setattr(init_db_module, name, lambda n=name: recorded.append(n))
    return recorded


def test_init_db_sqlite_executes_full_light_chain(calls, monkeypatch):
    """Comportamento SQLite preservado: bootstrap + as 7 etapas, na ordem."""
    from app.infrastructure.database import init_db as init_db_module

    monkeypatch.setattr(init_db_module, "engine", _CountingEngine(create_engine("sqlite:///:memory:")))

    init_db_module.init_db()

    assert calls == ["_bootstrap_schema", *LIGHT_STEPS]


def test_init_db_postgresql_only_bootstraps_schema(calls, monkeypatch):
    """PostgreSQL: só o bootstrap (Alembic/create_all); nenhuma etapa SQLite."""
    from app.infrastructure.database import init_db as init_db_module

    stub = _PostgresStubEngine()
    monkeypatch.setattr(init_db_module, "engine", stub)

    init_db_module.init_db()

    assert calls == ["_bootstrap_schema"]
    assert stub.connect_calls == 0


def test_init_db_postgresql_nao_loga_falha(calls, monkeypatch, caplog):
    """O boot em PostgreSQL não pode mais registrar o ERROR R-1."""
    from app.infrastructure.database import init_db as init_db_module

    monkeypatch.setattr(init_db_module, "engine", _PostgresStubEngine())

    with caplog.at_level(logging.DEBUG, logger="gasflow.init_db"):
        init_db_module.init_db()

    erros = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert erros == []
    assert not any("schema migration leve falhou" in r.getMessage() for r in caplog.records)


def test_ensure_sqlite_columns_noop_em_postgresql(monkeypatch):
    """PRAGMA é SQLite-only: em PostgreSQL a função vira no-op, sem conectar."""
    from app.infrastructure.database import init_db as init_db_module

    stub = _PostgresStubEngine()
    monkeypatch.setattr(init_db_module, "engine", stub)

    assert init_db_module._ensure_sqlite_columns() is None
    assert stub.connect_calls == 0


def test_ensure_sqlite_columns_conecta_no_sqlite(monkeypatch):
    """No SQLite a função continua executando (guard não pode travar o Desktop)."""
    from app.infrastructure.database import init_db as init_db_module

    counting = _CountingEngine(create_engine("sqlite:///:memory:"))
    monkeypatch.setattr(init_db_module, "engine", counting)

    init_db_module._ensure_sqlite_columns()

    assert counting.connect_calls == 1
