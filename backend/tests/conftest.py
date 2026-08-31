"""
Pytest conftest — configures test-specific environment variables
and cleans sensitive data between test modules.

Each test file creates its own in-memory engine for isolation.
This conftest does NOT create tables — that's done per-engine
in each test's own db fixture.
"""

import os
import pytest

# Set test-specific environment variables BEFORE any imports
# This ensures Settings.from_env() uses test values
os.environ.setdefault("ADMIN_PASSWORD", "test_password_123")
os.environ.setdefault("ENVIRONMENT", "test")


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


def pytest_runtest_setup(item):
    """Clear rate limiter and auth singleton BEFORE every test.

    This is a hook that runs before every test's setup phase,
    including fixture setup. This ensures the RateLimiter buckets
    are always empty when a login fixture runs, preventing 429 errors
    that accumulate across test modules.
    """
    try:
        import app.presentation.dependencies as deps
        # Force a fresh auth service with clean rate limiter
        deps._auth_service = None
    except Exception:
        pass


def pytest_runtest_teardown(item):
    """Ensure rate limiter is cleared after each test item."""
    try:
        import app.presentation.dependencies as deps
        if deps._auth_service is not None:
            deps._auth_service._rate_limiter._buckets.clear()
    except Exception:
        pass
