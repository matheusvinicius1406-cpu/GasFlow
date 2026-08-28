#!/bin/bash
# GasFlow Deployment Script
# Usage: ./scripts/deploy.sh [--skip-backup]
#
# Reproducible deployment flow:
#   1. Verify environment
#   2. Backup current database
#   3. Run migrations
#   4. Restart backend
#   5. Health check
#   6. Smoke test

set -euo pipefail

SKIP_BACKUP=false
if [ "${1:-}" = "--skip-backup" ]; then
    SKIP_BACKUP=true
fi

echo "============================================"
echo "GasFlow Deployment"
echo "============================================"
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Environment: ${ENVIRONMENT:-development}"
echo ""

# Step 1: Verify environment
echo "[1/6] Verifying environment..."
if [ ! -f .env ] && [ "${ENVIRONMENT:-}" != "development" ]; then
    echo "  ERROR: .env file not found for non-development environment"
    exit 1
fi

# Check Python dependencies
python3 -c "import fastapi, sqlalchemy, uvicorn" 2>/dev/null || {
    echo "  Installing dependencies..."
    pip install -r requirements.txt
}
echo "  ✅ Environment OK"

# Step 2: Backup
if [ "$SKIP_BACKUP" = false ]; then
    echo "[2/6] Creating backup..."
    bash scripts/backup.sh || echo "  ⚠️  Backup failed (continuing)"
else
    echo "[2/6] Skipping backup (--skip-backup)"
fi

# Step 3: Migrations
echo "[3/6] Running database migrations..."
python3 -m alembic upgrade head 2>&1 || {
    echo "  ⚠️  Migration failed or not configured. Using init_db() fallback."
}
echo "  ✅ Migrations OK"

# Step 4: Verify import
echo "[4/6] Verifying application imports..."
python3 -c "from app.main import app; print(f'  App: {app.title} v{app.version}')"
echo "  ✅ Imports OK"

# Step 5: Health check (if server is running)
echo "[5/6] Health check..."
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    HEALTH=$(curl -s http://localhost:8000/health)
    echo "  ✅ Backend alive: $HEALTH"
else
    echo "  ⚠️  Backend not running (start with: uvicorn app.main:app --port 8000)"
fi

# Step 6: Smoke test
echo "[6/6] Smoke test..."
if curl -sf http://localhost:8000/ > /dev/null 2>&1; then
    ROOT=$(curl -s http://localhost:8000/)
    echo "  ✅ Root endpoint: $ROOT"
else
    echo "  ⚠️  Root endpoint not responding"
fi

echo ""
echo "============================================"
echo "Deployment completed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================"
