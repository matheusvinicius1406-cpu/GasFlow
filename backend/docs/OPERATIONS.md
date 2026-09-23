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
| DELIVERY_SMART_ROUTING_ENABLED | false | Fase 8: sequenciamento de rota com OR-Tools |
| DELIVERY_SMART_DISPATCH_ENABLED | false | Fase 9: score de despacho extraído (DispatchScorer) |
| ROUTING_PROVIDER | haversine | Fase 10: `haversine` ou `osrm` |
| OSRM_BASE_URL | (vazio) | URL do OSRM self-hosted |
| OSRM_TIMEOUT_SECONDS | 2 | Timeout por request ao OSRM |
| OSRM_BREAKER_FAILURES | 3 | Falhas seguidas para abrir o breaker |
| OSRM_BREAKER_COOLDOWN_S | 60 | Janela do breaker antes da sondagem |
| ROUTING_DEFAULT_SPEED_KMH | 28 | Velocidade média assumida sem provedor real |
| DISPATCH_WEIGHT_PROXIMITY | 0.45 | Peso do componente de proximidade |
| DISPATCH_WEIGHT_LOAD | 0.25 | Peso do componente de carga |
| DISPATCH_WEIGHT_DEADLINE | 0.20 | Peso do componente de prazo |
| DISPATCH_WEIGHT_FAIRNESS | 0.10 | Peso do componente de justiça |
| DISPATCH_LOAD_FULL_DELIVERIES | 4 | Entregas concorrentes que "enchem" o entregador |

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

## Entregadores (drivers)

`delivery_drivers` é a **fonte única** de identidade do entregador. As tabelas
`delivery_records`, `driver_locations` e a de histórico guardam o `codigo`
(string de 6 dígitos), **não** o `id` — por isso **`codigo` é imutável**: trocá-lo
órfãa entregas, posições e histórico.

### Criar — `POST /admin/drivers` (canônico) e `POST /delivery/drivers` (alias)

`POST /admin/drivers` é o **caminho canônico**: cria a entidade `delivery_drivers`
+ o `User(role=DRIVER)` + a membership na mesma transação e devolve a **senha
temporária** (aparece uma única vez; o app exige a troca no primeiro acesso).
Requer admin.

`POST /delivery/drivers` é **alias documentado**: mesmo efeito e mesmo contrato de
resposta (`driver_id`, `username`, `temporary_password`). Antes ele criava **apenas
a entidade** — entregador sem credencial, que **não conseguia abrir o app**.

Os dois passam pelo `CreateDriverWithCredentialUseCase` (camada de aplicação),
então não voltam a divergir: **nenhum caminho público cria entregador sem
login**. O audit é gravado uma vez por criação.

### Editar — `PUT /delivery-drivers/{codigo}` (admin)

Campos editáveis: `nome`, `telefone`, `placa`, `document` (CPF/CNH),
`vehicle_id`, `status`. Atualização parcial. `codigo` no corpo → **422**.
Entregador de outro tenant → **404** (nunca 403, que vazaria a existência).

### Excluir — `DELETE /admin/drivers/{id}` (admin)

Soft delete, um efeito só:

1. `ativo=false` — o **cadastro** sai de circulação;
2. `status=DISABLED` — o **estado operacional** também (são dois conceitos:
   `ativo` é cadastro, `status` é operacional);
3. `User` vinculado desativado e **sessões revogadas** — o login morre na hora;
4. `tracking_epoch` incrementado — os **links públicos de rastreio** já emitidos
   passam a responder **410**;
5. registro em `auth_audit_log` (quem, quando, qual entregador).

Entrega em rota (`ASSIGNED`, `DISPATCHED`, `EN_ROUTE`) → **409** e nada é
alterado: excluir deixaria entrega órfã apontando para entregador desligado.
O histórico de entregas e posições é preservado — a linha nunca é apagada.

`PATCH /delivery-drivers/{codigo}/disable` é **alias** do mesmo use case
(mantido por compatibilidade).
