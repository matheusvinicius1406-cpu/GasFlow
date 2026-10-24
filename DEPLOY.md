# Deploy — GasFlow

Guia de implantação da stack de produção (`docker-compose.prod.yml`).

## WhatsApp — motor e variáveis

O serviço WhatsApp usa **Baileys** (WebSocket puro, sem Chromium) por padrão:

```env
# Motor: baileys (default) | wwebjs (rollback, exige imagem com Chromium)
WA_ENGINE=baileys
# Alternativa ao QR no primeiro pareamento (opcional)
WA_PAIRING_CODE_PHONE=
# Nível de log interno do Baileys (default: error)
BAILEYS_LOG_LEVEL=error
```

Higiene de envio (campanhas): `WA_MINUTE_CAP`, `WA_HOURLY_CAP`, `WA_DAILY_CAP`,
`WA_RECIPIENT_COOLDOWN_MIN`, `WA_QUIET_HOURS_ENABLED/START/END`,
`WA_SEND_MEAN_MS`, `WA_SEND_STDEV_MS`, `WA_BROADCAST_ENABLED`.

Sessões: `baileys_auth/` (Baileys) e `wwebjs_auth/` (rollback) são volumes —
o primeiro pareamento (QR ou pairing code) só é necessário uma vez.
Rollback completo em `docs/phase16/BAILEYS_MIGRATION.md`.

## Pré-requisitos

- Docker Engine 24+ com Docker Compose v2+
- Acesso de escrita ao GHCR (`ghcr.io`) para as imagens (ou build local)
- Domínio + DNS apontando para o host (se exposto à internet)

## Arquitetura de produção

```
Internet → nginx (frontend, :80)                [frontend/nginx.conf]
             ├── /                      → SPA (try_files → index.html)
             ├── /assets/*              → estático (cache 1y)
             ├── /api/v1/*              → backend:8000  SEM strip  (FastAPI serve /api/v1/*)
             ├── /api/driver/*          → backend:8000  SEM strip  (namespace legado)
             ├── /api/*                 → backend:8000  COM strip  (/api → / p/ clients, orders, auth…)
             ├── /auth/*  /driver/*  /ws            → backend (app do entregador)
             ├── /health /ready /docs /openapi.json /redoc → backend
             ├── /payments/webhook/pix  → backend (callback do PSP)
             └── /metrics, /metrics/, /api/metrics → 404 (nunca exposto;
                                            Prometheus fala direto na rede
                                            interna com Bearer)
backend (:8000, interna)
   ├── postgres:5432 (interna)     — schema gerenciado por Alembic
   └── whatsapp:3000 (interna)     — serviço WhatsApp (bridge POST /whatsapp/incoming
                                     e scrape /metrics; ambos na rede interna)
whatsapp (:3001 host, opcional p/ pareamento QR)
prometheus / alertmanager / grafana  (--profile observability, só rede interna)
```

A matriz URL → destino está coberta por
`backend/tests/test_nginx_routing.py` (confere cada location contra as rotas
reais do FastAPI — regressões de strip/refixo quebram o teste sem Docker).

- **Frontend** (`nginx:alpine`) é a única porta pública padrão (`80`).
- **Postgres e backend** ficam na rede interna, sem porta exposta.
- **WhatsApp** expõe `3001` no host apenas para parear QR quando necessário.
- O backend roda `alembic upgrade head` antes de subir a API: **o schema de
  produção é 100% gerenciado por migrations** (o `create_all` do boot fica
  para dev/testes).

## Passo a passo

```bash
# 1. Configuração
cp .env.production.example .env.production
#    Preencha: POSTGRES_PASSWORD, ADMIN_PASSWORD, CORS_ORIGINS, MARCOS_GAS_API_KEY,
#    GRAFANA_ADMIN_PASSWORD (exigido pelo compose mesmo sem --profile observability)
#    ALERTS_WEBHOOK_SECRET (opcional; vazio = o Alertmanager leva 503 do backend)
#    Ajuste DATABASE_URL se o Postgres for externo.
#    Valide antes de subir:
docker compose -f docker-compose.prod.yml --env-file .env.production config -q

# 2. Build das imagens (ou use as do GHCR — veja "Imagens GHCR")
docker compose -f docker-compose.prod.yml --env-file .env.production build

# 3. Subir
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

# 4. Verificar saúde
docker compose -f docker-compose.prod.yml ps          # todos healthy?
./scripts/smoke-test.sh http://localhost              # (use a porta configurada)

# 5. Acompanhar logs
docker compose -f docker-compose.prod.yml logs -f backend
```

## Atualização (deploy novo)

```bash
git pull            # ou imagem nova no registry
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build --pull always
./scripts/smoke-test.sh
```

As migrations novas são aplicadas automaticamente no boot do backend
(`alembic upgrade head`). Backups do Postgres não são feitos pelo compose —
configure `pg_dump` agendado (cron) apontando para o volume `postgres_data`.

## Rollback

```bash
# 1. Voltar para a imagem/tag anterior
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build
#    (edite as tags no compose ou aponte o build para o commit anterior)

# 2. Se a migration NÃO tiver downgrade testado, restaure o banco do backup
#    antes de subir a versão anterior (migrations são forward-only por padrão).

# 3. Validar
./scripts/smoke-test.sh
```

> Regra: rode `alembic downgrade -1` somente em staging para validar o
> downgrade da migration ANTES de levar a produção. Em produção, o caminho
> seguro de rollback é restaurar o backup + subir a versão anterior.

## Imagens GHCR

O workflow `.github/workflows/build-push.yml` publica em
`ghcr.io/<owner>/<repo>/gasflow-{backend,frontend,whatsapp}` com tags:
`latest` (main), `sha-<commit>` e `vX.Y.Z` (tags `v*`).

Para usar as imagens em vez de build local, troque `build:` por `image:` no
compose e autentique o host:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u <owner> --password-stdin
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## CI/CD

- **CI** (`.github/workflows/ci.yml`): em todo PR/push para `main` roda
  backend (ruff + pytest), frontend (tsc + build + vitest), whatsapp
  (typecheck + build + testes) e E2E (Playwright contra o stack completo em
  `docker-compose.e2e.yml`).
- **Imagens** (`.github/workflows/build-push.yml`): em push para `main` e
  tags `v*`, builda e publica as 3 imagens no GHCR.

## Variáveis de ambiente

Todas documentadas em `.env.production.example` (PostgreSQL, backend,
frontend, whatsapp, IA e PIX com placeholders para fases futuras).

> Só entra no container o que está em `environment:` de cada service do
> `docker-compose.prod.yml`. As seções de IA/áudio do example (`AI_*`,
> `STT_*`, `TTS_*`, `PIPER_*`, `OPENAI_*`) ainda não são repassadas ao
> backend — acrescente a linha equivalente em `environment:` quando for
> habilitar esses recursos no deploy (as demais, incluindo
> `METRICS_PUBLIC`, `ALERTS_WEBHOOK_SECRET` e `WA_*`, já estão ligadas).

## Perfil Home Server (12 GB)

O `docker-compose.prod.yml` é dimensionado para um host de 12 GB:

| Grupo | Services | RAM (deploy.resources.limits) |
|---|---|---|
| Core (`up -d` padrão) | postgres, redis, backend, frontend, whatsapp | 512 + 128 + 1024 + 256 + 2048 = **3968 MB** |
| Observabilidade (`--profile observability`) | prometheus, alertmanager, grafana | 512 + 128 + 256 = **896 MB** |
| Total | core + observabilidade | **4864 MB** (~7 GB de folra p/ SO e Docker) |

- **O `up -d` padrão sobe só o core.** Prometheus/Alertmanager/Grafana entram
  com `--profile observability` (recomendado subir depois do core estar
  healthy). A interpolação `${GRAFANA_ADMIN_PASSWORD:?...}` é avaliada para o
  arquivo inteiro — por isso a senha é obrigatória mesmo sem o profile.
- Sem o profile não há scrape, mas a postura de métricas não muda:
  `/metrics` exige `Bearer == MARCOS_GAS_API_KEY` (401 sem a chave) e o nginx
  responde 404 em `/metrics` (nada de métrica pela borda).
- Saúde: `docker compose ps` (todos `healthy`) → `./scripts/smoke-test.sh` →
  `GET /health` (liveness) e `GET /ready` (database/redis/whatsapp).
- Disco: volumes `driver: local` para `postgres_data`, `whatsapp_data`,
  `whatsapp_auth`, `baileys_auth`, `whatsapp_uploads`, `whatsapp_export` e
  `backups_data` (mais `prometheus_data`/`grafana_data` com o profile).
  Backups do Postgres continuam sendo `pg_dump` agendado no host sobre o
  volume `postgres_data`.
- IA local: `AI_PROVIDER=ollama` aponta para `host.docker.internal:11434` e o
  modelo carregado consome RAM **fora** dos limites do compose — se o host for
  apertado, use `AI_PROVIDER=mock` ou limite a memória do Ollama.
- Evidências de config (rodam no CI, sem Docker): `backend/tests/test_prod_stack_config.py`
  (invariantes O1/O2, perfis, limits e volumes) e
  `backend/tests/test_nginx_routing.py` (matriz de roteamento).

## Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| `backend` reiniciando | migration falhou ou DB sem conexão | `docker compose logs backend`; rode `alembic upgrade head` manualmente no container |
| `/api/health` 502 | backend não saudável | `docker compose ps`; veja healthcheck do backend |
| WhatsApp 503 nos proxies | serviço whatsapp fora do ar | `docker compose logs whatsapp`; confira healthcheck `/api/health` |
| Login retorna 401/403 | `ADMIN_PASSWORD` errado no backend | confira `.env.production` e `docker compose exec backend env` |
| CORS bloqueado no browser | `CORS_ORIGINS` sem a origem exata | inclua `https://seu-dominio` (sem barra final) |

## Escala horizontal

O backend é stateless (sessões em memória **por worker**):
- Aumente `BACKEND_WORKERS` (workers uvicorn por contêiner).
- O rate limiter usa Redis compartilhado em produção (`RATE_LIMIT_MODE=redis`,
  default no `docker-compose.prod.yml`) — contadores globais entre workers;
  se o Redis cair, degrada para in-memory (fail-open, não derruba a API).
- O volume `whatsapp_auth` (sessão do WhatsApp) não é compartilhável entre
  réplicas: rode o whatsapp como 1 instância.

## Realtime (WebSocket)

O backend expõe `/ws` (canal por tenant, token na query string `?token=…`) e
empurra eventos de ciclo de vida de entregas/motoristas via Event Bus → WS
(ver `docs/phase15/RT01_DECISION.md`). O frontend conecta no `DashboardLayout`
e invalida as queries do React Query ao receber eventos `delivery.*`/`driver.*`
(entregas e dashboard reagem em segundos; polling de 30s permanece como
fallback).

Requisitos de proxy (já configurados):

| Camada | Config | Nota |
|---|---|---|
| Dev (Vite) | `server.proxy['/ws']` com `ws: true` em `frontend/vite.config.ts` | sem rewrite — o backend serve `/ws` na raiz |
| Prod (nginx) | `location /ws` com `Upgrade`/`Connection` + `proxy_http_version 1.1` em `frontend/nginx.conf` | timeouts de 3600s para conexões longas |

Multi-worker: com `REALTIME_BACKEND=redis` (default no compose prod) cada
worker publica eventos no Redis (`RedisPubSub`) e um listener por processo os
repassa aos clientes locais — eventos publicados em um worker chegam aos
WebSocket clients dos demais (necessário porque `BACKEND_WORKERS=2` cria um
ConnectionManager por processo). Mensagens carregam a origem e o worker que
publicou não re-entrega a si mesmo (sem duplicatas).

## PIX

- A chave PIX é configurada por tenant via API/UI (`/payments/pix`); o BR Code
  (copia-e-cola) e o QR Code são gerados pelo backend (`POST /payments/pix/payload`
  para um valor/pedido). Status por TXID: `GET /payments/pix/{txid}/status`.
- **PSP (PIX-02/pendência)**: `POST /payments/webhook/pix` recebe a confirmação
  do banco (HMAC-SHA256 do corpo com `PSP_WEBHOOK_SECRET` no header
  `X-Pix-Signature`), encontra o payment por txid e o confirma automaticamente
  (`confirmed_by=psp-webhook`). Sem secret configurado o endpoint responde 503.
  Na borda, o nginx encaminha esse caminho raiz (`location /payments/webhook/pix`);
  `/api/payments/webhook/pix` (strip) e `/api/v1/payments/webhook/pix` chegam ao
  mesmo handler — sem esse location o callback do banco receberia o HTML da SPA.
- Provedor: `PSP_PROVIDER=mock` (default, sem rede) | `gerencianet` |
  `pagseguro` | `mercadopago` (exigem `PSP_API_URL` + `PSP_API_KEY`; sem
  credenciais as chamadas falham com erro explícito — nunca tentam rede
  incompleta). Variáveis: `PSP_PROVIDER`, `PSP_API_URL`, `PSP_API_KEY`,
  `PSP_CLIENT_ID`, `PSP_CLIENT_SECRET`, `PSP_WEBHOOK_SECRET`.

## Testes E2E

- Suíte Playwright (`e2e/`) roda contra o stack **completo e real** em
  `docker-compose.e2e.yml` (postgres + redis + backend + frontend/nginx em
  `:8080`), sem o serviço whatsapp.
- Cobre os fluxos críticos pela UI + API real: login/rotas protegidas,
  cliente, produto, motorista, pedido (criação + confirmação de status) e
  PIX (configuração da chave + payload BR Code/QR).
- Rodar:
  ```bash
  docker compose -f docker-compose.e2e.yml up -d --build
  cd e2e && npm ci && npx playwright install chromium && npx playwright test
  ```

## Deploy em Produção (Checklist)

### Pré-deploy
- [ ] `git checkout main && git pull`
- [ ] `git tag` — conferir versão atual (ex.: `v1.0.0-rc.1`)
- [ ] `docker compose -f docker-compose.prod.yml --env-file .env.production config -q`
      (valida sintaxe/env — sem `--env-file` ele lê o shell e falha em
      `${VAR:?...}`)
- [ ] Variáveis definidas (`.env.production`): `POSTGRES_PASSWORD`,
      `ADMIN_PASSWORD`, `CORS_ORIGINS`, `MARCOS_GAS_API_KEY`, e
      `GRAFANA_ADMIN_PASSWORD` (exigido pelo compose mesmo sem
      `--profile observability`); `METRICS_PUBLIC=false` (default) e
      `ALERTS_WEBHOOK_SECRET` (recomendado) conforme
      `.env.production.example`
- [ ] Imagens: `docker compose -f docker-compose.prod.yml pull` (GHCR) ou
      `build` local

### Deploy
- [ ] `docker compose -f docker-compose.prod.yml --env-file .env.production up -d`
- [ ] Healthchecks: `docker compose ps` (postgres, redis, backend, frontend,
      whatsapp em `healthy`)
- [ ] Migrations: `docker compose logs backend` — `alembic upgrade head` sem erro
- [ ] Smoke: `./scripts/smoke-test.sh http://localhost` (9/9 — SPA, `/health`,
      `/ready`, `/api/v1` sem strip, `/auth/me` 401, `/driver/me` 401,
      `/metrics` 404, whatsapp 401, login + `/dashboard`)

### Pós-deploy
- [ ] `GET /api/ready` → `database`, `redis` e `whatsapp` ok
- [ ] Login admin na UI
- [ ] Rate limiter em Redis: 6+ logins errados → `429` e chave no Redis
      (`redis-cli --scan`); se DBSIZE=0 o Redis não está sendo usado — o
      `RATE_LIMIT_REDIS_URL` no container deve apontar para o host `redis`
      (não `localhost`; ver `docs/phase15/GOLDEN.md`)
- [ ] WebSocket: `ws://host/ws?token=<jwt>` → `welcome` + `ping`→`pong`
- [ ] PIX: `PATCH /api/payments/pix` (chave) → `POST /api/payments/pix/payload`
      → BR Code `000201…` + QR
- [ ] E2E: `docker compose -f docker-compose.e2e.yml up -d --build && cd e2e &&
      npx playwright test` (contra o stack de teste)

### Rollback
- [ ] `docker compose -f docker-compose.prod.yml down`
- [ ] Subir a tag anterior: troque a tag das imagens no compose (ou
      `git checkout <tag-anterior>` + `up -d --build`)
- [ ] O banco é compatível com migrations: rode `alembic downgrade -1` apenas
      se a versão anterior exigir (migrations são forward-only por padrão)

## Release

- Versão do frontend/whatsapp/e2e em `package.json` (o backend usa a tag Git
  como versão).
- `CHANGELOG.md` no root lista o que entrou em cada release.
- Tag semântica `v*` dispara `build-push.yml`, que publica as 3 imagens no
  GHCR com `latest` + tag da versão.
  ```bash
  git tag -a v1.0.0-rc.1 -m "Release Candidate 1"
  git push origin v1.0.0-rc.1
  ```
- Detalhes, decisões e bugs encontrados: `docs/phase15/E2E.md`.
