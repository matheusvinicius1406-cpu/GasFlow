# Fase 16.1 — WhatsApp Anti-Ban Hygiene + Cloud API (Meta Oficial)

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).


> Escopo acordado: **sem camadas de evasão** (fingerprint spoofing, memory
> hooking, deteção de vigilância) — essas técnicas não reduzem o risco real
> (a deteção é server-side) e violam os termos da Meta. O que funciona é
> **higiene de volume** no canal não-oficial e o **canal oficial** para campanhas.

## Arquitetura resultante

| Tráfego | Canal | Risco |
|---|---|---|
| Conversacional (bot de pedidos, respostas) | `whatsapp-web.js` (`incoming.ts` → backend AI) | Baixo (1:1, iniciado pelo usuário) |
| Campanhas / notificações em massa | **WhatsApp Business Cloud API** (`cloud_api_adapter.py`) | ~zero (política-compliant) |
| Broadcast legado (listas pequenas e quentes) | `broadcast.ts` com higiene anti-ban | Médio — controlado por caps |

## Fase 1 — Higiene anti-ban (serviço Node)

Novos módulos em `whatsapp/src/anti-ban/`:

| Módulo | Função | Env |
|---|---|---|
| `limiter.ts` | Caps por minuto/hora (janela deslizante em SQLite `send_history`) + **cooldown por destinatário** | `WA_MINUTE_CAP` (20), `WA_HOURLY_CAP` (200), `WA_RECIPIENT_COOLDOWN_MIN` (60) |
| `warmup.ts` | Rampa diária progressiva 50→100→200→350→500→700→1000 (7 dias), contadores em `send_counters` | `WA_DAILY_CAP` (1000, pós-warmup) |
| `quiet-hours.ts` | Bloqueia envios 22:00–07:00 (hora local do servidor) | `WA_QUIET_HOURS_ENABLED` (true), `WA_QUIET_HOURS_START` (22), `WA_QUIET_HOURS_END` (7) |
| `gaussian.ts` | Delay gaussiano entre envios (média 3s, desvio 1s) substituindo o uniforme 2–10s | `WA_SEND_MEAN_MS` (3000), `WA_SEND_STDEV_MS` (1000) — `WA_SEND_MIN/MAX_INTERVAL_MS` viraram piso/teto |

Integração em `broadcast.ts` (ordem de avaliação):
1. Kill-switch `WA_BROADCAST_ENABLED=false` desliga o worker (Fase 3).
2. Quiet hours → worker pausa até `WA_QUIET_HOURS_END`.
3. Orçamento diário (warmup ou cap) → worker reavalia a cada 10 min.
4. Rate limit + cooldown → job devolvido para `PENDING` e worker pausado até abrir.
5. Envio; sucesso grava em `send_history` + `send_counters`.

Tabelas novas (migração automática no boot, `db.ts`): `send_history`
(indexada por conta+tempo e conta+destinatário), `send_counters`.

## Fase 2 — WhatsApp Business Cloud API (backend)

- `app/infrastructure/whatsapp_provider/cloud_api_adapter.py` — adapter oficial
  (texto livre na janela de 24h, mídia por link, **templates aprovados** para campanhas).
- `factory.py` — `WHATSAPP_PROVIDER=cloud_api` (ou `meta`) ativa o adapter.
- `app/presentation/api/whatsapp_cloud_webhook.py` — webhook
  `GET/POST /api/v1/whatsapp/cloud-api/webhook` com verificação de assinatura
  `X-Hub-Signature-256` (fail-closed sem secret) e parsing de statuses/mensagens.

### Setup (Meta Business)

1. Criar app no [Meta for Developers](https://developers.facebook.com) com produto WhatsApp.
2. Business verification + número verificado (ou número de teste).
3. Criar System User com token permanente e permissão `whatsapp_business_messaging`.
4. Templates de mensagem aprovados (ex.: `entrega_confirmada`, `pedido_recebido`).

### Variáveis de ambiente (backend)

```env
WHATSAPP_PROVIDER=cloud_api
WHATSAPP_CLOUD_API_TOKEN=EAAG...            # token permanente do System User
WHATSAPP_CLOUD_API_PHONE_NUMBER_ID=123456789
WHATSAPP_CLOUD_API_VERSION=v21.0
WHATSAPP_CLOUD_API_APP_SECRET=...           # valida assinatura do webhook (obrigatório p/ POSTs)
WHATSAPP_CLOUD_API_VERIFY_TOKEN=...         # handshake GET do webhook
# Templates por evento (opcionais, usados pelo helper template_name_for_event):
WHATSAPP_CLOUD_API_TEMPLATE_ORDER_RECEIVED=pedido_recebido
WHATSAPP_CLOUD_API_TEMPLATE_DELIVERY_CONFIRMED=entrega_confirmada
```

### Uso programático

```python
from app.infrastructure.whatsapp_provider.factory import create_provider

provider = create_provider("primary")  # usa WHATSAPP_PROVIDER do env

# Campanha (fora da janela de 24h): template aprovado
await provider.send_template(
    "5591999999999",
    template_name_for_event("DELIVERY_CONFIRMED") or "entrega_confirmada",
    body_params=["João", "Pedido #42"],
)

# Resposta conversacional (dentro da janela de 24h): texto livre
await provider.send_text(SendOptions(recipient="5591999999999", text="Seu gás chegou!"))
```

## Fase 3 — Separação de tráfego

O serviço `whatsapp-web.js` fica reservado ao tráfego conversacional.
Para desativar campanhas pelo canal não-oficial: `WA_BROADCAST_ENABLED=false`
(padrão `true` durante a transição; o compose repassa a variável).

## Testes

- Node: `whatsapp/tests/anti-ban.test.ts` — 18 testes (caps, cooldown, warmup,
  quiet hours, distribuição gaussiana). Suite completa: 71 passando.
- Python: `backend/tests/test_whatsapp_cloud_api.py` — 23 testes (config,
  normalização E.164, erros 401/429/4xx, mídia por link, template, assinatura
  HMAC do webhook, parsing de eventos, factory). Suite WhatsApp: 133 passando.

## Critérios realistas

A combinação higiene + canal oficial reduz drasticamente o risco de ban para
campanhas, mas **nenhuma configuração do canal não-oficial garante <1%** — o
número depende de qualidade de lista, opt-in e comportamento dos destinatários
(blocks/reports). A meta de "zero ban" só é garantida pelo canal oficial.
