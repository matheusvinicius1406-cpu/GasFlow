# App do Entregador — Fase 1 executada (2026-09-14)

**Decisões da sessão:** estender a API da Fase 14 (não duplicar); relay como **código local** (deploy Fly.io fica para o dono); scaffold RN com lógica testável.

## 1. O que já existia (Fase 14) — NÃO refeito

A API do motorista já estava completa: login/logout, `/me`, entregas (accept/start/arrive/complete/fail), rotas, location com rate limit, proofs, batch sync com conflito de versão, idempotência DB-backed, isolamento por motorista/tenant — **93 testes** (`tests/test_driver_api.py`), namespaces `/api/driver/v1/*` (legado) e `/api/v1/driver/*` (oficial). Tabela `driver_locations` já existia.

## 2. Gaps fechados nesta sessão (vs. prompt do roadmap)

| Requisito do prompt | Status | Implementação |
|---|---|---|
| `/auth/mobile/login` — access 15min + refresh 7d | ✅ | `app/presentation/api/driver_mobile_auth.py` |
| JWT escopo `mobile` | ✅ | Mini-JWT HS256 stdlib (`issue_access_token`/`verify_access_token`) — sem dependência nova (PyJWT não estava no ambiente; ver decisão abaixo) |
| `/auth/mobile/refresh` com rotação | ✅ | Tabela `driver_refresh_tokens` + repo; rotação mantém `family_id` |
| Reuso de refresh revoga ambos | ✅ | Token ROTATED reapresentado → família inteira REVOKED (401) |
| Rate limit 10 login/min/IP | ✅ | `RateLimiter` (mesmo do auth web) por IP |
| Middleware rejeita escopo errado | ✅ | `_authenticate_driver` aceita sessão DB **ou** JWT escopo mobile; desktop (`get_tenant_context`) só aceita sessões web — isolamento nos dois sentidos |
| Location em lote | ✅ | `DriverLocationService.ingest_batch` (cap 500; posição malformada descartada sem derrubar o lote) |
| 403 fora do horário de trabalho (LGPD) | ✅ | `driver.work_hours.start/end` no quadro de configurações (seed 06:00–22:00, admin edita); `WorkHoursViolation` + audit `driver.location.rejected_out_of_hours` |
| Retenção 90 dias | ✅ | `purge_old_locations()` no boot (idempotente, skip em TESTING); sync log também purga |
| Audit de acesso à localização | ✅ | `driver.location.batch` / `driver.location.read` / rejeição (best-effort, sem coordenadas no log) |
| Delta sync `GET /driver/sync?since=` | ✅ | Lê `offline_sync_log` (nova tabela) + devolve entregas do próprio motorista com status/versão |
| Relay nuvem (Fly.io) | ✅ código | `relay/` — FastAPI + WS registry + cache de última posição; 6 testes; Dockerfile/fly.toml/DEPLOY.md prontos, **sem deploy** |
| Desktop WS outbound | ✅ | `desktop/src/main/relay-client.ts` (backoff exponencial 1s→60s, injectável) + settings `relay*` + IPC `gasflow:driver-location`; 4 testes |
| App mobile (Fase 2) | 🟡 scaffold | `mobile/` — lógica pura testada (9 testes: work-hours LGPD, fila offline com backoff, fallback LAN→nuvem→offline) + telas RN escritas; build nativo depois de `npm install` |

## 3. Decisões técnicas

- **Mini-JWT HS256 stdlib em vez de PyJWT**: PyJWT não estava no ambiente e o backend empacota via PyInstaller — 30 linhas de `hmac`/`hashlib` evitam dependência nova. Só o access token é JWT (15 min); a revogação forte fica nos refresh tokens DB-backed. Secret: `MOBILE_JWT_SECRET` (env) com fallback ao `ADMIN_PASSWORD` — trocar a senha invalida access tokens, e o app renova via refresh sem re-login.
- **Rotação não estende a família**: `new_expires_at = min(expira_original, agora+7d)` — sessão máxima de 7 dias desde o login.
- **Work hours fail-open em config inválida** (não bloqueia operação) e **fail-closed sem config** no app (`isWithinWorkHours(null) === false`).
- **Relay não proxya sync** (MVP): localização em tempo real + cache de última posição. Sync continua direto no backend (LAN ou futura VPN). Fotos não passam pelo relay — bandwidth protegida.
- **`_authenticate_driver` ampliado com fallback JWT** — rotas de motorista são mobile por definição; o desktop continua rejeitando (outra tabela de sessões).

## 4. Como testar

```bash
cd backend   && python -m pytest tests/test_driver_mobile.py tests/test_driver_api.py -q   # 104 passed
cd relay     && python -m pytest tests/test_relay.py -q                                   # 6 passed
cd desktop   && npm test                                                                   # 29 passed
cd mobile    && npm test                                                                   # 9 passed
```

## 5. Deploy do relay (quando decidido)

Ver `relay/DEPLOY.md` — `fly launch`, `fly secrets set RELAY_TOKEN=...`, `fly deploy`; mesma token no `settings.json` do desktop (`relayEnabled/relayUrl/relayToken/relayTenant`).

## 6. Próximos passos (Fases 2–4)

1. `npm install` em `mobile/` + build nativo (EAS/Gradle) — telas já escritas
2. Background geolocation nativo (`@transistorsoft`) respeitando `workHours`
3. QR code de conexão LAN no desktop + mapa em tempo real (Fase 3)
4. Consentimento LGPD por escrito no primeiro login do motorista (Fase 4)
