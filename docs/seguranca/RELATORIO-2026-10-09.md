# Relatório de segurança — matriz de rotas (2026-10-09)

Fase 1 das primeiras 48h do plano de estabilização. Escopo: apenas autenticação/autorização
da API existente. Nenhuma página, módulo, banco ou stack novo.

- Antes: `docs/seguranca/matriz-de-rotas-antes.{json,md}`
- Depois: `docs/seguranca/matriz-de-rotas-depois.{json,md}`
- Gerador: `backend/scripts/route_matrix.py` (`python scripts/route_matrix.py <saida.json>`)

## Método

O classificador não olha só `dependencies=[...]` no `APIRouter`/`@router.get`; ele
recrea o app e resolve a **cadeia de dependências** (incluindo transitivas e fábricas
como `require_permission("...")`), marcando cada operação como:

| classe | significado |
|---|---|
| `PERMISSAO` | exige permissão (`require_permission`/`require_role`) |
| `AUTENTICADA` | exige sessão (`get_tenant_context`) |
| `ADMIN` / `ENTREGADOR` / `ROLE` | gate por papel |
| `SERVICO` | chave de serviço (`X-GasFlow-Key`/Bearer), sem usuário |
| `SOMENTE_DB` | só `get_db` — sem credencial, escopo por banco |
| `SEM_AUTH?` | nenhuma dependência de credencial |
| `PUBLICA_DESIGN` | pública de propósito (identificada por whitelist) |

668 operações / 582 paths, idênticos antes e depois (nenhuma rota nova).

## Resultado

| classe | antes | depois |
|---|---:|---:|
| `PERMISSAO` | 182 | 246 |
| `AUTENTICADA` | 267 | 276 |
| `SEM_AUTH?` | **87** | **18** |
| `SOMENTE_DB` | 14 | 10 |
| demais | — | iguais |

**69 operações deixaram de ser anônimas.**

### Rotas corrigidas

1. **Proxy `/whatsapp/*`** (`app/presentation/api/whatsapp/accounts.py`) — 31 rotas.
   Passou a exigir `whatsapp.read` no router; `POST /accounts/{id}/messages` exige
   `whatsapp.send`. Antes qualquer anônimo listava contas, via QR, disparava mensagens
   e manipulava campanhas/listas/clientes do CRM via proxy.
2. **`POST /whatsapp/contacts/sync`** (`whatsapp/contacts.py`) — `whatsapp.read`.
3. **`GET /whatsapp/conversations`** (`whatsapp/gateway.py`) — sessão
   (`get_tenant_context`); vazava histórico de conversas.
4. **`POST /automation/workflows`** (`api/automation.py`) — sessão (única rota do módulo
   sem gate; as demais já exigiam sessão).
5. **`GET /ai/tools`** (`api/ai.py`) — sessão (única rota de `/ai` sem gate).
6. **`GET /segments/rules`** (`api/segmentation.py`) — sessão (única rota do módulo).
7. **`GET /automation/whatsapp/connection-check`** (`whatsapp/automation.py`) — sessão.
8. **`GET /realtime/stats`** (`infrastructure/realtime/websocket.py`) — sessão via
   `Depends(get_tenant_context)`; vazava contagem de conexões/tenants online.
9. **`GET /metrics`** (`app/main.py`) — gate no handler: liberado só com
   `METRICS_PUBLIC=1` (default **false**) ou com a chave de serviço (`X-GasFlow-Key`
   ou `Authorization: Bearer`, comparada com `hmac.compare_digest`). `docker-compose.yml`
   liga `METRICS_PUBLIC=true` porque o Prometheus da rede interna faz scrape.

### Exceções públicas por design (permanecem sem sessão)

`/`, `/health`, `/ready`, `/leads`, `/demo-request`, `/mobile/version`,
`/public/tracking/{token}`, `POST /payments/webhook/pix`, `POST /webhooks/alerts`,
`GET|POST /whatsapp/cloud-api/webhook`.

`GET /metrics` continua listado como `SEM_AUTH?` porque o gate é interno ao handler
(existe teste cobrindo 401/200).

## Evidência

```
backend$ python -m pytest tests/test_whatsapp_proxy_routes.py      # 8 passed
backend$ python -m pytest tests/test_auth_negative_matrix.py       # 23 passed
backend$ python -m pytest tests/test_realtime.py                   # 16 passed
backend$ python -m pytest -q -p no:randomly                        # 2263 passed, 30 skipped,
                                                                  # 1 failed* (pré-existente)
                                                                  # (24min49s)
backend$ ruff check <arquivos alterados>                           # limpo
backend$ mypy app                                                  # 0 errors (era 4; corrigidos)
frontend$ npx vitest run src/features/finance src/lib/utils.test.ts # 117 passed
```

- `tests/test_whatsapp_proxy_routes.py`: contrato de proxy + **401 anônimo**,
  **401 token inválido**, **403 para DRIVER** (usuário criado via `/admin/users`).
- `tests/test_auth_negative_matrix.py` (novo): 401/403 em todas as rotas corrigidas,
  caminho feliz autenticado e `/metrics` (401 anônimo → 200 com chave de serviço ou
  `METRICS_PUBLIC`).

\* `tests/test_routing_optimizer.py::test_reordena_com_ganho_real` — **confirmado
pré-existente**: rodado em worktree do commit `beab979` (antes de qualquer mudança
desta sessão) com a mesma venv → mesmo resultado (`provider="fallback"` vs
`"haversine"`), 1 failed / 7 passed. Nenhuma alteração em `app/application/routing`.

**Mypy**: os 4 erros do baseline (`app/application/contacts/renamer.py`) foram
corrigidos — `_chave` aceita `Optional[str]` (já tratava `None` em runtime),
narrowing de `nome` na cauda e `endereco: Optional[str]`. `mypy app` agora
termina com "Success: no issues found in 337 source files"; 78 testes de
renomeador continuam verdes.

## Status da Fase 1

> **Autenticação concluída** (SEM_AUTH 87→18, 69 operações corrigidas, 23 testes negativos).
> **Isolamento multiempresa (tenant_id em conversas/workflows) PENDENTE — P0.**
> Fase 1 **não fechada** até authz concluído.

O gate de sessão/permissão está no lugar. O que **não** está garantido ainda: um usuário
autenticado do tenant A não deveria ler conversas de tenant B — e o modelo de conversa
WhatsApp ainda não tem `tenant_id`. É porta trancada com fechadura que abre com qualquer
chave. Abrir issue P0 explícita antes de qualquer trabalho de multiempresa.

## Auditoria das 18 rotas SEM_AUTH? restantes

| rota | veredito | evidência |
|---|---|---|
| `POST /leads`, `POST /demo-request` | pública por design | honeypot (`website`) + validação de e-mail em `api/leads.py`; listagem exige `require_admin` |
| `GET /`, `/health`, `/ready` | pública por design | liveness/readiness de infra |
| `GET /mobile/version` | pública por design | app mobile precisa ler antes de logar |
| `GET /public/tracking/{token}` | pública por design | token assinado com **epoch** + `revoke` (ADMIN) em `public_tracking.py`; snapshot sem PII |
| `POST /payments/webhook/pix` | pública com assinatura | `verify_webhook_signature` (PSP) |
| `GET\|POST /whatsapp/cloud-api/webhook` | pública com assinatura | `X-Hub-Signature-256` validada, **fail-closed** sem `APP_SECRET` |
| `POST /webhooks/alerts` | **dívida** | `api/alerts_webhook.py` **não valida origem** — só loga. Aceitável só em rede interna; exposto = spam de log/DoS. Encaminhar: header de segredo ou restrição por IP no reverse proxy |
| `GET /metrics` | gate interno | handler exige `METRICS_PUBLIC=1` ou chave de serviço |

## Diagnóstico do alembic (17 migrations atrás)

Banco local `gasflow.db`: `alembic_version = f2b9d4c6a8e0`, head = `9f4b7e2a6c31`
(17 revisões). Mas o schema real tem **69 tabelas** e praticamente todos os objetos —
porque `init_db()` roda `create_all()` + migrações leves **em paralelo** às migrations.

- **Tabelas/colunas**: das 17 revisions, todas as tabelas declaradas já existem no banco.
- **Índices**: ~12 índices declarados nessas migrations **nunca foram criados**
  (`ix_auth_session_refresh_hash`, `ix_auth_user_driver_id`,
  `ix_driver_loc_hist_*`, `ix_tracking_alert_state_*`, `ix_clients_geocode_status`,
  `ix_geocode_cache_id`, `ix_contact_jobs_tipo`, `ix_coupons_invite_token`).
- **Consequência**: `alembic upgrade head` neste banco **falha** (tabela já existente)
  — e, mesmo que passasse, não criaria os índices que faltam por já existirem as tabelas.
- **Risco real**: qualquer migration futura que use `batch_alter_table` (SQLite) ou
  `ADD COLUMN` em tabela já criada pelo `create_all` entra nessa zona cinzenta. É o
  cenário clássico de "deploy que funciona no dev e quebra no Postgres/produção".
- Script de verificação: `C:\Users\mathe\AppData\Local\Temp\opencode\alembic_drift_check.py`
  (reexecutável; cruza migrations × schema real).

Ainda não apliquei nada no banco (nem `stamp`, nem índices). Requer decisão + backup.

## Verificação de impacto (antes de aplicar)

- Frontend (`frontend/src/lib/api/client.ts`): todas as chamadas do proxy passam pelo
  `apiClient` com Bearer — nenhuma chamada anônima de máquina.
- Desktop (`desktop/src/main/wa-bridge.ts`): fala direto com o serviço WhatsApp
  (`:3001`), não com o proxy; `desktop/src/main/gasflow.ts` envia Bearer.
- Serviço WhatsApp (`whatsapp/services/*`): só chama
  `POST /whatsapp/contacts/sync-batch` e `POST /whatsapp/incoming`, ambos com
  `X-GasFlow-Key` (não foram tocados).

## Pendências conhecidas (não resolvidas aqui)

1. **Escopo por tenant**: `GET /whatsapp/conversations` e o catálogo de workflows em
   memória (`_workflows`) não têm `tenant_id` — o modelo de conversa WhatsApp ainda não
   suporta multiempresa. Hoje o gate é de sessão/permissão, não de tenant.
2. **10 rotas `SOMENTE_DB`** (ex.: `POST /auth/mobile/*`, `POST /integrations/import`,
   `POST /public/referral/*`) — sem credencial no router; a importação de integração
   precisa de revisão.
3. **Alembic** (diagnóstico feito, correção pendente de decisão): banco local em
   `f2b9d4c6a8e0` vs head `9f4b7e2a6c31` (17 migrations); o schema real já tem as
   tabelas (via `create_all`), mas **~12 índices dessas migrations nunca foram
   criados** e `alembic upgrade head` falharia por tabela já existente. Ver seção
   "Diagnóstico do alembic".
4. **CI**: e2e >45min; TS7/typescript-eslint. (Mypy baseline resolvido: 0 erros.)
5. `/metrics` fora do compose precisa de `METRICS_PUBLIC=1` ou da chave de serviço no
   `prometheus.yml` correspondente (o de `monitoring/` aponta para `backend:8000`
   dentro do compose, que já liga a flag).
