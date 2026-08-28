#!/bin/bash
# GasFlow Database Backup Script
# Usage: ./scripts/backup.sh [backup_dir]
#
# Creates a timestamped backup of the database with integrity verification.
# Retention: keeps last 30 backups by default.

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
RETENTION_COUNT="${RETENTION_COUNT:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ENVIRONMENT="${ENVIRONMENT:-development}"

# Load database URL from .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DATABASE_URL="${DATABASE_URL:-sqlite:///./gasflow.db}"

# Extract SQLite path from URL
if [[ "$DATABASE_URL" == sqlite* ]]; then
    DB_PATH=$(echo "$DATABASE_URL" | sed 's|sqlite:///||')
    BACKUP_FILE="${BACKUP_DIR}/gasflow_${ENVIRONMENT}_${TIMESTAMP}.db"

    mkdir -p "$BACKUP_DIR"

    echo "[BACKUP] Starting backup..."
    echo "[BACKUP] Source: $DB_PATH"
    echo "[BACKUP] Destination: $BACKUP_FILE"

    # SQLite backup using .backup command (safe for concurrent reads)
    python3 -c "
import sqlite3
src = sqlite3.connect('$DB_PATH')
dst = sqlite3.connect('$BACKUP_FILE')
src.backup(dst)
dst.close()
src.close()
print('[BACKUP] Database copied successfully')
"

    # Verify backup integrity
    python3 -c "
import sqlite3
conn = sqlite3.connect('$BACKUP_FILE')
result = conn.execute('PRAGMA integrity_check').fetchone()
if result[0] == 'ok':
    print('[BACKUP] Integrity check: OK')
else:
    print(f'[BACKUP] Integrity check FAILED: {result[0]}')
    exit(1)
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print(f'[BACKUP] Tables: {len(tables)}')
for t in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM [{t[0]}]').fetchone()[0]
    print(f'  - {t[0]}: {count} rows')
conn.close()
"

    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[BACKUP] Completed: $BACKUP_FILE ($BACKUP_SIZE)"

elif [[ "$DATABASE_URL" == postgresql* ]]; then
    # PostgreSQL backup
    BACKUP_FILE="${BACKUP_DIR}/gasflow_${ENVIRONMENT}_${TIMESTAMP}.sql"
    mkdir -p "$BACKUP_DIR"

    echo "[BACKUP] Starting PostgreSQL backup..."
    # Extract connection details from URL
    PG_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\).*|\1|p')
    PG_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    PG_DB=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
    PG_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\).*|\1|p')

    PGPASSWORD="${PG_PASSWORD:-gasflow}" pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$PG_DB" > "$BACKUP_FILE"
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[BACKUP] Completed: $BACKUP_FILE ($BACKUP_SIZE)"
else
    echo "[BACKUP] ERROR: Unsupported DATABASE_URL scheme"
    exit 1
fi

# Cleanup old backups (keep last RETENTION_COUNT)
echo "[BACKUP] Cleaning up old backups (keeping last $RETENTION_COUNT)..."
cd "$BACKUP_DIR"
ls -t gasflow_${ENVIRONMENT}_* 2>/dev/null | tail -n +$((RETENTION_COUNT + 1)) | xargs -r rm -f
cd - > /dev/null

echo "[BACKUP] Done."
