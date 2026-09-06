# Changelog

Todas as mudanças relevantes do GasFlow, agrupadas por release.

## [1.0.0-rc.4] - 2026-09-05

Resiliência do WhatsApp + integração com o app do entregador
(ver `docs/phase16/PHASE16_WHATSAPP_RESILIENCE_INTEGRATION.md`).

### 🐛 Correções

- **`--disable-dev-shm-usage` no arquivo errado (rc.3)**: o fix que destravou
  o QR em Docker estava em `wwebjs-provider.ts` (código morto); o runtime usa
  `provider-manager.ts`, que não tinha a flag. Movido para o caminho real.
- **Bridge de mensagens recebidas inexistente**: o serviço WhatsApp nunca
  enviava mensagens ao backend — o `POST /whatsapp/incoming` (IA + conversas)
  existia mas nada o chamava. Bot não funcionava ponta a ponta.

### 🚀 Funcionalidades

- **Heartbeat de presença** (`sendPresenceAvailable` a cada 5 min por padrão,
  `WA_HEARTBEAT_INTERVAL_MIN`) para manter a sessão ativa.
- **Reconexão endurecida**: 10 tentativas com backoff exponencial (5s→80s +
  jitter) e alerta webhook (`WA_CRITICAL_WEBHOOK_URL`) ao esgotar.
- **Envio de mídia**: `sendMedia` no contrato do provider + endpoint
  `POST /api/whatsapp/accounts/:id/media` (base64 ou mediaPath, idempotente).
- **Bridge de entrada whatsapp → backend**: mensagens recebidas são
  encaminhadas para `/whatsapp/incoming` (autenticadas via `X-GasFlow-Key`),
  e a resposta da IA é enviada de volta automaticamente (loop fechado).
- **Pacing humano de campanhas**: intervalo aleatório 2–10s entre envios
  (`WA_SEND_MIN/MAX_INTERVAL_MS`) no lugar do fixo de 2s.
- **Logs estruturados** (JSON lines) no serviço WhatsApp.
- **Auth service-to-service no backend**: `/whatsapp/incoming` aceita
  `X-GasFlow-Key` = `WHATSAPP_SERVICE_KEY`/`MARCOS_GAS_API_KEY`.
- **CI/CD do entregadorGasFlow**: workflow GitHub Actions (typecheck + build +
  testes) no repositório do app do entregador.

### 🧪 Testes

- WhatsApp: 38 → **53** (bridge de entrada + mídia).

### 🔐 Hardening anti-ban, canal oficial e motor Baileys (incluído na tag rc.4)

- **Anti-ban no serviço WhatsApp** (`src/anti-ban/`): caps por janela deslizante
  (20/min, 200/h, diário com warmup 50→1000 em 7 dias), cooldown por
  destinatário (60 min), quiet hours (22:00–07:00), pacing gaussiano (média 3s,
  σ 1s) — tudo persistido em SQLite (`send_history`, `send_counters`) e
  configurável por env (`WA_*`). Kill-switch `WA_BROADCAST_ENABLED`.
- **Canal oficial Cloud API (backend)**: `cloud_api_adapter.py` (texto, mídia,
  templates aprovados, E.164, erros mapeados, `list_message_templates`) +
  webhook assinado HMAC (`/api/v1/whatsapp/cloud-api/webhook`) + factory
  `WHATSAPP_PROVIDER=cloud_api`. Campanhas de massa devem migrar para cá.
- **Motor Baileys (dual-mode)**: `WA_ENGINE=baileys|wwebjs` (e
  `WA_ENGINE_PRIMARY/SECONDARY` por conta) — WebSocket puro, sem Chromium;
  pareamento por QR ou pairing code (`WA_PAIRING_CODE_PHONE`); rollback = 1
  env var. Dockerfile slim (`BUILD_WWEBJS=1` para build antigo).
- **Observabilidade**: `/metrics` Prometheus no serviço WhatsApp
  (`whatsapp_messages_sent_total`, `whatsapp_messages_failed_total`,
  `whatsapp_account_connected`, reconexões) e no backend
  (`gasflow_http_requests_total`, duração). Stack Prometheus + Grafana
  (provisionado) + Alertmanager no compose prod (`monitoring/`), com receiver
  `POST /api/v1/webhooks/alerts` no backend.
- **Segurança/CI**: Dependabot (npm/pip/docker/actions, semanal), job Trivy
  (CRITICAL+HIGH) no CI, pre-commit (ruff + ruff-format + higiene).
- **Testes**: WhatsApp 53 → **99** (anti-ban + engine Baileys + métricas);
  backend 1223 → **1244** (Cloud API, webhook, alerts); frontend 159 (devtools
  React Query em DEV).
- Backend: +4 testes HTTP de auth do `/whatsapp/incoming`.

## [1.0.0-rc.3] - 2026-09-04

Round de execução das pendências restantes (QR pareado ao vivo, GHCR
publicado, FE-02 completo).

### 🚀 Funcionalidades

- **WA-02 (pendência)**: pareamento real do WhatsApp concluído — QR escaneado
  e sessão `primary` conectada (número 559181689969) persistida no volume
  `gasflow_whatsapp_auth`.
- **WA-02 (pendência)**: harness live `test_provider_live_harness.py`
  **12/12 passando** contra o serviço real conectado (envio de mensagem,
  idempotência, contatos, sessão, health, QR, stop/restart, erros) —
  `LIVE_MODE=true WHATSAPP_TEST_PHONE=559181689969 WHATSAPP_SERVICE_URL=http://localhost:3001`.
- **FE-02 (pendência)**: testes para as 7 telas reais restantes
  (CampaignResultsPage, ConversationsPage, CopilotPage, IntelligencePage,
  ReorderPage, PaymentSettingsPage, LoginPage) — **29 testes novos**, frontend
  agora com **159 testes**.
- **E2E WhatsApp**: `e2e/tests/whatsapp.spec.ts` — renderização da página,
  estado de serviço indisponível (determinístico na stack E2E) e teste de
  sessão pareada gated por `E2E_WHATSAPP_CONNECTED=1` (CI-safe).
- **GHCR**: imagens publicadas — `git push origin main` + tag `v1.0.0-rc.2`
  enviados; workflow build-push disparado no remote.

### 🐛 Correções

- **whatsapp (`wwebjs-provider.ts`)**: adicionado `--disable-dev-shm-usage`
  aos args do Puppeteer — sem essa flag o Chromium não lançava em containers
  com `/dev/shm` de 64M (padrão Docker) e o QR nunca chegava ao estado
  `qr_pending`. Este é o fix que destravou o pareamento.
- **PaymentSettingsPage**: `fetchMethods`/`fetchConfigs` não limpavam o erro em
  sucesso — após um erro, o botão "Tentar novamente" nunca recuperava a tela
  (as demais páginas resetam o erro no refetch). Teste de regressão incluso.

## [1.0.0-rc.2] - 2026-09-04

Resolução de pendências levantadas nas fases anteriores (ver
`docs/phase15/PENDING_RESOLUTION.md`).

### 🚀 Funcionalidades

- **RT-01 (pendência)**: eventos `order.created`/`order.updated` publicados no
  Event Bus (criação, mudança de status e atribuição de motorista); bridge
  realtime assina `order.*`; frontend invalida lista de pedidos + dashboard.
- **Realtime multi-worker (pendência RT-01)**: Redis pub/sub opcional
  (`REALTIME_BACKEND=redis`) — eventos publicados em um worker uvicorn agora
  chegam aos WebSocket clients dos demais workers (prod roda `BACKEND_WORKERS=2`
  com um ConnectionManager por processo). Listener ignora eventos próprios
  (sem duplicatas) e roteia eventos remotos sem loops.
- **PIX PSP (pendência PIX-01)**: gateway de provedor (`mock` default +
  adapters HTTP p/ gerencianet/pagseguro/mercadopago) e webhook de confirmação
  `POST /payments/webhook/pix` (HMAC-SHA256) que encontra o payment por txid e
  confirma automaticamente.
- **FE-02 (pendência)**: testes para SegmentsPage, WhatsAppPage e
  AutomationsPage (loading/empty/error/list/interação) — total do frontend
  agora 130 testes.

### 🐛 Correções

- Nenhuma regressão; fixes de concorrência/sessão e do rate limiter Redis já
  estavam no rc.1 (GOLDEN).

### ⚠️ Limitações Conhecidas

- PSP real (Gerencianet/PagSeguro/Mercado Pago) aguarda credenciais para
  validação ao vivo (mock cobre o fluxo completo).
- WA-02 (live WhatsApp): 15 testes executados contra o serviço Node real
  (15/15 ✓, contas desconectadas — sem pareamento); a suíte completa
  (enviar/receber mensagens, 13 testes do harness) continua dependendo de
  telefone real pareado via QR.
- GHCR/E2E WhatsApp: aguardam push autenticado / pareamento (workflows e
  specs prontos).

## [1.0.0-rc.1] - 2026-09-04

Release Candidate 1 — primeira versão candidata a produção, cobrindo as fases
DB-01 → E2E + validação GOLDEN.

### 🚀 Funcionalidades

- **DB-01**: Migrations Alembic com baseline de 39 tabelas + drift guard.
- **DM-01**: Dashboard operacional com dados reais e KPIs.
- **API-01**: Contrato FE↔BE completo (0 divergências).
- **FE-01**: Inventário tela-a-tela (`docs/phase15/FE01_SCREEN_INVENTORY.md`).
- **DP-01**: CI/CD + Deploy (GitHub Actions + GHCR + `docker-compose.prod.yml`).
- **IA/Ollama**: Providers reais de LLM/STT/TTS (Ollama, Whisper, Piper) com
  fallback determinístico por ambiente (`MARCOS_GAS_*`).
- **SC-01**: Rate limiting com Redis compartilhado e fail-open in-memory;
  endpoints `/health` e `/ready`.
- **PIX-01**: Geração de PIX estático com BR Code (copia-e-cola) e QR Code
  (PNG base64), chave aleatória ou por tenant (`PixConfigRecord`).
- **FE-02**: Testes nas 11 telas sem cobertura (loading/sucesso/vazio/erro);
  cobertura do frontend subiu para ~57%.
- **RT-01**: Frontend conectado ao WebSocket por tenant já existente no backend
  (`useRealtime` + `RealtimeBridge` invalidando queries do React Query em
  eventos `delivery.*`/`driver.*`); proxies dev (`ws: true`) e prod (nginx
  `/ws` com Upgrade) configurados.
- **E2E**: Suíte Playwright contra o stack completo real em
  `docker-compose.e2e.yml` (8/8 estáveis): login/rotas protegidas, cliente,
  produto, motorista, pedido (criação + confirmação de status) e PIX.

### 🐛 Correções

- **AuthService: corrida de sessão DB** (E2E): o singleton de `AuthService`
  compartilhava UMA Session SQLAlchemy entre threads (threadpool + event loop
  do WS) — requests paralelas intercalavam `commit()`/queries e corrompiam a
  transação ("session is in 'prepared' state" → 500 para todo request
  autenticado). Fix: serialização com `RLock` + rollback em erro nos métodos
  que tocam DB + teste de regressão concorrente.
- **Rate limiter Redis ignorava `RATE_LIMIT_REDIS_URL`** (GOLDEN): o middleware
  construía `RedisSlidingWindowRateLimiter()` sem URL — o default
  `redis://localhost:6379/0` não alcança o Redis em container (host `redis`),
  então o circuit breaker degradava permanentemente para o fallback in-memory
  por processo (DBSIZE=0 em produção). Fix: passar `settings.rate_limit_redis_url`
  + testes de regressão do wiring.
- **ReportsPage**: estado de erro inalcançável (`Promise.allSettled`).
- **WhatsApp**: imagem migrada para `node:24` (node:sqlite).
- `bcrypt`/`reportlab` adicionados ao `requirements.txt`.
- `Optional[str, None]` → `Optional[str]` em agent_engine.
- **E2E**: specs idempotentes (telefones únicos por execução; login único via
  `storageState` para não estourar o rate limiter de login).
- **Nginx**: rota `/ws` com headers `Upgrade`/`Connection` + `proxy_http_version 1.1`.

### 📚 Documentação

- `DEPLOY.md` com arquitetura, passos, troubleshooting, escala e checklist de
  produção.
- `README.md` com badges de status, arquitetura e comandos.
- `docs/phase15/` com relatório de cada fase (DB-01 → E2E → GOLDEN).

### ⚠️ Limitações Conhecidas

- **WA-02 (live WhatsApp)**: testes ao vivo dependem de instância real pareada
  via QR — BLOCKED por ambiente; providers e testes com serviço real prontos.
- **RT-01**: `ConnectionManager` é in-process (1 worker/processo); Redis
  pub/sub para espalhar eventos entre workers é P2.
- **PIX-01**: status de pagamento é mock até integração com PSP/webhook
  (confirmação manual via `POST /payments/{id}/confirm`).
- Sessões de auth e de WhatsApp são em memória por worker/instância (1
  instância do whatsapp recomendada).
