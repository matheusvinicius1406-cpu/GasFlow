# GasFlow — Disaster Recovery

## RTO/RPO Targets

| Scenario | RTO | RPO |
|----------|-----|-----|
| Database corruption | 15 min | Last backup (max 24h) |
| Backend crash | 2 min | 0 (no data loss) |
| Full server loss | 30 min | Last backup (max 24h) |
| Container failure | 1 min | 0 (stateless backend) |

## Recovery Procedures

### Scenario 1: Database Corruption

```bash
# 1. Stop the application
docker compose stop backend

# 2. Find last good backup
ls -lh backups/gasflow_* | tail -5

# 3. Restore
bash scripts/restore.sh backups/gasflow_development_YYYYMMDD_HHMMSS.db

# 4. Verify integrity
PYTHONIOENCODING=utf-8 python scripts/db_integrity_check.py

# 5. Restart
docker compose start backend

# 6. Verify
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### Scenario 2: Backend Crash

```bash
# 1. Check logs
docker compose logs --tail=50 backend

# 2. Restart
docker compose restart backend

# 3. Verify
curl http://localhost:8000/health
```

### Scenario 3: Full Server Loss

```bash
# 1. Setup new server with Docker
# 2. Clone repository
git clone <repo-url> GasFlow

# 3. Restore database from offsite backup
scp backup-server:backups/gasflow_production_*.db ./backups/
bash scripts/restore.sh backups/gasflow_production_*.db

# 4. Configure environment
cp backend/.env.example backend/.env
# Edit .env with production values

# 5. Start services
docker compose up -d

# 6. Verify all services
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### Scenario 4: Failed Migration

```bash
# 1. Stop backend
docker compose stop backend

# 2. Rollback migration
cd backend
python -m alembic downgrade -1

# 3. Restore database if needed
bash scripts/restore.sh backups/gasflow_*.pre-restore.*

# 4. Restart
docker compose start backend
```

## Backup Strategy

- **Automated**: Daily backup via cron at 02:00 UTC
- **Retention**: 30 days
- **Offsite**: Copy backups to external storage weekly
- **Testing**: Restore test monthly

## Monitoring Checklist

- [ ] Backend health endpoint responding
- [ ] Database connections healthy
- [ ] Disk space > 20%
- [ ] Memory usage < 80%
- [ ] Error rate < 1%
- [ ] Backup completed in last 24h
- [ ] No critical alerts
