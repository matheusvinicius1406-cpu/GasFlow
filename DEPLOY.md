# Deploy — GasFlow

Guia de implantação da stack de produção (`docker-compose.prod.yml`).

## Pré-requisitos

- Docker Engine 24+ com Docker Compose v2+
- Acesso de escrita ao GHCR (`ghcr.io`) para as imagens (ou build local)
- Domínio + DNS apontando para o host (se exposto à internet)

## Arquitetura de produção

```
Internet → nginx (frontend, :80)
             ├── /            → SPA (dist estático)
             ├── /api/*       → backend FastAPI (strip do prefixo)
             └── /docs|health → backend (rotas raiz)
backend (:8000, interna)
   ├── postgres:5432 (interna)     — schema gerenciado por Alembic
   └── whatsapp:3000 (interna)     — serviço WhatsApp (proxy /whatsapp/*)
whatsapp (:3001 host, opcional p/ pareamento QR)
```

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
#    Preencha: POSTGRES_PASSWORD, ADMIN_PASSWORD, CORS_ORIGINS, MARCOS_GAS_API_KEY
#    Ajuste DATABASE_URL se o Postgres for externo.

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
  backend (ruff + pytest), frontend (tsc + build + vitest) e whatsapp
  (typecheck + build + testes).
- **Imagens** (`.github/workflows/build-push.yml`): em push para `main` e
  tags `v*`, builda e publica as 3 imagens no GHCR.

## Variáveis de ambiente

Todas documentadas em `.env.production.example` (PostgreSQL, backend,
frontend, whatsapp, IA e PIX com placeholders para fases futuras).

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

Escala: o `ConnectionManager` é in-process (1 worker/proc). Para múltiplos
workers, usar Redis pub/sub para espalhar eventos entre processos (P2).

## PIX

- A chave PIX é configurada por tenant via API/UI (`/payments/pix`); o BR Code
  (copia-e-cola) e o QR Code são gerados pelo backend (`POST /payments/pix/payload`
  para um valor/pedido). Status por TXID: `GET /payments/pix/{txid}/status` —
  retorna `NOT_FOUND` até existir integração com PSP/webhook (confirmação é
  manual em `POST /payments/{id}/confirm`).
