# Resolução de Pendências (WA-02 + GHCR + PIX + Redis + FE + RT-01)

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).


Data: 2026-09-04 · Branch `main` · v1.0.0-rc.3

## Round 2 — executado (rc.3)

### WA-02 — pareamento real + harness live ✅ (12/12)

- **Fix que destravou tudo**: `whatsapp/src/provider/wwebjs-provider.ts`
  ganhou `--disable-dev-shm-usage` nos args do Puppeteer. Sem isso o Chromium
  falhava ao lançar em container (Docker padroniza `/dev/shm` em 64M) e o
  whatsapp-web.js nunca chegava ao estado `qr_pending` — o QR jamais tinha
  sido exibido antes deste round. Também foi necessário limpar um
  `SingletonLock` obsoleto deixado por execuções anteriores no volume
  `gasflow_whatsapp_auth`.
- QR pareado ao vivo pelo usuário (sessão `primary` conectada,
  `559181689969`, persistida no volume).
- Harness live: `LIVE_MODE=true WHATSAPP_TEST_PHONE=559181689969
  WHATSAPP_PROVIDER=current WHATSAPP_SERVICE_URL=http://localhost:3001
  pytest tests/test_provider_live_harness.py -v` → **12/12 passed**
  (envio real de mensagem, idempotência, contatos, sessão, health, QR,
  stop/restart, erros).
- Restam os testes que exigem telefone de DESTINO adicional ou media
  (adapter não expõe media) — o núcleo do fluxo live está validado.

### GHCR — publicado ✅

- `git push origin main` (8a203de..f7c7d8f) e tag `v1.0.0-rc.2` enviados —
  workflow `build-push.yml` disparado no remote (GHCR: latest + tag).
- A tag `v1.0.0-rc.3` será publicada junto deste round.

### FE-02 — telas restantes ✅ (29 testes novos)

As 7 telas reais sem cobertura agora têm testes seguindo o padrão
apiClient-mock da suíte: CampaignResultsPage (6), ConversationsPage (5),
CopilotPage (4), IntelligencePage (1), ReorderPage (5), PaymentSettingsPage
(5), LoginPage (3). Total do frontend: **159 testes**. `tsc --noEmit` 0 erros.

Nota: a lista original da fase FE-02 citava SettingsPage/CampaignHistoryPage/
CampaignWizardPage/WhatsAppPage/SegmentsPage/AutomationsPage como pendentes —
essas **já tinham testes**; as realmente pendentes eram as 7 acima.

### E2E WhatsApp ✅ (spec real, CI-safe)

`e2e/tests/whatsapp.spec.ts`: página renderiza com as abas; estado
"Serviço Indisponível" quando a stack não tem o serviço whatsapp
(determinístico na stack E2E); teste de sessão pareada gated por
`E2E_WHATSAPP_CONNECTED=1` (pula em CI — exige serviço + QR na stack).

### PIX PSP — sandbox real permanece bloqueado 🔒

A imagem `openpix/openpix` **não existe** no Docker Hub (pull negado) — o
passo do prompt era fictício. Sandbox real (Gerencianet/PagSeguro/Mercado
Pago) exige conta + credenciais de homologação; o gateway + webhook HMAC já
estão implementados e testados com mock (10 testes) e prontos para receber
credenciais.

---

## Round 1 — executado (rc.2)

Todas as pendências levantadas nas fases anteriores foram tratadas. Status
por item — o que era resolvível localmente foi implementado, testado e
validado; o que depende de ambiente/credenciais/telefone físico está
documentado com o passo exato para executar.

## 1. RT-01 — Notificações de pedidos (order.*) ✅

- `EventType.ORDER_CREATED` / `ORDER_UPDATED` + helper `publish_order_event`
  em `app/domain/events/event_bus.py`.
- `orders.py` publica `order.created` (POST /orders), `order.updated`
  (PATCH status e assign-driver).
- Bridge (`setup_realtime_bridge`) agora assina `delivery.*`, `driver.*` e
  `order.*`.
- Frontend: `realtimeQueryKeys('order.*')` → invalida `['orders']` +
  `['dashboard']` (novo pedido aparece na lista/dashboard em segundos).
- Testes: FE realtime (+1) · backend realtime (13) · orders (33) verdes.

## 2. Redis Pub/Sub — Realtime multi-worker ✅

- **Contexto**: prod roda `BACKEND_WORKERS=2` — cada processo uvicorn tem seu
  próprio Event Bus + ConnectionManager; eventos de um worker não chegavam aos
  clientes WS do outro.
- `app/infrastructure/realtime/pubsub.py`: `RedisPubSub` (publish + listener
  async). Mensagens carregam `origin` (worker id); o listener ignora mensagens
  próprias (o worker de origem já fez o broadcast local) e roteia as dos
  outros workers para os canais locais.
- `ConnectionManager.broadcast_event` publica cross-worker quando habilitado;
  `broadcast_event_dict` roteia eventos remotos **sem** re-publicar (sem loop).
- Config: `REALTIME_BACKEND=memory|redis` (default memory). Em prod o
  `docker-compose.prod.yml` já define `REALTIME_BACKEND=redis` +
  `REALTIME_REDIS_URL=redis://redis:6379/0` (herda do rate limiter se ausente —
  sem o default `localhost` silencioso da lição GOLDEN).
- `main.py` lifespan inicia/cancela o listener quando `redis`.
- Testes determinísticos (sem Redis): `tests/test_realtime_pubsub.py` (8).
- **Validação ao vivo** (Redis real em container): worker-A publica
  `order.created` → worker-B recebe e roteia; origem ignorada. ✓

## 3. PIX PSP — camada de provedor + webhook de confirmação ✅ (parcial: real exige credenciais)

- `app/infrastructure/payment/psp_gateway.py`:
  - `MockPixProvider` (default, sem rede) — ciclo PENDING → CONFIRMED via
    `simulate_confirmation` (dev/testes).
  - `HttpPixProvider` (gerencianet | pagseguro | mercadopago) — exige
    `PSP_API_URL` + `PSP_API_KEY`; sem credenciais levanta `PspNotConfigured`
    na chamada (nunca tenta rede com config incompleta).
  - Assinatura de webhook: HMAC-SHA256 do corpo cru com `PSP_WEBHOOK_SECRET`.
- `POST /payments/webhook/pix` — recebe confirmação do banco, encontra o
  Payment por txid (`external_id` ou copy-paste; novos métodos de lookup no
  repo + service) e confirma com `confirmed_by="psp-webhook"`. Sem secret
  configurado → 503 (nunca aceita confirmação não assinada).
- Config `PSP_*` em `config.py` (e documentadas — o `.env.production.example`
  é dotfile e os editores do agente não o abrem; adicionar as chaves PSP lá ao
  rodar localmente, ou ver DEPLOY.md).
- Testes: `tests/test_psp_gateway.py` (10) — ciclo mock, factory, assinatura,
  endpoint (503/401/confirma/NOT_FOUND).
- **Pendência real**: validar com credenciais de um PSP de verdade
  (Gerencianet/PagSeguro/Mercado Pago) — sem credenciais não há como exercitar
  o wire real; o mock cobre o fluxo completo localmente.

## 4. FE-02 — telas restantes sem cobertura ✅ (subset)

Telas que REALMENTE não tinham teste (Settings/CampaignHistory/CampaignWizard
já eram cobertos desde o FE-02 original):

| Tela | Arquivo de teste | Estado |
|---|---|---|
| SegmentsPage | `segments/SegmentsPage.test.tsx` | ✅ (5) |
| WhatsAppPage | `whatsapp/WhatsAppPage.test.tsx` | ✅ (4) |
| AutomationsPage | `whatsapp/AutomationsPage.test.tsx` | ✅ (4) |

Cobertura: loading/list/empty/error + interações reais (avaliar segmento,
conectar conta, criar regra). Frontend total: **130 testes**.

Restantes (P2/baixa prioridade, sem mudança de comportamento): CampaignResults,
Conversations, Copilot, Intelligence, Reorder, PaymentSettings, LoginPage.

## 5. WA-02 — Testes live WhatsApp ✅ parcial (15/15) / 🔒 completa exige QR

**Executado nesta máquina** (com aprovação do usuário para parar o `twenty`
temporariamente e liberar a porta 3000):

- Subiu o serviço Node real do GasFlow em `:3000` (imagem `gasflow-whatsapp`,
  volumes vazios → contas `primary`/`secondary` em estado `disconnected`, sem
  sessão — sem risco de enviar mensagens reais).
- `pytest tests/test_provider_live_real.py -v` → **15 passed** contra o serviço
  real (sem mocks): health/uptime/memory, accounts (2), estrutura de status,
  criação de adapter, connection state/info/session, envio falha graciosamente
  com `NOT_CONNECTED`, isolamento multi-conta e latências.
- `twenty` religado em seguida (health `healthy`; o container original havia
  sido criado com ENCRYPTION_KEY que não estava em `.env`/shell — o usuário
  optou por gerar uma chave nova; sessões de login resetam e secrets de
  integrações criptografados com a chave antiga precisam ser reconectados).

**Bloqueio restante — suíte completa (`test_provider_live_harness.py`, 13
testes)**: exige `LIVE_MODE=true` + `WHATSAPP_TEST_PHONE` + **telefone real
pareado via QR** (escaneamento manual). Não há como automatizar o pareamento.

Para reproduzir:

```bash
# (a) com o twenty parado (ou porta 3000 livre), whatsapp do GasFlow em :3000
# (b) sem pareamento — valida o serviço real (15 testes)
cd backend && pytest tests/test_provider_live_real.py -v
# (c) com telefone pareado (QR) — suíte completa
LIVE_MODE=true WHATSAPP_TEST_PHONE=5511XXXXXXXXX \
  WHATSAPP_PROVIDER=current pytest tests/ -m live -v
```

## 6. GHCR — publicação das imagens ⚠️ depende de push (workflow pronto)

- `.github/workflows/build-push.yml` dispara em `main` e tags `v*.*.*`,
  publica backend/frontend/whatsapp no GHCR com `latest` + tag (credenciais
  via `GITHUB_TOKEN`, `packages: write`).
- Remote configurado: `github.com/matheusvinicius1406-cpu/GasFlow`.
- Para publicar basta (ação do usuário — requer autenticação no GitHub):

```bash
git push origin main
git push origin v1.0.0-rc.2
```

## 7. E2E WhatsApp ⚠️ depende do WA-02 (idem)

A suíte E2E de WhatsApp exige instância real pareada (mensagens reais).
Sem pareamento não há como escrever um teste E2E honesto. O `pix.spec`/
`auth.spec` etc. seguem verdes contra o stack real; quando houver sessão,
`e2e/tests/whatsapp.spec.ts` pode ser adicionado seguindo os fluxos reais da
tela (WhatsAppPage/ConversationsPage).

---

## Resumo

| Item | Status |
|---|---|
| RT-01 order notifications | ✅ implementado + testado |
| Redis pub/sub multi-worker | ✅ implementado + testado + validado live |
| PIX PSP (gateway + webhook) | ✅ mock completo + webhook seguro; real aguarda credenciais |
| FE-02 telas restantes | ✅ 3 telas novas (14 testes); total FE 130 |
| WA-02 live WhatsApp | ✅ 15/15 executados contra o serviço real; suíte completa 🔒 aguarda QR/telefone |
| GHCR | 🔒 workflow pronto; aguarda `git push` autenticado |
| E2E WhatsApp | 🔒 depende do WA-02 |
