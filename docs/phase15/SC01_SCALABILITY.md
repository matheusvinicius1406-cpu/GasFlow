# SC-01 — Escalabilidade (Redis + Rate Limiting + Readiness)

**Status:** CONCLUÍDO — validado ao vivo (Redis real + fallback testado)

---

## Decisão sobre a branch de escalabilidade

`origin/claude/gas-flow-scalability-plan-80jlq7` foi revisada (`git fetch` +
`git log` + `git diff --stat main..branch`).

**Veredito: NÃO mesclar.** A branch é antiga (base `862fa57`, ~4 commits de
Fase 0–3 de um plano anterior) e o diff contra `main` atual é catastrófico:
**514 arquivos / −80.978 linhas**. Mesclá-la deletaria o serviço WhatsApp
completo, o frontend atual, as migrations Alembic, o infra de deploy (DP-01)
e praticamente todo o progresso dos últimos blocos.

Os itens do `docs/SCALABILITY_PLAN.md` (da branch) foram auditados um a um —
**quase todos já estão implementados em `main`**:

| Item do plano | Estado em main |
|---|---|
| FKs reais + migrations Alembic | ✅ 39 tabelas, baseline validado (DB-01) |
| config lendo .env | ✅ `Settings.from_env()` |
| Postgres ok | ✅ prod compose + smoke validado (DP-01) |
| JWT + RBAC + tenant isolation | ✅ Fases anteriores |
| Paginação | ✅ Contratos com `page/limit/total` |
| Testes + CI + logging estruturado | ✅ 1141 testes + workflows (DP-01) |
| **Redis (rate limit compartilhado)** | ⚠️ **ESTE PR** |
| **Readiness com dependências** | ⚠️ **ESTE PR** |

## O que foi implementado

### 1. Rate limiter com Redis (back-end compartilhado)

- `app/core/rate_limit_redis.py` (novo): `RedisSlidingWindowRateLimiter` —
  janela deslizante via ZSET do Redis (`ZREMRANGEBYSCORE` + `ZCARD` + `ZADD`
  + `PEXPIRE`), mesma interface do limiter in-memory (`check() -> (allowed,
  headers)`). Import de `redis` é lazy: dev/testes sem o pacote não quebram.
- `app/core/rate_limit.py`: middleware agora escolhe o back-end por
  `RATE_LIMIT_MODE`:
  - `memory` (default, single worker) — comportamento anterior intacto;
  - `redis` (produção multi-worker) — contadores compartilhados entre
    workers/instâncias.
- **Fail-open garantido em dois níveis**:
  1. Se o Redis estiver inacessível (circuit breaker com cache de 5s/30s),
     o middleware degrada para o limiter in-memory (nunca derruba a API);
  2. Qualquer exceção inesperada do limiter libera a request
     (`except: allowed=True`) com log — **rate limit nunca vira 500**.
- Config (`.env`/`.env.production.example`):
  `RATE_LIMIT_MODE`, `RATE_LIMIT_REDIS_URL`.

### 2. Readiness `/ready` com dependências

- `app/presentation/api/health.py`: `/ready` agora verifica:
  - `database` (crítico — `SELECT 1`);
  - `redis` (crítico **apenas** quando `RATE_LIMIT_MODE=redis`);
  - `whatsapp` (informacional — nunca derruba o probe).
- Status `ready` / `degraded`; `/ready` já era excludido do logging e agora
  tem política `public` no rate limiting.

### 3. Infra

- `backend/requirements.txt`: + `redis`
- `docker-compose.prod.yml`: serviço `redis:7-alpine` (rede interna,
  healthcheck, sem volume — contadores são efêmeros por design); backend
  recebe `RATE_LIMIT_MODE=redis` default e `depends_on: redis healthy`
- `docker-compose.yml` (dev): serviço `redis` + envs (paridade)

## Validação ao vivo (docker + uvicorn local)

1. Redis 7 em container + backend local com `RATE_LIMIT_MODE=redis`,
   `DATABASE_URL=sqlite`:
   - `/ready` → `{"status":"ready","checks":{"database":"ok","redis":"ok",
     "whatsapp":"error: timed out"}}` ✓ (whatsapp ausente é informacional)
2. **Rate limiting real**: 130 requests em `/health` (política public 120/min)
   → 119×200 + 11×429, com `X-RateLimit-Limit: 120`, `Remaining: 0`,
   `Retry-After: 6` ✓
3. **Fail-open**: `docker rm` do Redis com a API no ar →
   - `/ready` → `{"status":"degraded","checks":{"database":"ok",
     "redis":"unavailable",...}}` ✓
   - API continua respondendo 200 (fallback in-memory) + log de fallback ✓

## Testes

- `tests/test_rate_limit_redis.py` (novo, 10 casos): limiter Redis com fake
  client determinístico (janela, headers, expiração, independência de keys,
  circuit breaker) + fallback do middleware (redis caído → in-memory;
  limiter explodindo → fail-open).
- Suíte completa: **1141 passed, 27 skipped** (100s), ruff limpo.
- Compose: `config -q` OK em prod e dev.

## Riscos / pendências

- Contadores Redis não são atômicos entre leitura e escrita (subset para
  janela deslizante é aproximado sob concorrência extrema) — aceitável para
  rate limiting; pode evoluir para Lua script se necessário.
- `/ready` não é usado pelo healthcheck do compose (usa `/health` liveness)
  — disponível para orquestradores/probes externos.
- Testes de carga (ab/vegeta) não executados — dependem de hardware/ambiente;
  o comportamento foi validado com 130 requests reais.
