"""
Database Connection — FASE 7.1

SQLite configuration:
- PRAGMA foreign_keys = ON (FK enforcement)
- PRAGMA journal_mode = WAL (concurrent reads during writes)
- PRAGMA busy_timeout = 5000 (wait up to 5s on lock contention)
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./gasflow.db"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    # WAL mode: allows concurrent reads during writes
    cursor.execute("PRAGMA journal_mode = WAL")
    # Busy timeout: wait up to 5 seconds on lock contention before raising
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)
