# FASE 16 — Resiliência do WhatsApp + Integração dos 2 Repositórios

Data: 2026-09-05 · Branch `main` · v1.0.0-rc.4 (proposto)

## O que foi encontrado (bugs reais na análise)

1. **Fix do rc.3 estava no arquivo errado.** O `--disable-dev-shm-usage`
   (que destravou o QR em Docker) foi adicionado em `wwebjs-provider.ts` —
   código morto. O `server.ts` usa `provider-manager.ts`, que continuava SEM
   a flag. Em container, o Chromium continuaria falhando. **Corrigido no
   `provider-manager.ts`** (caminho real de execução).
2. **Mensagens recebidas NUNCA chegavam ao backend.** O serviço WhatsApp não
   fazia nenhuma chamada HTTP de saída; o endpoint `POST /whatsapp/incoming`
   (pipeline de IA + conversas) existia mas nada o chamava. O "bot responde
   automaticamente" não estava ligado de ponta a ponta. **Bridge implementado.**

## Implementado — GasFlow/whatsapp

| Item | Detalhe |
|---|---|
| Heartbeat | `sendPresenceAvailable()` a cada `WA_HEARTBEAT_INTERVAL_MIN` (default 5 min) após `ready`; parado em disconnect/stop/logout |
| Reconexão | 5 → **10 tentativas**, backoff exponencial 5s→80s com jitter; ao esgotar, dispara alerta webhook `WA_CRITICAL_WEBHOOK_URL` (fire-and-forget) |
| Envio de mídia | `sendMedia()` no contrato `WhatsAppProvider` (types.ts) + `POST /api/whatsapp/accounts/:id/media` (base64+mimetype ou mediaPath, idempotente como /messages) |
| Bridge de entrada | `src/incoming.ts`: mensagem recebida → `POST <GASFLOW_BACKEND_URL>/whatsapp/incoming` com `X-GasFlow-Key`; se o backend responder `outbound_text`+`outbound_to`, responde automaticamente (loop do bot). Ignora fromMe e mensagens de grupo; retry com backoff em 5xx; tolerante a falhas (nunca derruba o serviço) |
| Pacing humano | Broadcast worker com intervalo aleatório 2–10s (`WA_SEND_MIN/MAX_INTERVAL_MS`) no lugar do intervalo fixo de 2s — mantém protection mode |
| Logs estruturados | `src/log.ts` — JSON lines (`service: gasflow-whatsapp`), usado no provider-manager e no bridge |

## Implementado — GasFlow/backend

| Item | Detalhe |
|---|---|
| Auth service-to-service | `POST /whatsapp/incoming` agora aceita `X-GasFlow-Key` = `WHATSAPP_SERVICE_KEY` (fallback `MARCOS_GAS_API_KEY`); usuários continuam via Bearer. Sem chave configurada, só usuário autenticado passa (nada fica aberto) |
| Config | `whatsapp_service_key` em `core/config.py` |
| Testes | +4 testes HTTP (sem auth → 401, chave errada → 401, chave certa → 200, usuário Bearer → 200) — `tests/test_whatsapp_gateway.py` |

## Driver API (app do entregador) — validado

- 16 endpoints em `driver_v1.py` todos com `summary` (Swagger) — login,
  logout, me, deliveries (list/detail/accept/start/arrive/complete/fail),
  routes, GPS location, availability, proofs, sync.
- `tests/test_driver_api.py` + `test_auth_persistence.py`: **109 passed**.

## entregadorGasFlow (repositório separado) — CI/CD

- Workflow `.github/workflows/ci.yml` criado: typecheck (`tsc --noEmit`) +
  build (`tsc && vite build`) + testes (vitest) em Node 20.
- Estado local: typecheck 0 erros, 18 testes passando.
- App já aponta para `/api/v1/driver` (mesma namespace do backend).

## Compose / env

- `docker-compose.yml` e `docker-compose.prod.yml`: backend ganha
  `WHATSAPP_SERVICE_KEY`; serviço whatsapp ganha `GASFLOW_BACKEND_URL`,
  `GASFLOW_SERVICE_KEY` e os `WA_*`.
- `whatsapp/.env.example` criado; `.env.example`, `.env.production.example`
  e `whatsapp/.env` documentam as variáveis novas.

## Como ligar o bot ponta a ponta (dev local)

O `MARCOS_GAS_API_KEY` precisa do **mesmo valor** nos dois lados:

```bash
# backend/.env
MARCOS_GAS_API_KEY=minha_chave

# whatsapp/.env
MARCOS_GAS_API_KEY=minha_chave
GASFLOW_SERVICE_KEY=minha_chave
GASFLOW_BACKEND_URL=http://localhost:8000
```

Depois disso, mensagem recebida no WhatsApp → `/whatsapp/incoming` → IA do
GasFlow → resposta automática enviada de volta pelo mesmo número.

## Bloqueado (depende de ambiente/credenciais)

- **PSP PIX real** — mock + webhook HMAC prontos; exige credenciais de
  homologação (Gerencianet/PagSeguro/Mercado Pago).
- **Teste live de mídia** (`sendMedia` contra WhatsApp real) — exige telefone
  pareado via QR + telefone de destino.
- **E2E full stack (pedido → entrega → notificação → app)** — exige a stack
  Docker (docker-compose.e2e.yml) com o serviço whatsapp pareado.

## Evasão de bloqueio — posição

Implementamos **resiliência legítima**: pacing com comportamento humano,
heartbeat de presença, sessão persistente, reconexão com backoff e protection
mode (já existente). **Não** implementamos rotação de fingerprint/IP ou
stealth para burlar a política do WhatsApp — para volume garantido de
campanhas, o caminho recomendado é a WhatsApp Business Platform (Cloud API),
que tem o provider pattern pronto para receber um adapter.

## Números

| Suíte | Antes | Depois |
|---|---|---|
| WhatsApp (node:test) | 38 | **53** |
| WhatsApp typecheck | 0 erros | 0 erros |
| Backend whatsapp_gateway | 32 | **36** |
| Backend driver_api | 93 | 93 (+16 auth persistence) |
