# GasFlow — Operations Guide

## Quick Start

### Development (SQLite)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Development (Docker)
```bash
docker compose up -d
```

### Production (Docker)
```bash
ENVIRONMENT=production \
ADMIN_PASSWORD=<secure-password> \
POSTGRES_PASSWORD=<secure-password> \
CORS_ORIGINS=https://app.gasflow.com \
docker compose up -d
```

## Services

| Service | Port | Health Check |
|---------|------|--------------|
| Backend API | 8000 | GET /health |
| Frontend | 5173 (dev) / 80 (docker) | — |
| PostgreSQL | 5432 | pg_isready |
| WhatsApp | 3001 | GET /api/health |

## Database

### Migrations (Alembic)
```bash
# Apply all migrations
python -m alembic upgrade head

# Create new migration
python -m alembic revision --autogenerate -m "description"

# Rollback one step
python -m alembic downgrade -1

# Check current version
python -m alembic current
```

### Integrity Check
```bash
python scripts/db_integrity_check.py
```

## Backup & Restore

### Backup
```bash
# Manual backup
bash scripts/backup.sh

# Backup to specific directory
bash scripts/backup.sh /path/to/backups

# Automated (cron)
0 2 * * * cd /app && bash scripts/backup.sh
```

### Restore
```bash
# List available backups
ls -lh backups/

# Restore from backup
bash scripts/restore.sh backups/gasflow_development_20260101_020000.db
```

## Deployment

### Deploy
```bash
# Full deployment with backup
bash scripts/deploy.sh

# Deploy without backup
bash scripts/deploy.sh --skip-backup
```

### Rollback
```bash
# 1. Restore database from pre-migration backup
ls backups/*.pre-restore.*
bash scripts/restore.sh backups/gasflow_*.pre-restore.*

# 2. Rollback code (git)
git log --oneline -10
git checkout <previous-commit>
docker compose up -d --build

# 3. Rollback migration (if safe)
python -m alembic downgrade -1
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| ENVIRONMENT | development | development/staging/production |
| DEBUG | false | Enable debug mode |
| DATABASE_URL | sqlite:///./gasflow.db | Database connection string |
| ADMIN_PASSWORD | admin123 | Default admin password |
| CORS_ORIGINS | (dev defaults) | Comma-separated allowed origins |
| WHATSAPP_SERVICE_URL | http://localhost:3000 | WhatsApp service URL |
| LOG_LEVEL | INFO | Logging level |
| POSTGRES_PASSWORD | gasflow | PostgreSQL password (Docker) |

## Monitoring

### Health Endpoints
```bash
# Liveness (is process alive?)
curl http://localhost:8000/health

# Readiness (can accept traffic?)
curl http://localhost:8000/ready
```

### Logs
```bash
# Docker logs
docker compose logs -f backend

# Specific service
docker compose logs -f postgres
```

## Troubleshooting

### Backend won't start
1. Check `.env` file exists
2. Check database connectivity: `python scripts/db_integrity_check.py`
3. Check migrations: `python -m alembic current`

### Database errors
1. Run integrity check: `python scripts/db_integrity_check.py`
2. Check for missing migrations: `python -m alembic history`
3. Apply pending migrations: `python -m alembic upgrade head`

### WhatsApp service unavailable
1. Check service: `docker compose ps whatsapp`
2. Check logs: `docker compose logs whatsapp`
3. Restart: `docker compose restart whatsapp`

### Cross-tenant data leak
1. Run integrity check: `python scripts/db_integrity_check.py`
2. Check tenant_id on all records
3. Review repository filters
