# OPS-01B — Perfil Home Server (i3-10110U / 12 GB / HDD 1 TB)

Configuração de implantação do GasFlow para o **servidor doméstico**, isolada do
GasFlow Desktop que já roda na mesma máquina em `127.0.0.1:8000` (SQLite).
Nada aqui sobe, migra, faz backup ou faz deploy: são **arquivos de
configuração + procedimento de validação em laboratório**.

## 1. Arquivos

| Arquivo | Papel |
|---|---|
| `docker-compose.homeserver.yml` | Overlay do `docker-compose.prod.yml` com limites de RAM/CPU, rotação de logs, healthchecks e hardening do perfil Home Server |
| `docker-compose.homeserver.lab.yml` | Terceiro arquivo do laboratório: use `-p gasflow-hs-lab`, containers `-lab`, `restart: "no"`; `ports: !override` fixa `127.0.0.1:8088`, e o backend fixa o DSN em `gasflow_lab`, independentemente de variáveis herdadas |
| `deploy/home-server/.env.lab.example` | Template de variáveis **fictícias** do laboratório (copiar para `.env.lab`, fora do git) |
| `deploy/home-server/verify-static.sh` | Verificação estática (compose config, portas, orçamento de RAM, rotação de logs) — não sobe nada |
| `backend/tests/test_ops01b_homeserver_profile.py` | Testes das invariantes deste perfil (sem Docker daemon) |
| `backend/tests/test_ops01c_lab_pre_homologation.py` | Gate estático da fase 0 do LAB-01 (ignora overrides de porta/DSN/projeto, falha segura, PG/Redis isolados, alembic no container) |

O `docker-compose.prod.yml` **não foi alterado**: o perfil é aditivo, para que o
compose de produção continue válido para hosts maiores e para o CI.
O `.env.production.example` ganhou apenas um bloco de documentação do perfil.

## 2. Montagem (sempre na ordem prod → homeserver → lab)

```bash
# Perfil real (servidor doméstico)
docker compose -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  --env-file .env.production config -q

# Laboratório isolado
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml \
  --env-file deploy/home-server/.env.lab config -q
```

## 3. Serviços obrigatórios e opcionais

**Obrigatórios** (sobem no `up -d` padrão, sem profile):

| Serviço | Papel | Essentials |
|---|---|---|
| `postgres` | banco de produção (schema via Alembic) | ✔ |
| `redis` | rate limit + pub/sub realtime entre workers + fila de aprovações | ✔ |
| `backend` | FastAPI (`alembic upgrade head` no boot) | ✔ |
| `frontend` | nginx: SPA + proxy `/api`, `/auth`, `/driver`, `/ws` (única porta publicada) | ✔ |
| `whatsapp` | gateway Baileys (rollback wwebjs) | ✔ |

**Opcionais** (`--profile observability`, nenhuma porta publicada):

| Serviço | Papel |
|---|---|
| `prometheus` | scrape autenticado (`Bearer` via `/run/secrets/metrics_key`) |
| `alertmanager` | alertas → `POST /api/v1/webhooks/alerts` assinado |
| `grafana` | dashboards (provisioning as code) |

**Fora do perfil:** IA local (Ollama) e OSRM **não** são serviços deste compose
e não são dependência de nada. O overlay não os adiciona; o laboratório usa
`AI_PROVIDER=mock`.

## 4. Limites de recursos (overlay Home Server)

`deploy.resources.limits` do arquivo resolvido:

| Serviço | RAM | CPUs |
|---|---|---|
| postgres | 640 MB | 1.0 |
| redis | 128 MB | 0.5 |
| backend | 768 MB | 1.5 |
| frontend | 128 MB | 0.5 |
| whatsapp | 1024 MB | 1.0 |
| **core** | **2688 MB** | — |
| prometheus | 384 MB | 0.5 |
| alertmanager | 96 MB | 0.25 |
| grafana | 192 MB | 0.5 |
| **com observabilidade** | **3360 MB** | — |

- O prod genérico declara 4864 MB; o perfil doméstico usa **~31% menos**.
- Conta do host: ~4 GB de Windows 11 + 2,6 GB do core ≈ 6,6 GB de 11,7 GB →
  **~4,4 GB de folga** (ou ~3,4 GB com observabilidade).
- CPUs são **tetos**, não reservas: a soma passa de 4 threads de propósito
  (`i3-10110U` = 2C/4T) para permitir burst de um serviço sem afogar os outros.
- `BACKEND_WORKERS=1` é o ajuste recomendado no servidor doméstico (2 workers
  cabem na RAM, mas disputam CPU com o GasFlow Desktop). O perfil lê
  `BACKEND_WORKERS` do `.env.production` — ver bloco "Home Server" no
  `.env.production.example`; o laboratório já fixa `BACKEND_WORKERS=1`.
- `shm_size: 128mb` no Postgres evita que sort/hash join caiam em arquivo
  temporário no HDD.

## 5. Rede

| Ambiente | Portas publicadas | Bind |
|---|---|---|
| Perfil real (prod + homeserver) | `FRONTEND_PORT` (default 80) | todas as interfaces (LAN/túnel) |
| Laboratório (`-p gasflow-hs-lab`, prod + homeserver + lab) | `8088` | **somente `127.0.0.1` (fixo no overlay)** |

- Postgres, Redis, backend, WhatsApp, Prometheus, Alertmanager e Grafana
  **não publicam porta nenhuma** — falam entre si pela rede `internal`.
- `/metrics` continua **404 na borda** (nginx) e **401 sem Bearer** na origem
  (`METRICS_PUBLIC=false`); o Prometheus autentica por
  `/run/secrets/metrics_key`. Nada de métrica pública.
- O laboratório não disputa a `:80`, nem a `127.0.0.1:8000` do GasFlow Desktop.
- `whatsapp` não tem dependência do backend: sobe sozinho, responde
  `/api/health` e o bridge reenvia mensagens. Amarrá-lo ao healthcheck do
  backend só atrasaria o pareamento em até 2 min (start_period da migration).
  `frontend` → `backend (service_healthy)` e `backend` →
  `postgres/redis (service_healthy)` seguem do prod.

## 6. Volumes e persistência

Nomes **idênticos aos do prod** (`<projeto>_<volume>`), sem renomear nada:

| Volume | Montagem | Dado | Sobrevive `down -v`? |
|---|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | banco | ✖ (exige `pg_dump` fora) |
| `whatsapp_data` | `/app/data` | SQLite do gateway | ✖ |
| `baileys_auth` | `/app/baileys_auth` | **sessão Baileys** (não versionar) | ✖ (re-QR) |
| `whatsapp_auth` | `/app/wwebjs_auth` | sessão wwebjs (rollback) | ✖ |
| `whatsapp_uploads` | `/app/uploads` | mídia enviada/recebida | ✖ |
| `whatsapp_export` | `/app/export` | relatórios de dedupe | ✖ |
| `backups_data` | `/app/backups` | backups dentro do container | ✖ (mesmo disco ≠ backup) |
| `prometheus_data` / `grafana_data` | dados da obs | descartáveis (config as code) | ✖ |
| — (Redis) | sem volume | contadores efêmeros (por desenho) | n/a |

- **Segredos**: `metrics_key` e `alerts_secret` são `secrets` do Compose
  criados a partir do ambiente (`MARCOS_GAS_API_KEY`, `ALERTS_WEBHOOK_SECRET`)
  e aparecem em `/run/secrets/*` dentro do container (0444, leitura de
  prometheus/alertmanager). Nenhuma credencial vai para a imagem.
- **Sessão WhatsApp / dados**: ficam só nos volumes; `whatsapp/.dockerignore`
  já exclui `data/`, `baileys_auth/`, `wwebjs_auth/`, `uploads/` e `export/`.
- **Logs**: stdout dos containers com `json-file` rotacionado
  (`max-size: 10m`, `max-file: 3` → teto de 30 MB por serviço, 240 MB no pior
  caso com os 8 serviços).
- **Backups futuros**: `backups_data` é o diretório de saída dos scripts
  (`/app/backups`), mas **não é backup** enquanto estiver no mesmo HDD. A
  cópia off-host (HD externo/nuvem) segue como pendência do integrador
  (OPS-01D).
- **Nomes**: o projeto Compose do prod deriva do diretório do checkout
  (ex.: `GasFlow` → `gasflow`). Se o servidor usar outro diretório, rode com
  `-p gasflow` para **não** órfãos os volumes existentes.

## 7. Isolamento do laboratório

| Item | Ambiente real | Laboratório |
|---|---|---|
| Projeto Compose | `<dir>` (ex.: `gasflow`) | `gasflow-hs-lab` (fixado também por `-p`) |
| Containers | `gasflow-*` | `gasflow-hs-lab-*` |
| Volumes | `<projeto>_postgres_data` … | `gasflow-hs-lab_postgres_data` … |
| Rede | `<projeto>_internal` | `gasflow-hs-lab_internal` |
| Secrets | `<projeto>_metrics_key` / `_alerts_secret` | `gasflow-hs-lab_metrics_key` / `_alerts_secret` |
| Porta | `0.0.0.0:80` | `127.0.0.1:8088` |
| Banco | `gasflow` (Postgres) | `gasflow_lab` (Postgres) |
| Reinício | `unless-stopped` | `"no"` (não volta sozinho) |
| WhatsApp | número real | número de teste; **broadcast desligado** |
| Segredos | `.env.production` (real) | `.env.lab` (placeholders `CHANGE_ME_lab_*`) |

O laboratório **não** toca em: GasFlow Desktop, `127.0.0.1:8000`, SQLite do
desktop (`%APPDATA%\gasflow-desktop`), sessões WhatsApp reais, portas `:80` /
`:5432` / `:6379` do host.

## 8. Procedimento de validação em laboratório

> **Nada disto foi executado nesta entrega** (proibido subir serviços na
> OPS-01B). Execute numa janela controlada, com o GasFlow Desktop intacto.

Pré-requisitos:

- Docker Desktop + WSL2 inicializados; `docker compose version` ≥ 2.24.4
  (a tag `!override` fixa a porta do lab em `127.0.0.1:8088`; abaixo disso
  o compose recusa `docker-compose.homeserver.lab.yml`).
- ~20 GB livres (3 imagens buildadas localmente ficam ~2,5 GB) e 8 GB livres
  de RAM no pico do build.
- `cp deploy/home-server/.env.lab.example deploy/home-server/.env.lab`
  (os placeholders `CHANGE_ME_lab_*` são aceitáveis no laboratório; se quiser,
  troque por valores locais — nunca por segredos reais).

Passos:

```bash
# 1. Verificação estática (não sobe nada, não usa daemon)
./deploy/home-server/verify-static.sh

# 2. Conferir o que seria criado
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  config --images

# 3. Subir SÓ o core (obs fica de fora)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  up -d --build

# 4. Saúde (todos healthy; frontend/alertmanager/grafana agora têm healthcheck)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab ps

# 5. Smoke HTTP pela borda do laboratório
./scripts/smoke-test.sh http://127.0.0.1:8088

# 6. RAM real x limites (o pico deve ficar abaixo do limite de cada serviço)
docker stats --no-stream

# 7. Observabilidade opcional (depois do core healthy)
docker compose -p gasflow-hs-lab ... --profile observability up -d

# 8. Desmontar
docker compose -p gasflow-hs-lab ... down          # preserva volumes do lab
docker compose -p gasflow-hs-lab ... down -v       # APAGA só volumes gasflow-hs-lab_*
```

> **WhatsApp no laboratório**: o gateway **não** conecta conta sozinho no
> boot (o pareamento é sempre uma ação explícita). Se for testar o fluxo,
> use um **número de teste** — nunca o número de produção — e saiba que
> `WA_BROADCAST_ENABLED=false` está fixo no overlay do laboratório.
> Sessão e dados ficam nos volumes `gasflow-hs-lab_*`, separados dos reais.

Critérios de aceite do laboratório:

1. `compose config -q` verde nos dois modos (com e sem `--profile observability`).
2. Nenhum container `gasflow-*` criado; nenhum volume fora de `gasflow-hs-lab_*`.
3. Nada escutando em `0.0.0.0:80` nem em `127.0.0.1:8000` por causa do lab.
4. `ps` com os 5 serviços do core `healthy`; `smoke-test.sh` verde.
5. `docker stats` mostrando cada serviço abaixo do seu limite.
6. GasFlow Desktop continua respondendo em `127.0.0.1:8000` durante e depois.
7. `down` + `up` preservando volumes do lab (mesma sessão/`whatsapp_data`).

## 9. Segurança aplicada neste perfil

- **Exposição**: só o frontend publica porta (80 no real; `127.0.0.1:8088` no
  lab). Métricas continuam 404 na borda e autenticadas na origem.
- **Privilégios**: `security_opt: no-new-privileges:true` em todos os 8
  serviços; nenhum `privileged`, nenhum socket do Docker montado.
- **Restart**: `unless-stopped` no servidor (volta após reboot/queda); `"no"`
  no laboratório.
- **Logs**: rotação json-file em todos os serviços.
- **Segredos**: via `secrets:`/arquivos (`/run/secrets`), nunca em `argv`,
  nunca na imagem, nunca no git. `.env.lab` fica fora do git.
- **Healthchecks**: os 5 do core (frontend adicionado) e os 3 da obs
  (alertmanager e grafana adicionados), com `start_period` compatível com o
  boot lento do HDD.
- **Shutdown**: `stop_grace_period` explícito (Postgres 60s) para não matar
  checkpoint em disco lento.

## 10. Riscos restantes (para o integrador)

1. **HDD 5400 rpm é o gargalo real** (não a RAM): I/O de Postgres + builds
   locais + logs no mesmo disco. Recomendação OPS-01E: SSD SATA.
2. **Modo LAN do app dos entregadores (M1)** continua dependendo de expor
   `:8000`/rotas na nginx — fora do escopo desta fase (o perfil só publica a
   porta do frontend). Decidir entre publicar 8000 restrito à LAN ou ajustar
   locations.
3. **`alembic upgrade head` no boot sem backup prévio (O4)**: o wrapper
   `pg_dump` → `up -d` → smoke não foi criado aqui (os scripts de
   `scripts/home-server/data/` são de outro responsável). Enquanto não
   existir, faça snapshot manual antes de atualizar.
4. **`BACKEND_WORKERS`**: o template prod mantém `2` (host maior/CI). No
   servidor doméstico use `1` (ver bloco Home Server do
   `.env.production.example`, ou o `.env.lab.example`).
5. **Windows/notebook como servidor**: desligar suspensão/hibernação, modo de
   energia "Alto desempenho", tampa fechada não deve dormir, e o limite de
   memória do WSL2 (`%UserProfile%\.wslconfig`) deve ser fixado — fora do
   repositório.
6. **Redis 128 MB sem `maxmemory`**: sob carga anômala o container pode ser
   OOM-killed; contadores de rate limit se perdem (degradação já prevista,
   fail-open). Não alterado de propósito (mudaria semântica do rate limit).
7. **Primeiro boot é lento** (build de 3 imagens no HDD, ~10–20 min). Para
   piloto, considere usar as imagens do GHCR (ver `DEPLOY.md`).
8. **TLS**: termina na borda/túnel, como antes; nginx segue HTTP interno
   (`frontend/nginx.conf` não foi tocado).
9. **Postgres com 640 MB**: consultas muito pesadas/paralelas podem ser
   OOM-killed (restart automático; banco transacional recupera). É o preço de
   caber em 12 GB divididos com o Windows — monitorar no piloto.
10. **Backup off-host** e **domínio/URL fixa** seguem pendentes de decisão
   humana (OPS-01C/01D).
11. **PDF/impressão, relay e desktop** não foram tocados nesta fase.
