# DP-01 — CI/CD + Deploy (relatório)

> Status: **CONCLUÍDO** — validado ao vivo com Docker.

## Implementado

- **`docker-compose.prod.yml`** — produção: sem bind mounts de source;
  postgres/backend na rede interna (sem portas); backend roda
  `alembic upgrade head` antes do uvicorn (schema 100% via migrations);
  healthchecks + `depends_on: service_healthy`; frontend (nginx) é a
  entrada pública.
- **`.env.production.example`** — todas as variáveis (Postgres, backend,
  frontend, whatsapp, placeholders IA/PIX) + `.env.example` consolidado.
- **CI** (`.github/workflows/ci.yml`) — PR/push em `main`:
  - backend: `ruff check app tests` + `pytest` (1117 testes)
  - frontend: `tsc` (via build) + `vite build` + `vitest` (62 testes)
  - whatsapp: `typecheck` + `build` (tsc) + testes
- **Imagens GHCR** (`.github/workflows/build-push.yml`) — backend/frontend/
  whatsapp em `ghcr.io/<repo>/gasflow-*`, tags latest/sha/vX.Y.Z.
- **`backend/requirements-dev.txt`** — reprodutibilidade (pytest, pytest-
  asyncio, pytest-timeout, ruff) antes inexistente.
- **`backend/ruff.toml`** + autofix + fixes (ver commit `29fdc65`).
- **`scripts/smoke-test.sh`** — smoke pós-deploy (SPA, health via nginx,
  docs, proxy whatsapp, login real + `/dashboard`).
- **`DEPLOY.md`** + seção Produção no README.
- **WhatsApp Dockerfile** — `npm run build` (dist é gitignored; imagem
  quebrava sem o passo) e `node:24-slim` (`node:sqlite` exige Node ≥ 22).

## Bugs reais encontrados na validação ao vivo

1. Backend não bootava na imagem: `bcrypt` e `reportlab` importados mas
   ausentes do requirements → adicionados.
2. WhatsApp em crash loop na imagem (`ERR_UNKNOWN_BUILTIN_MODULE`):
   `node:sqlite` não existe no Node 20 → imagem node:24.
3. `Optional[str, None]` inválido em 2 arquivos do automation engine
   (`TypeError` em import) → `Optional[str]`.
4. `whatsapp_repository.py` com sintaxe de import quebrada + interface
   financeira sem import de `LedgerEventType` (achados do ruff).
5. Dockerfile do whatsapp não compilava TS (`dist/` gitignored).

## Validação (executada)

```
docker compose -f docker-compose.prod.yml build   → 3 imagens OK
docker compose ... up -d                          → postgres/backend/frontend/whatsapp healthy
alembic upgrade head no PostgreSQL                → OK (39 tabelas)
./scripts/smoke-test.sh http://localhost:8080     → 5 ok / 0 falhas
  (SPA 200, /api/health 200, docs 200, whatsapp proxy 200,
   login admin → token → GET /dashboard 200)
```

## Pendências

- CI roda de fato quando houver push (workflows prontos; sem runner aqui).
- ESLint: repo não tem config; gate usa tsc (strict) + build + testes.
- Rate limiter em memória por worker (escala horizontal → Redis, ver SC-01).
- Config de HTTPS/TLS fora do escopo (nginx expõe HTTP).
