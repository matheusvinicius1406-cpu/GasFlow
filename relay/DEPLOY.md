# GasFlow Relay — deploy (quando o dono decidir)

Código pronto e testado localmente. O deploy exige conta Fly.io e secrets —
**não executado automaticamente** (decisão da sessão: código local, deploy depois).

```bash
cd relay
fly launch --no-deploy            # ou: fly apps create gasflow-relay
fly secrets set RELAY_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(32))")
fly deploy
```

Depois, configure no desktop (`settings.json`) e no mobile:

```
RELAY_URL = https://gasflow-relay.fly.dev
RELAY_TOKEN = <o mesmo valor do secret>
```

## Limites do free tier (monitorar)

| Recurso   | Limite   | Uso estimado (MVP)                        |
| --------- | -------- | ----------------------------------------- |
| VMs       | 3 shared | 1 (relay)                                 |
| Storage   | 3GB      | ~0 (sem persistência no relay)            |
| Transfer  | 160GB/mês| ~1GB/mês (posições são pequenas)          |

Fotos NÃO passam pelo relay (upload direto desktop/depósito) — bandwidth
protegida por design. Se um dia passar de 100GB/mês, migrar para VPS.
