"""
Pytest conftest — ensures all DB tables exist before tests run
and configures test-specific environment variables.

This is the single source of table creation for tests.
Prevents 'no such table' errors when driver_api.py uses
DB-backed idempotency/sessions instead of in-memory stores.
"""

import os
import pytest

# Set test-specific environment variables BEFORE any imports
# This ensures Settings.from_env() uses test values
os.environ.setdefault("ADMIN_PASSWORD", "test_password_123")
os.environ.setdefault("ENVIRONMENT", "test")

from app.infrastructure.database.base import Base
from app.infrastructure.database.init_db import engine


@pytest.fixture(scope="session", autouse=True)
def create_all_tables():
    """Create all tables at session start. Drop at teardown."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
