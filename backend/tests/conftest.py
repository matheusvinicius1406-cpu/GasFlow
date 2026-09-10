"""
Pytest conftest — configures test-specific environment variables,
isolates the database engine from the developer's gasflow.db and
cleans sensitive data between test modules.

Each test file creates its own in-memory engine for isolation.
Tests that rely on the app's global engine (TestClient, driver_api,
integration flows) are redirected to a throwaway file-based SQLite
in a temp dir, so the developer's backend/gasflow.db is never touched.
"""

import os
import shutil
import tempfile

import pytest

# Set test-specific environment variables BEFORE any imports
# This ensures Settings.from_env() uses test values
os.environ.setdefault("ADMIN_PASSWORD", "test_password_123")
os.environ.setdefault("ENVIRONMENT", "test")


def _build_isolated_engine():
    """Create a dedicated file-based SQLite engine for the whole test session.

    The global engine in app.infrastructure.database.connection points at the
    developer's backend/gasflow.db. This test engine points at a temp dir so
    create_all/drop_all and every TestClient-based test never touch dev data.
    """
    from sqlalchemy import create_engine, event

    test_dir = tempfile.mkdtemp(prefix="gasflow-tests-")
    engine = create_engine(
        f"sqlite:///{os.path.join(test_dir, 'test.db')}",
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        # Mirror the pragmas set in connection.py so tests run under the
        # same SQLite configuration as production.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    return engine, test_dir


ISOLATED_ENGINE, ISOLATED_DB_DIR = _build_isolated_engine()

# Rebind the production module attributes to the isolated engine.
# This MUST happen at conftest import time — BEFORE test collection imports
# app.main (which captures `engine` at module level in main.py:218) and
# tests/test_integration_dataflow.py (`from connection import engine,
# SessionLocal`). A fixture-based monkeypatch would run too late for those
# module-level captures, so we rebind the module attributes directly here.
import app.infrastructure.database.connection as _conn_module  # noqa: E402
import app.infrastructure.database.init_db as _init_db_module  # noqa: E402

_conn_module.engine = ISOLATED_ENGINE
_init_db_module.engine = ISOLATED_ENGINE
# SessionLocal is a shared sessionmaker object: configure(bind=...) mutates it
# in place, so even references captured before this line follow the new bind.
_conn_module.SessionLocal.configure(bind=ISOLATED_ENGINE)


@pytest.fixture(scope="session", autouse=True)
def setup_and_cleanup_db():
    """Create tables at session start, drop at end.

    Tables are created on the ISOLATED test engine (never on the dev
    gasflow.db). Tests that use TestClient(app) or driver_api.py depend on
    these. Also ensures the rate limiter is clear at session start.
    """
    from app.infrastructure.database.base import Base
    from app.infrastructure.database.init_db import engine

    Base.metadata.create_all(bind=engine)
    # Ensure rate limiter is clear at session start
    try:
        import app.presentation.dependencies as deps

        if deps._auth_service is not None:
            deps._auth_service._rate_limiter._buckets.clear()
    except Exception:
        pass
    yield
    Base.metadata.drop_all(bind=engine)
    # Session-wide teardown: release the isolated DB so the temp dir can go.
    ISOLATED_ENGINE.dispose()
    shutil.rmtree(ISOLATED_DB_DIR, ignore_errors=True)


@pytest.fixture(autouse=True, scope="module")
def clear_rate_limiter_module():
    """Clear rate limiter at module start.

    Conftest autouse fixtures run before test-file fixtures,
    so this executes before module-scoped login fixtures (admin_token)
    that would otherwise hit 429 from accumulated buckets.
    """
    _clear_rate_limiter()
    yield
    _clear_rate_limiter()


@pytest.fixture(autouse=True, scope="module")
def clean_db_module():
    """Clean sensitive tables between test modules to prevent UNIQUE violations."""
    yield
    # Truncate tables that accumulate data across test modules
    # (runs against the isolated test engine — never against gasflow.db)
    from sqlalchemy import text
    from app.infrastructure.database.init_db import engine

    tables_to_clean = [
        "whatsapp_conversations",
        "whatsapp_messages",
        "auth_sessions",
        "auth_audit_log",
    ]
    with engine.connect() as conn:
        for table in tables_to_clean:
            try:
                conn.execute(text(f"DELETE FROM {table}"))
            except Exception:
                pass
        conn.commit()


def _clear_rate_limiter():
    """Clear all rate limiter buckets.

    Clears BOTH:
    1. AuthService._rate_limiter (login-level rate limiting)
    2. core.rate_limit._limiter (middleware-level rate limiting)
    """
    try:
        import app.presentation.dependencies as deps

        if deps._auth_service is not None:
            deps._auth_service._rate_limiter._buckets.clear()
    except Exception:
        pass
    try:
        from app.core.rate_limit import _limiter

        _limiter._buckets.clear()
    except Exception:
        pass


def pytest_runtest_setup(item):
    """Clear rate limiter BEFORE every test.

    This hook runs before each test's setup phase.
    """
    _clear_rate_limiter()


def pytest_runtest_teardown(item, nextitem):
    """Clear rate limiter after each test and before next test's fixtures.

    The nextitem parameter lets us clear BEFORE the next test's
    module-scoped fixtures execute, fixing the 429 issue with
    admin_token fixtures.
    """
    _clear_rate_limiter()
