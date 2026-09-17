# GasFlow Relay — deploy no notebook + Cloudflare Tunnel

O relay roda **no notebook da empresa** (o mesmo que roda o backend GasFlow)
e é exposto à rua via **Cloudflare Tunnel** — gratuito, sem abrir portas no
roteador, sem IP público, com WebSocket nativo (o desktop mantém a conexão
WS aberta através do túnel).

Arquitetura da cadeia do rastreador:

```
Mobile (GPS 120s, só em rota) ──HTTPS──▶ trycloudflare.com ──▶ cloudflared
   ──▶ relay (uvicorn 127.0.0.1:8080) ──WS──▶ desktop ──POST──▶ backend
   ──▶ driver_locations ──▶ mapa do operador (polling 30s)
```

## 1. Subir o relay (notebook)

```bat
cd relay
start-relay.bat
```

- Na **primeira execução** gera o `RELAY_TOKEN` (secreto) e salva em
  `relay\.env` (fora do git — **nunca commitar**).
- O **mesmo token** vai no desktop (`settings.relayToken`) e no mobile
  (`mobile/src/logic/config.ts` → `relayToken`).
- O relay fica em `http://127.0.0.1:8080` (só local — o acesso externo é
  exclusivamente via túnel).

Validação local (opcional):

```bash
curl http://127.0.0.1:8080/health
# → {"status":"ok"}
```

## 2. Expor à rua (Cloudflare Tunnel)

### 2a. Quick tunnel — teste/validação (sem conta, sem domínio)

```bat
cd relay
start-tunnel.bat
```

Copia a URL `https://<algo>.trycloudflare.com` que o cloudflared imprime.
**A URL muda a cada execução do script** — serve para validar a cadeia hoje
e para o smoke em campo. Para produção (entregador com URL fixa), faça o
2b assim que houver domínio.

### 2b. Produção — tunnel nomeado (exige conta Cloudflare + domínio)

Gratuito no plano free da Cloudflare. O domínio precisa estar adicionado à
conta (nameservers da Cloudflare). Registrar direto na Cloudflare Registrar
custa ~US$10/ano (sem markup).

```bash
cloudflared tunnel login                        # abre o navegador
cloudflared tunnel create gasflow-relay         # cria o túnel (gera credencial)
cloudflared tunnel route dns gasflow-relay relay.seudominio.com
```

`~/.cloudflared/config.yml` (Windows: `%USERPROFILE%\.cloudflared\config.yml`):

```yaml
tunnel: <UUID-do-tunel>
credentials-file: C:\Users\<voce>\.cloudflared\<UUID>.json
ingress:
  - hostname: relay.seudominio.com
    service: http://127.0.0.1:8080
  - service: http_status:404
```

Rodar como **serviço do Windows** (auto-start, sobe com o notebook — o
notebook deve ficar ligado no horário de trabalho):

```bat
cloudflared service install
net start cloudflared
```

URL fixa resultante: `https://relay.seudominio.com` (muda só se o domínio
mudar).

## 3. Configurar os clientes

| Cliente | Onde | Valor |
|---|---|---|
| Desktop | `settings.json` (app GasFlow) | `relayEnabled: true`, `relayUrl: https://<url-do-tunel>`, `relayToken: <RELAY_TOKEN>`, `relayTenant: default` |
| Mobile | `mobile/src/logic/config.ts` | `cloudBaseUrl: "https://<url-do-tunel>"`, `relayToken: "<RELAY_TOKEN>"` |

## 4. Validar (critério de aceite)

```bash
# saúde pelo túnel (de qualquer rede, inclusive 4G do celular)
curl https://<url-do-tunel>/health                # → {"status":"ok"}

# ingest com auth (positivo e negativo)
curl -X POST https://<url-do-tunel>/driver/location \
  -H "X-Relay-Token: <RELAY_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"driver_id":"654321","tenant_id":"default","positions":[{"lat":-1.4558,"lng":-48.4902}]}'
# → {"accepted":1,"delivered_to_desktop":true|false}   (false se desktop offline — posição fica em cache)

# sem token → 401
curl -X POST https://<url-do-tunel>/driver/location -H "Content-Type: application/json" -d '{}'
# → {"detail":"Unauthorized"}
```

- Desktop conecta no WS (`wss://<url-do-tunel>/relay/ws?tenant=default&token=<RELAY_TOKEN>`) sem erro de auth.
- Mobile posta posição via 4G (F2.5 — `sendPosition` rota para `cloud`).

## 5. Diagnóstico

| Sintoma | Onde olhar |
|---|---|
| `/health` não responde pelo túnel | relay está de pé? (`start-relay.bat` na porta 8080) |
| Tunnel cai / URL nova a cada start | quick tunnel é efêmero por design — migrar para 2b |
| `delivered_to_desktop: false` | desktop está com `relayEnabled: true` e a mesma URL? (log do Electron: `[relay] status:`) |
| 401 no POST | `X-Relay-Token` difere do `RELAY_TOKEN` do `.env` do relay |
| Desktop não recebe posição | token/tenant do WS divergem; ver logs do `cloudflared` e do relay-client no desktop |

## Limites e notas

- **Uptime do relay = uptime do notebook.** Notebook desligado ⇒ rua sem
  ingest; posições do mobile entram na fila offline (F2.5) e sobem quando o
  canal voltar.
- Fotos **não** passam pelo relay (upload direto desktop/depósito) —
  bandwidth protegida por design.
- O túnel é outbound-only: nenhuma porta de entrada aberta no notebook.
- O relay continua exigindo `X-Relay-Token` (o túnel não é camada de auth).
