# Changelog

Todas as mudanças relevantes do GasFlow, agrupadas por release.

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
- WA-02 (live WhatsApp): 15 testes do serviço real prontos — dependem da
  porta 3000 livre (projeto `twenty` do usuário a ocupa) e de telefone pareado
  (QR) para a suíte completa.
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
