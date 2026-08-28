#!/bin/bash
# GasFlow Database Restore Script
# Usage: ./scripts/restore.sh <backup_file>
#
# Restores database from a backup file with pre-restore safety checks.

set -euo pipefail

BACKUP_FILE="${1:-}"
RESTORE_DIR="./backups/restored"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    echo "Available backups:"
    ls -lh ./backups/gasflow_* 2>/dev/null || echo "  No backups found in ./backups/"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "[RESTORE] ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Load database URL from .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DATABASE_URL="${DATABASE_URL:-sqlite:///./gasflow.db}"

echo "[RESTORE] ============================================"
echo "[RESTORE] GasFlow Database Restore"
echo "[RESTORE] ============================================"
echo "[RESTORE] Backup: $BACKUP_FILE"
echo "[RESTORE] Target: $DATABASE_URL"
echo ""

# Step 1: Pre-backup safety backup
if [[ "$DATABASE_URL" == sqlite* ]]; then
    DB_PATH=$(echo "$DATABASE_URL" | sed 's|sqlite:///||')

    if [ -f "$DB_PATH" ]; then
        SAFETY_BACKUP="${DB_PATH}.pre-restore.$(date +%Y%m%d_%H%M%S)"
        cp "$DB_PATH" "$SAFETY_BACKUP"
        echo "[RESTORE] Safety backup created: $SAFETY_BACKUP"
    fi

    # Step 2: Verify backup file integrity
    echo "[RESTORE] Verifying backup integrity..."
    python3 -c "
import sqlite3
conn = sqlite3.connect('$BACKUP_FILE')
result = conn.execute('PRAGMA integrity_check').fetchone()
if result[0] == 'ok':
    print('[RESTORE] Backup integrity: OK')
else:
    print(f'[RESTORE] ERROR: Backup integrity check FAILED: {result[0]}')
    exit(1)
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print(f'[RESTORE] Backup contains {len(tables)} tables:')
for t in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM [{t[0]}]').fetchone()[0]
    print(f'  - {t[0]}: {count} rows')
conn.close()
"

    # Step 3: Restore
    echo "[RESTORE] Restoring database..."
    cp "$BACKUP_FILE" "$DB_PATH"
    echo "[RESTORE] Database restored."

    # Step 4: Verify restored database
    echo "[RESTORE] Verifying restored database..."
    python3 -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
result = conn.execute('PRAGMA integrity_check').fetchone()
if result[0] == 'ok':
    print('[RESTORE] Restored database integrity: OK')
else:
    print(f'[RESTORE] ERROR: Restored database integrity FAILED: {result[0]}')
    exit(1)
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print(f'[RESTORE] Restored database has {len(tables)} tables')
conn.close()
"

elif [[ "$DATABASE_URL" == postgresql* ]]; then
    echo "[RESTORE] PostgreSQL restore from SQL dump..."
    PG_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\).*|\1|p')
    PG_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    PG_DB=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
    PG_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\).*|\1|p')

    PGPASSWORD="${PG_PASSWORD:-gasflow}" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$PG_DB" < "$BACKUP_FILE"
    echo "[RESTORE] PostgreSQL restore completed."
else
    echo "[RESTORE] ERROR: Unsupported DATABASE_URL scheme"
    exit 1
fi

echo "[RESTORE] ============================================"
echo "[RESTORE] Restore completed successfully."
echo "[RESTORE] ============================================"
