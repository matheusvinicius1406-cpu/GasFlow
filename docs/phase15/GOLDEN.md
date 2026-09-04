# GOLDEN — Release Candidate v1.0.0-rc.1

Data: 2026-09-04 · Branch `main` · Commit/tag: `v1.0.0-rc.1`

## Checklist pré-release

| Item | Resultado |
|---|---|
| Backend pytest | ✅ 1178 passed / 27 skipped |
| Frontend vitest | ✅ 116 passed · `tsc --noEmit` 0 erros |
| WhatsApp | ✅ typecheck + testes |
| E2E Playwright | ✅ 8/8 (3 runs consecutivas na fase E2E) |
| Ruff | ✅ limpo |
| Compose prod | ✅ `docker compose config` válido |
| Smoke test | ✅ 5/5 (true prod stack) |
| WebSocket real | ✅ welcome + ping→pong via nginx, token real |
| PIX real | ✅ chave configurada → payload BR Code + QR validado com CRC |
| Rate limiter Redis | ✅ 5×200 → 6º em diante 429, com ZSET gravado no Redis |

## Versionamento

- `frontend`, `whatsapp` e `e2e` (package.json + package-lock) → `1.0.0-rc.1`.
- Backend não tem arquivo de versão (decisão de arquitetura): a versão do
  backend é a tag Git / tag da imagem.
- Pipeline `build-push.yml` já publica no GHCR em tags `v*` (latest + semver).

## Bug encontrado e corrigido na validação

### Rate limiter Redis apontava para `localhost` (degradava silenciosamente)

**Sintoma**: durante a validação ao vivo do rate limiter no stack prod
(`RATE_LIMIT_MODE=redis`), todas as requisições passaram a retornar 429 depois
de alguns requests — mas `DBSIZE` no Redis ficava em 0.

**Causa raiz**: `app/core/rate_limit.py` construía o limiter assim:

```python
_limiter = RedisSlidingWindowRateLimiter() if settings.rate_limit_mode == "redis" ...
```

O construtor sem `url` usa o default `redis://localhost:6379/0`. Dentro do
container de produção o Redis é um serviço separado (`redis:6379`) — o ping a
`localhost` falhava, o circuit breaker entrava em modo indisponível por 30s e o
middleware caía **permanentemente** no fallback in-memory por processo. Em
multi-worker isso anularia o rate limit compartilhado (cada worker com contador
próprio) sem nenhum erro visível além do log de warning.

**Por que o SC-01 não pegou**: a validação ao vivo do SC-01 rodou o backend no
host, onde `localhost:6379` **era** o Redis (porta publicada no Docker) — o
default funcionava por acaso.

**Fix** (`app/core/rate_limit.py`):

```python
_limiter = (
    RedisSlidingWindowRateLimiter(url=settings.rate_limit_redis_url)
    if settings.rate_limit_mode == "redis"
    else SlidingWindowRateLimiter()
)
```

**Validação pós-fix** (stack prod, Redis limpo):

```
login1..5:  401 (permitido, senha errada)
login6..12: 429 (rate limited)
DBSIZE=1 · ZCARD do key auth = 5  ← janela deslizante real no Redis
```

**Regressão**: `tests/test_rate_limit_redis.py::TestRedisLimiterWiring` —
recarrega o módulo com `settings.rate_limit_mode=redis` e uma URL arbitrária e
asserta que o `_limiter` global foi construído com ela (e que em
`rate_limit_mode=memory` o backend é o in-memory).

## Validação ao vivo (stack prod `docker-compose.prod.yml` + override de volume)

Tudo executado contra a stack real (nginx :80, backend interno, Redis, Postgres
com volume dedicado `gasflow_golden_postgres_data`, `ENVIRONMENT=production`):

1. **Smoke 5/5** — health, ready, docs, auth e proxy whatsapp respondendo.
2. **WebSocket** — `ws://localhost/ws?token=<jwt real>` → `welcome` com canal
   `tenant:default`; `ping` → `pong`.
3. **PIX** — `PATCH /payments/pix` (chave + holder + cidade) → `POST
   /payments/pix/payload` → payload `000201…` com CRC16 válido e QR PNG base64.
4. **Rate limiter Redis** — acima; comprova a correção deste release.

## Artefatos

- `CHANGELOG.md` — histórico completo desde DB-01.
- `README.md` — badges de CI/cobertura/E2E/versão.
- `DEPLOY.md` — seção "Deploy em Produção (Checklist)".
- Tag Git `v1.0.0-rc.1`.

## Pendências para v1.0.0 (estável)

- [ ] WA-02: live WhatsApp com instância real pareada (BLOCKED por ambiente).
- [ ] Redis pub/sub para realtime multi-worker (P2).
- [ ] Integração PSP/webhook para status PIX automático (P2).
- [ ] Publicação das imagens no GHCR (executar o job de tag quando o repositório
      estiver num remote com Actions habilitadas).
