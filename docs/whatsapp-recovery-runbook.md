# WhatsApp — Runbook de Recuperação e Re-pareamento

**Origem:** incidente de 2026-09-06 (conta primary nunca conectava; loop de
`account.disconnected` com `reason 408` até esgotar 10 tentativas, QR
regenerado a cada ciclo — sessão nunca ficou `connected`, `sendText` nunca
disparou). **Correção:** recuperação por caminho no `provider-manager.ts` +
telemetria de transições (`account.state_transition`, contador
`disconnectsByReason`).

---

## 1. Diagnóstico de um novo incidente (5 min)

1. Transições: `grep account.state_transition whatsapp/dev.log | tail -50` —
   cada linha traz `{account, engine, from, to, reason}`.
2. Contagem por motivo: `GET /api/whatsapp/health` (ou
   `/whatsapp/accounts/:id/health`) → campo `disconnectsByReason`.
3. Classifique pela contagem do motivo que **precede** a queda:

| Motivo (statusCode) | Evento | Caminho | Ação automática (já implementada) |
|---|---|---|---|
| 401 "logged out" / device removed | `account.logged_out` | **A** | wipe de `baileys_auth/<id>/` + re-init (QR reabre) |
| 428 "connection closed" / Bad MAC / No session record; 440 conflict | `account.connection_closed` + `account.disconnected` | **B** | limpa `session-*`/`sender-key-*`/`pre-key-*`, preserva `creds.json`; 3 falhas → caminho A |
| 515 "restart required" | `account.disconnected` | **C** | 1 reconexão limpa; se repetir → caminho B |
| 408 (timed out), 411, 418, 429, 5xx | `account.disconnected` | rede | backoff exponencial existente (5s→80s, 10 tentativas) |

**Lição do incidente:** 408 em rajada com QR regenerado a cada ciclo = pareamento
via QR nunca concluído — não era 401 nem 428. Re-pareamento manual resolve.
Antes deste fix o log não distinguia 408 de 428/401; agora distingue.

## 2. Re-pareamento manual (QR) — uma vez por incidente de caminho A

> O WhatsApp invalida o device **server-side**; não existe auto-recuperação
> sem re-pareamento. O fix troca loop infinito por estado limpo + QR.

1. Pare o serviço whatsapp (`logs/whatsapp.pid`, pm2 ou o terminal do `npm run dev`).
2. Apague a sessão corrompida:
   ```bash
   rm -rf whatsapp/baileys_auth/primary   # ou secondary
   ```
   Necessário **apenas** se a sessão já estava corrompida antes do deploy
   deste fix — o código novo apaga sozinho em qualquer `logged_out` futuro.
3. Suba o serviço e abra a UI de conexão (ou `GET /qr`).
4. No celular: WhatsApp → Dispositivos conectados → Conectar dispositivo →
   escaneie o QR em até 60s (TTL; um novo é gerado automaticamente).
5. Confirme: `GET /api/whatsapp/health` → `{"healthy":true,"state":"connected"}`.

**Rollback de engine** (se o Baileys ficar instável): `WA_ENGINE=wwebjs` —
a sessão antiga em `wwebjs_auth/` continua válida, sem rebuild.

## 3. Se o próximo incidente for de outro caminho

- **Caminho B dominante (428):** o auto-recovery limpa a sessão Signal até 3×
  e escala sozinho para o wipe. Manual, se preciso: dentro de
  `baileys_auth/<id>/` apague `session-*`, `sender-key-*`, `pre-key-*`
  **mantendo** `creds.json` e `app-state-*`, e reinicie.
- **Caminho C recorrente (515):** já tratado (restart único → caminho B).
  Persistindo após o wipe, cheque a versão: `npm ls @whiskeysockets/baileys`
  — 515 em loop costuma ser version skew do protocolo.
- **Rate limit do WhatsApp (429/403 stream erased):** NÃO force reconexões;
  aumente `RECONNECT_BASE_DELAY_MS` e revise `anti-ban/` (quiet hours,
  delays gaussianos). Não altere o módulo anti-ban.

## 4. Telemetria disponível (a partir deste fix)

- `account.state_transition` — toda mudança de estado `{account, from, to, reason}`.
- `account.connection_closed` — `statusCode` + texto do Boom a cada close.
- `account.recovery.signal_session_clear` / `.signal_clear_escalated` — caminho B.
- `account.logout_failed` — falha do wipe no caminho A (logada, não engolida).
- `disconnectsByReason` — contador em memória por conta, exposto nos healths.
- Métricas Prometheus: `account_connected`, `reconnect_attempts_total`.
