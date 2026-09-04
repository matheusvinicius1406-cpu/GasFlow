# RT-01: Decisão de Realtime (WebSocket / SSE / Polling)

## Contexto

O GasFlow precisa refletir mudanças de **entregas** e **motoristas** (feitas via
`driver_api.py` / `assignment_service.py`) na tela do operador sem esperar o
próximo polling. O Dashboard hoje atualiza via `refetchInterval: 30000`; a página
de Entregas **não tem nenhum auto-refresh** (depende de refetch manual).

O que **já existe** no backend (construído nas fases 14/WA e **montado em
`main.py`**, mas **sem nenhum teste**):

| Componente | Local | Estado |
|---|---|---|
| `ConnectionManager` (canais `tenant:*`, `driver:*`, `delivery:*`, `operations:*`) | `app/infrastructure/realtime/websocket.py` | ✅ completo |
| Endpoint `GET /ws?token=&channel=` com auth (JWT admin OU sessão de driver) + isolamento por tenant | idem | ✅ completo |
| Ping/pong + `GET /realtime/stats` | idem | ✅ completo |
| Bridge Event Bus → WebSocket (`setup_realtime_bridge()` no lifespan) | idem + `main.py:53` | ✅ completo |
| Eventos reais publicados (delivery.assigned/accepted/started/arrived/completed/failed, driver.*) | `driver_api.py`, `assignment_service.py` | ✅ completo |
| Cliente WebSocket/SSE no frontend | — | ❌ ausente |
| Proxy `/ws` (dev vite + prod nginx) | `vite.config.ts`, `nginx.conf` | ❌ ausente |

## Opções avaliadas

### 1. Polling (estado atual)
- **Prós**: zero infra; já funciona para o Dashboard (30s).
- **Contras**: latência de até 30s; a página de Entregas **nem atualiza**;
  tráfego contínuo mesmo sem mudanças.
- **Veredito**: mantido como *fallback*, não como estratégia.

### 2. WebSocket (recomendado)
- Backend **já implementado e completo**: eventos de domínio de entrega/motorista
  são publicados no Event Bus e roteados por canal ao tenant correto com
  autenticação e isolamento.
- O que falta é **cliente**: conectar o frontend do operador a `ws://host/ws?token=…`
  (canal `tenant:{id}` derivado do token), e ao receber eventos de
  entrega/motorista invalidar as queries do React Query (`dashboard`,
  `deliveries`, `delivery-summary`, `delivery-drivers`, `orders`) → refetch
  imediato e seletivo.
- Também falta **teste** (nenhum) e **proxy** (dev e prod não encaminham `/ws`).
- **Prós**: bidirecional, baixa latência, reconexão automática, isolamento por
  tenant já embutido, escala via Redis pub/sub quando houver >1 worker.
- **Contras**: gerenciamento de conexão no cliente (resolvido por hook).

### 3. SSE (Server-Sent Events)
- **Prós**: simples, reconexão automática.
- **Contras**: unidirecional; **duplicaria o transporte** — o backend já empurra
  os eventos de entrega/motorista por WebSocket a partir do mesmo Event Bus.
  Para notificações ao operador (novos pedidos WhatsApp → alerta), o evento
  `order.created` ainda **não é publicado** no Event Bus — SSE não resolveria
  isso sem trabalho adicional de eventos; e o frontend precisaria de um
  segundo stream (SSE + WS) para o mesmo dado.
- **Veredito**: **rejeitado agora**. Revisitar somente se houver um consumidor
  unidirecional distinto (ex.: alertas push quando `order.created`/`payment.*`
  passarem a ser publicados no Event Bus).

### 4. Long Polling
- Legado; descartado.

## Decisão

**WebSocket, canal por tenant, com polling mantido como fallback.**

- Conecta com o mesmo token JWT do operador (`?token=…`); o servidor deriva o
  canal `tenant:{id}` e recusa conexões cujo canal não pertence ao tenant
  (código 4003).
- Eventos recebidos invalidam as queries do React Query → o Dashboard e a
  página de Entregas reagem em segundos às mudanças feitas pelo motorista.
- Polling de 30s do Dashboard permanece como rede de segurança (ex.: reconexão
  perdida), sem custo extra.
- Escala multi-worker (Redis pub/sub) fica como melhoria futura — o
  `ConnectionManager` já documenta isso e o RATE_LIMIT_REDIS_URL está disponível.

## Escopo executado nesta fase

1. **Backend**: testes determinísticos do `ConnectionManager` e do endpoint `/ws`
   (auth, ping/pong, isolamento por tenant) — o módulo estava sem nenhum teste.
2. **Proxies**: dev (`vite.config.ts` → `ws: true`) e prod (`nginx.conf` →
   headers de upgrade em `/ws`).
3. **Frontend**: hook `useRealtime` (reconexão com backoff + heartbeat) e
   `RealtimeBridge` montado no `DashboardLayout` que invalida queries em eventos
   `delivery.*` / `driver.*`.
4. **Documentação**: este documento + `DEPLOY.md`.

## Validação ao vivo (uvicorn real, não TestClient)

- Login admin real → `ws://localhost:8998/ws?token=…` → welcome com canal
  `tenant:default` (derivado do token) ✓
- `ping` → `pong` ✓
- `/realtime/stats` registrou a conexão (`tenant:default: 1`) ✓
- Entrega de eventos em processo (Event Bus → WS) coberta por testes
  determinísticos; em produção os eventos são publicados no mesmo processo
  do uvicorn (driver_api/assignment_service), então chegam às sockets
  conectadas.

## Fora de escopo (P2+)

- Publicar `order.created` / `payment.*` no Event Bus e criar alertas (ex.: novo
  pedido via WhatsApp) — pré-requisito para qualquer "notificações" reais por
  SSE ou WS.
- Escala multi-worker via Redis pub/sub (hoje single worker/proc no compose).
- Canal `driver:*` consumido por um app de motorista dedicado (existe endpoint,
  não existe consumidor frontend — o motorista opera via WhatsApp/API).
