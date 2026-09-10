"""
Database Connection — Production Ready

Supports:
- SQLite (development) with WAL mode and FK enforcement
- PostgreSQL (production) with connection pooling
"""

import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

load_dotenv()


# Register custom datetime adapters for SQLite to avoid Python 3.12+
# deprecation warning about the default datetime adapter.
# Returns naive UTC datetimes for backward compatibility.
def _adapt_datetime(dt):
    return dt.isoformat()


def _convert_datetime(s):
    dt = datetime.fromisoformat(s.decode())
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("datetime", _convert_datetime)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine_kwargs = {
    "pool_pre_ping": True,  # Verify connections before use
}

if _is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_recycle"] = 3600

engine = create_engine(DATABASE_URL, **engine_kwargs)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ARG001 — assinatura exigida pelo evento
    if _is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
