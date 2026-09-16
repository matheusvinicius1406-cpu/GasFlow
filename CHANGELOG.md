# Changelog

Todas as mudanças relevantes do GasFlow, agrupadas por release.

## [Unreleased]

### 📱 F2 — Mobile RN: navegação com gates + consentimento LGPD + fila offline ponta a ponta (16/09/2026)

Implementação da F2 do `docs/entregas-cupons-spec.md`:

- **RootNavigator com gates** (`src/navigation/`): login → consentimento →
  rota do dia → detalhe da entrega. Swipe desabilitado nos gates (não puláveis);
  splash mínimo enquanto o consentimento persistido carrega (sem flash).
- **ConsentScreen LGPD (B3)**: bloqueante no 1º login, texto sem jargão (o quê,
  quando, retenção 90 dias, quem vê), checkbox obrigatória. Registro com data +
  `CONSENT_VERSION` no store zustand (`logic/session.ts`) com storage injetável
  (memória nos testes; AsyncStorage entra na F2.5). Termo antigo ou storage
  quebrado = fail-closed (pede de novo).
- **Fila offline ponta a ponta (C4.3)**: contêineres wired (`src/containers/`)
  ligam as telas ao store + `OfflineQueue` + `POST /driver/deliveries/:id/:action`
  com `client_action_id` no corpo. Sem rede: ação fica `pending` e reenvia no
  flush ao reconectar; duplicata nunca chega ao servidor (1 POST por id).
- **API pura (`logic/api.ts`)**: login `/auth/mobile/login`, entregas e ações
  com baseUrl/fetch/token injetáveis — testável em node --test.
- Fix de dependências (`react-native-screens` 4.x, `react-native-permissions`
  5.x — versões nos package.json não existiam mais no registry) e do script de
  teste para glob (`node --test "tests/**/*.test.ts"` — Node 24/Windows não
  aceita diretório como alvo).
- Sem build nativo nesta fase (F2.5) — typecheck `tsc` cobre telas+navigator
  e suíte de lógica roda em CI.
- Testes: +7 mobile (5 consent gate fail-closed/versão do termo/persistência,
  2 replay offline→synced + não-duplicação). Suíte: mobile 16 ✅.

### 🗺️ F1b — Mapa do operador com posição dos entregadores (16/09/2026)

Implementação da F1b do `docs/entregas-cupons-spec.md`:

- **`DriverMap` (Leaflet + tiles OSM, sem API key)**: componente único
  reutilizável — marcadores circulares verdes (posição fresca) ou cinza
  (`is_stale`, >5min no backend), popup com nome e idade da posição,
  fitBounds automático, estado vazio instrutivo.
- **Páginas Entregas e Motoristas** (decisão do dono): mesmo componente nas
  duas telas; nomes dos motoristas juntados às posições no cliente.
- **Hook `useDriverLocations`**: consome o `GET /delivery/locations` (que já
  existia) com **polling de 30s** (padrão do repo — posição não vai por WS
  para evitar refetch storms, ver `lib/realtime.ts`).
- Sem coordenadas em logs/telemetria (LGPD).
- Testes: +3 frontend (`DriverMap` com Leaflet mockado: vazio, render,
  cleanup). Suítes: frontend 196 ✅, backend 1448 ✅ (F1a).

### 🚀 F1a — Entregador desktop: sessão, notificação e rastreio configurável (16/09/2026)

Implementação da F1a do `docs/entregas-cupons-spec.md` (fase 1 de 9):

- **Notificação de atribuição em tempo real (<10s)**: dois fixes no roteamento
  do WebSocket — `delivery.assigned` (publicado com o motorista como actor
  `DRIVER`) agora roteia também para o canal `driver:{id}`; e o check de tenant
  do `/ws` não fecha mais conexões de motorista com 4003 (canal `driver:{id}`
  não contém o tenant; permitido apenas para o próprio `driver_id` da sessão).
- **Guard de sessão no desktop**: com `driver_token` ativo e sem token de
  operador, `DashboardLayout` renderiza só o app do motorista (sem sidebar,
  header, RealtimeBridge de operador ou IA flutuante). Operador visitando
  `/driver` (os dois tokens presentes) mantém o layout admin intacto.
- **Intervalo de rastreio configurável**: nova setting
  `driver.tracking.interval_seconds` (default **120s**, min 15, categoria
  operations) exposta em `GET /driver/me`; o app do motorista throttleia o
  envio de GPS pelo intervalo (watchPosition continua capturando a melhor
  posição, o envio é que respeita a bateria).
- Testes: +2 backend (roteamento assignment → driver channel; sem actor
  DRIVER não roteia). Suítes: backend 1448 ✅, frontend 193 ✅, desktop 41 ✅.

### 🏗️ Reorganização Estrutural — v1.1.6 (16/09/2026)

Implementação completa do `docs/reorg-plan.md` (F1–F6):

- **Sidebar em 8 grupos** (era 18 itens chapados): Dashboard, WhatsApp
  (Conversas/Contatos/Campanhas/Automações/Contas & Conexão), Pedidos,
  Entregas (Entregas/Motoristas), Clientes (Lista/Segmentos/Recompra/Cupons),
  Produtos & Estoque (Produtos/Estoque/Notas de Compra), Financeiro &
  Relatórios, Configurações (Geral/Usuários/Auditoria/IA). Grupos colapsáveis
  que abrem sozinhos conforme a rota; fonte única em `nav.tsx` compartilhada
  entre desktop e mobile.
- **Módulo WhatsApp único**: rota `/contacts` removida — Contatos virou sub-rota
  `/whatsapp/contacts` (feature `contacts` absorvida pelo módulo whatsapp);
  `/whatsapp` agora é a home de Conversas; Campanhas em `/whatsapp/campaigns`;
  **Contas & Conexão** em `/whatsapp/accounts` (guard `whatsapp.read`) com a
  seção **WhatsApp Web** embutida (mesma flag `waWebPanel.enabled`) — rota
  `/whatsapp/web` removida.
- **IA como bolinha flutuante** (`FloatingCopilot`): FAB canto inferior-direito
  + slide-over com o chat do Copilot, persistência no localStorage, oculto em
  login/driver. Rota `/intelligence` e `IntelligencePage` **deletados**.
- **Backend em pastas por módulo** (`presentation/api/`): `whatsapp/`
  (accounts, gateway, automation, cloud_webhook, contacts), `catalog/`
  (products, inventory), `logistics/` (delivery*, dispatch, driver*),
  `finance/` (finance, payments, reports), `core/` (auth, health, settings,
  admin, dashboard). **Rotas de API preservadas** — única exceção:
  `/clients/contacts` → **`/whatsapp/contacts`** (consumidor único = nossa UI;
  serviço WhatsApp atualizado em `crm-sync.ts`).
- **POST /whatsapp/contacts/sync** movido para o namespace de contatos
  (mesma semântica de proxy ao serviço Node).
- **Limpeza total do banco (migration v4, `reorg_cleanup_v4`)**: clients,
  whatsapp_conversations/messages, ai_* e afins zerados no boot + catálogo
  real semeado — Água 20L R$10 e Gás P13 R$120 (cartão 1x R$125 / 2x R$130).
  `auth_*`, `system_settings` e RBAC intocados. Backup automático pré-migration.
- Suítes: backend 1446 ✅, frontend 193 ✅ (194 − 1 teste do
  IntelligencePage deletado com a rota; +3 novos do Copilot/WhatsApp),
  whatsapp 94 ✅, desktop 41 ✅,
  mobile 9 ✅.

### 🧪 Protótipo — Painel WhatsApp Web (14/09/2026)

- **Híbrido WhatsApp Web no desktop (F0–F5)**: WebContentsView com WhatsApp
  Web dentro da janela do GasFlow, para **apenas pairing, status e
  visibilidade operacional** — o envio continua 100% no Baileys. Uma view por
  conta (`persist:wa-web-<accountId>`), UA Chrome pinado, permissões negadas
  (câmera/mic/geo/notificações), healthcheck de presença (sem scraping).
- **Feature flag `waWebPanel.enabled` (default OFF)**: com a flag off,
  nenhum WebContentsView é instanciado e a página React mostra "desativado".
- Tela `/whatsapp/web` (guard `whatsapp.read`): abas por conta com badges de
  estado, botões abrir/re-parear/fechar, bounds sincronizados via
  ResizeObserver e push de status view → main → React (≤5s).
- Documentação em `docs/whatsapp-web-panel.md` (backup de `Partitions/`,
  expectativa de duas sessões independentes, riscos e plano de teste manual
  por fase). Suítes: desktop 29 → **41**, frontend 189 → **194**.

### 🔧 Correções — WhatsApp (14/09/2026)

- **Recuperação por caminho de desconexão** no provider: `logged_out` (401)
  agora apaga as credenciais (`baileys_auth/<id>/`) com guard de re-entrância,
  timeout de 10s e erro logado, antes do re-init (antes: `disconnect()`
  mantinha as creds → loop com sessão inválida); 428/440 limpam apenas a
  sessão Signal (preserva creds.json) com backoff e escalam para wipe após
  3 falhas; 515 tem restart único antes de tratar como 428.
- **Telemetria de diagnóstico**: evento `close` do Baileys propaga
  `statusCode`/texto do Boom (`account.connection_closed`), toda transição
  de estado emite `account.state_transition` e o contador
  `disconnectsByReason` é exposto nos endpoints de health.
- Runbook de re-pareamento (QR) em `docs/whatsapp-recovery-runbook.md` —
  diagnóstico do incidente de 06/09: o loop real era 408 com QR nunca
  pareado (nem 401, nem 428). Suíte: 86 → 94 testes.

### 🚀 Funcionalidades — App do Entregador, Fase 1 (14/09/2026)

- **Mobile auth** (`/auth/mobile/login|refresh|logout`): access token 15min
  (mini-JWT HS256 stdlib, escopo `mobile`) + refresh 7d com rotação e
  detecção de replay (reuso revoga a família), rate limit 10 login/min/IP.
  Sem dependência nova (sem PyJWT). `_authenticate_driver` aceita sessão DB
  ou JWT mobile — desktop continua isolado. Ver `docs/driver-app.md`.
- **LGPD no rastreamento**: location em lote com janela de trabalho
  (`driver.work_hours.start/end`, admin edita; fora → 403 + audit),
  retenção de 90 dias com purge idempotente no boot, audit de cada
  acesso/ingestão (sem coordenadas no log).
- **Delta sync** `GET /driver/sync?since=` com tabela `offline_sync_log`.
- **Relay na nuvem** (`relay/`): FastAPI + WS registry + cache de última
  posição; Dockerfile/fly.toml prontos — **deploy não executado** (decisão:
  código local; ver `relay/DEPLOY.md`).
- **Desktop relay-client**: WebSocket outbound com backoff 1s→60s,
  settings `relay*`, IPC `gasflow:driver-location`.
- **Scaffold mobile** (`mobile/`): lógica pura testada (fila offline com
  client_action_id/backoff/cap 5min, work-hours fail-closed, fallback
  LAN→nuvem→offline) + telas RN do MVP escritas.
- **Testes**: +11 backend (`test_driver_mobile.py`), +6 relay, +4 desktop,
  +9 mobile lógicos.

### 🚀 Funcionalidades — Item 3: IA no boot (14/09/2026)

- **IA pronta no primeiro boot**: `desktop/src/main/ai-setup.ts` detecta o
  Ollama em background (nunca bloqueia o app), pede consentimento antes de
  instalar (~800 MB, uma vez) e baixa o modelo com progresso via IPC
  (`ai:status-changed`, `ai:download-progress`). Retry 3x com backoff;
  qualquer falha vira estado `unavailable` — o boot jamais é afetado.
  Ver `docs/ai-setup.md`.
- **Factory de LLM com toggle admin**: `ai.enabled` (default ON) no quadro
  de configurações derruba toda a IA em runtime, sem restart. Health check
  do Ollama cacheado por 30s (timeout 2s); Ollama indisponível →
  `NullProvider` (degradação graciosa — cenário B da Fase 4.2: **sem**
  fallback externo, dados nunca saem da máquina). Provider desconhecido
  degrada em vez de cair no mock.
- **Tela Admin → Inteligência** (`/settings/ai`, permissão `ai.configure`):
  status sem jargão ("IA pronta" / "Preparando IA… 45%" / "IA local
  indisponível"), toggle "Ativar Inteligência", seção Avançado colapsada e
  teste rápido. Nenhum termo técnico fora do Avançado.
- **Endpoints `/ai/status`, `/ai/test`, `/ai/settings` (GET/PATCH),
  `/ai/model/download`(+progress)** com RBAC (`ai.use`/`ai.configure`) e
  auditoria (`ai.settings.changed` com before/after, `ai.test.prompt` com
  **hash** do prompt — nunca conteúdo).
- **RBAC**: permissão `ai.configure` nova (MANAGER); `ai.use` concedida a
  OPERATOR (catálogo + matriz + fallback de domínio).
- **Testes**: +9 backend (`test_ai_provider.py`), +6 desktop
  (`ai-setup.test.ts`), +5 frontend (`AISettings.test.tsx`). Suítes:
  backend 1434 ✓, frontend 189 ✓, desktop 25 ✓; mypy/ruff/tsc limpos.

### 🔄 Mudanças de negócio (14/09/2026)

- **Débito de estoque na entrega (Decisão B3a)**: o estoque só é debitado
  quando a entrega é finalizada (`DELIVERED`) — 1 cheio sai e 1 vazio entra
  (`deliver_stock_atomic`, commit único e idempotente). O pedido `CONFIRMED`
  não debita mais; `CANCELLED` do pedido é no-op; cancelamento da entrega
  após `DELIVERED` reverte o débito (`reverse_delivery_stock_atomic`).
  Migração v3 one-shot e idempotente no boot reverte débitos prematuros de
  pedidos antigos (movimento `RESERVATION_REVERSAL` + auditoria em
  `auth_audit_log`; marca em `system_settings`).
  Ver `docs/migrations/2026-09-delivery-debit.md`.

### 🚀 Funcionalidades

- **CRM ↔ WhatsApp (contatos)**: push automático de contatos do WhatsApp
  para o CRM (`crm-sync.ts`) — no boot, ao conectar a conta e manualmente.
  Upsert idempotente por telefone em `POST /clients/contacts/sync-batch`
  (lotes de `BATCH_SYNC_SIZE`, tolerante a falhas de rede).
- **Import/export VCF**: `POST /clients/contacts/import-vcf` e
  `GET /clients/contacts/export-vcf` (parser vCard próprio, sem dependência).
- **Enriquecimento por IA**: `POST /clients/contacts/{codigo}/enrich` extrai
  endereço embutido no nome do contato (LLM, no-op seguro em falha).
- **Reativação de inativos**: `POST /clients/contacts/reactivate` (com
  `dry_run`) cria executions para clientes OPTED_IN inativos há N dias
  (`whatsapp_reactivate_days`/`_template`/`_enabled` nas Configurações ›
  Sistema). Idempotente por cliente/dia; envio pelo executor de automações.
- **Executor em background (opt-in)**: `AUTOMATION_POLL_SECONDS>0` processa
  executions PENDING automaticamente; default desligado (cron externo
  chamando `POST /whatsapp-automation/process-pending` continua válido).
- **Tool `update_client_address`**: a IA pode atualizar o endereço do
  cliente na conversa (requer confirmação, permissão OPERATOR).
- **Última interação no CRM**: mensagens recebidas atualizam
  `last_interaction_at` (base da elegibilidade de reativação).
- **Configurações do sistema no frontend**: painéis de Sistema (quadro de
  configurações por categoria) e Usuários/Permissões (matriz RBAC).
- **Página de Promoções/Cupons** conectada à API de cupons.

### 🐛 Correções

- `sync-batch` agora é **service-key only** (`require_whatsapp_service`,
  `X-GasFlow-Key`): sem fallback JWT — token de usuário vazado não consegue
  sobrescrever o CRM em lote; fail-closed sem chave configurada.
- Contexto de serviço usava `tenant_id="1"` (contatos invisíveis no CRM);
  alinhado ao tenant do admin (`"default"`).
- `NameError` de `Tuple` em `contacts/service.py` (derrubava o boot).
- Reativação usava `was_recently_contacted(days=)` (assinatura errada) e
  duplicava a fila em re-execução no mesmo dia (PENDING não contava como
  contato) — substituído por checagem de REACTIVATION do dia.
- Botão "Sincronizar WhatsApp" não empurrava contatos ao CRM (chamava
  `sync-batch` vazio com JWT); agora dispara o push real via serviço.
- Boundary test de CRM tolera campos de sync na entidade Client (checa
  `import` real, não menção textual).

### 📦 Dependências e build (12/09/2026)

- **Merge de 21 PRs do Dependabot na main**: GitHub Actions (upload-artifact
  7, build-push 7, login 4, metadata 6, setup-buildx 4), imagens Docker
  (`python:3.14-slim`, `node:26-slim` no frontend e whatsapp), pip do backend
  (pytest ≥9.1.1, pytest-asyncio ≥1.4.0, pytest-timeout ≥2.4.0, ruff ≥0.16.5,
  prometheus-client), npm do frontend (React 19.2, Vite 8, zod 4.5,
  lucide-react 1.40) e do whatsapp (tsx 4.23.13, @types/node 26.5).
- **Express 4 → 5** no serviço WhatsApp: `app._router` (removido no v5)
  substituído por despacho direto pelo Router no alias `/send`; coerção
  `String()` nos 15 usos de `req.params` (tipagem `string | string[]` do
  express 5). tsc/eslint/build e 86 testes passando.
- **Desktop**: TypeScript 5.8 → 6.0.3 e `@types/node` 22 → 24 (Electron 44
  embute Node 24.20); `electron-builder.yml` corrigido para o schema do
  electron-builder 26 (`publisherName` migrou para `signtoolOptions`) —
  desbloqueia `npm run dist`. Instalador NSIS 1.1.2 gerado e validado
  (asar + extraResources: backend exe, agent, whatsapp, frontend).
- TypeScript mantido em **6.0.3** no frontend/whatsapp: `typescript-eslint`
  8.70 ainda exige `<6.1` (TS 7 volta quando houver suporte).

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
