"""
Pytest conftest — configures test-specific environment variables
and cleans sensitive data between test modules.

Each test file creates its own in-memory engine for isolation.
Tables on the file-based gasflow.db are created by init_db() when
the app starts. This conftest cleans them up at session end.
"""

import os
import pytest

# Set test-specific environment variables BEFORE any imports
# This ensures Settings.from_env() uses test values
os.environ.setdefault("ADMIN_PASSWORD", "test_password_123")
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture(scope="session", autouse=True)
def setup_and_cleanup_db():
    """Create tables at session start, drop at end.

    Tables are created on the file-based gasflow.db engine.
    Tests that use TestClient(app) or driver_api.py depend on these.
    Also ensures the rate limiter is clear at session start.
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
