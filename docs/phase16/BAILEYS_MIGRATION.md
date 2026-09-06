# Fase 16.2 — Migração wwebjs → Baileys (WebSocket puro)

> Estratégia: **migração dual-mode**. Ambos os motores permanecem no código;
> `WA_ENGINE` escolhe por conta. Rollback = trocar uma env var, sem rebuild
> e sem perder a sessão antiga.

## Por quê

| | whatsapp-web.js (wwebjs) | Baileys |
|---|---|---|
| Runtime | Puppeteer + Chromium (~500MB+ RAM) | WebSocket nativo (~80MB) |
| Reconexão | Recarrega o navegador | Instantânea (socket) |
| Imagem Docker | ~1.5GB+ (Chromium + deps) | Node slim |
| Sessão | `wwebjs_auth/` (LocalAuth) | `baileys_auth/{account}/creds.json` |

**Invariante preservado:** `provider-manager.ts` mantém a MESMA superfície
(`sendMessage`, `sendMedia`, `getContacts`, `getQr`, `healthCheck`, `onMessage`).
Backend, broadcast, incoming bridge, anti-ban e rotas HTTP não mudaram nada.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `src/provider/baileys-engine.ts` | **Novo** — motor Baileys: conexão, QR, pairing code, envio texto/mídia, contatos, saúde, download de mídia |
| `src/provider/provider-manager.ts` | Seleção de motor (`WA_ENGINE` / `WA_ENGINE_PRIMARY` / `WA_ENGINE_SECONDARY`); toda operação despacha para o motor ativo |
| `whatsapp/Dockerfile` | Chromium removido do build padrão; build arg `BUILD_WWEBJS=1` recria imagem com Chromium para rollback |
| `docker-compose.yml` | `WA_ENGINE=baileys` default, volume `baileys_auth` novo |
| `package.json` | `@whiskeysockets/baileys@^6.7.24` + `pino` adicionados (wwebjs mantido para rollback) |

Pino dedicado (`BAILEYS_LOG_LEVEL`, default `error`) silencia o log interno da lib.

## Cutover (primeira execução com Baileys)

1. `docker compose up -d --build whatsapp`
2. A sessão do wwebjs **não é compatível** — novo pareamento necessário:
   - **QR**: `GET /api/whatsapp/accounts/primary/qr` (ou `/connect`)
   - **Pairing code** (alternativa): defina `WA_PAIRING_CODE_PHONE=559181689969`
     e o código aparece no log do container na primeira conexão.
3. A sessão persiste em `baileys_auth/primary/` — restarts não pedem QR novamente.

## Rollback (se algo falhar)

```env
# .env
WA_ENGINE=wwebjs
# opcional: imagem com Chromium (o código wwebjs continua no container)
WHATSAPP_BUILD_WWEBJS=1
```

```bash
docker compose up -d --build whatsapp
```

A sessão antiga em `wwebjs_auth/` nunca foi apagada — o pareamento anterior
volta a valer imediatamente. Por conta: `WA_ENGINE_PRIMARY=wwebjs` mantém o
número principal no motor antigo enquanto o secundário testa o Baileys.

## Testes

- `tests/baileys-engine.test.ts` — 13 testes: JID normalization, fail-closed
  sem conexão, health/getters, mapeamento `toIncomingShape` compatível com o
  contrato que o `incoming.ts` consome (grupos → `author`, captions, timestamp).
- Suite completa: 84 testes passando (71 anteriores + 13 novos).

## Limitações conhecidas

- `getContacts()` no Baileys retorna apenas JIDs 1:1 visíveis no socket
  (sem nome/pushname/business). O catálogo rico do wwebjs se perde; para o
  fluxo de campanhas o campo essencial é o JID/telefone.
- `markAsRead` 1:1 continua não crítico (como no wwebjs).
- Baileys é biblioteca não-oficial: updates do WhatsApp podem exigir bump de
  versão. Pin em `^6.7.24` (linha estável; 7.0.0-rc é evitada de propósito).
