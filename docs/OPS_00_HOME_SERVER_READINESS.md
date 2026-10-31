# OPS-00 — Home Server Readiness (auditoria somente leitura)

> **Fase:** OPS-00 · **Data:** 2026-10-23 · **Escopo:** auditoria de hardware, rede,
> Docker e infraestrutura da máquina disponível + diagnóstico + plano. **Sem**
> alteração de código, sem instalação, sem `compose up`, sem commit/push.
> Este arquivo é novo e **não foi commitado** (working tree permanece com o
> checkpoint SEC-02 `544dca6` no topo).

---

## 00. Metodologia e escopo

- Comandos exclusivamente de leitura (`Get-*`, `Select-String`, `netstat -ano`,
  `wsl -l -v`, `Invoke-WebRequest` GET em `/health`, `docker compose config` com
  env dummy em fases anteriores).
- Não foi iniciado/instalado/reiniciado nada: Docker Desktop segue **parado**,
  WSL distros **Stopped**, nenhum serviço modificado.
- Segredos nunca exibidos (`relay/.env` apenas listado, não lido no console;
  `.env`/`whatsapp/.env` não impressos).
- IPs privados mascarados; nenhum IP público, MAC ou senha neste documento.
- Máquina auditada = **máquina de desenvolvimento** (é onde o VS Code/opencode
  roda). Se é o futuro Home Server: **PENDENTE** (seção 03).
- Formato dos achados: `Afirmação → Evidência → Estado → Impacto → Ação → Prioridade`.

---

## 01. Estado do repositório (checkpoint preservado)

| Item | Estado | Evidência |
|---|---|---|
| Branch | `sec-02-whatsapp-gateway` | `git status`/`git log` |
| HEAD | `544dca6` — *fix(security): harden WhatsApp gateway authentication and exposure* | `git log --oneline` |
| Árvore | **limpa** (só `.ruff_cache` descartável em fases anteriores) | `git status --porcelain` vazio |
| Diferença p/ `origin/main` | 3 commits à frente (SEC-01/01B `d135caf`, SEC-01C `656d2de`, SEC-02 `544dca6`) | `git log` |
| Whitespace | `git diff --check` → OK | execução nesta fase |
| Commits na OPS-00 | **nenhum** | — |

**Estado:** CONFIRMADO. Checkpoints SEC-01/01B/01C/02 preservados.

---

## 02. Hardware auditado

| Componente | Detalhe | Estado |
|---|---|---|
| Chassis | Notebook Samsung (tipo 10 = laptop) | CONFIRMADO |
| CPU | Intel Core i3-10110U (Comet Lake, 2C/4T, ~15W, 2019/2020) | CONFIRMADO |
| RAM | **12 GB** (módulos 8 GB + 4 GB, 2/2 slots ocupados, máx. 32 GB → upgrade 2×16 GB) | CONFIRMADO |
| Disco | **TOSHIBA MQ04ABF100 — HDD SATA 932 GB (NÃO SSD)**, partição C: única NTFS, **702 GB livres**, `HealthStatus=Healthy` | CONFIRMADO |
| SMART detalhado | `Get-StorageReliabilityCounter` vazio (exige elevação/ferramenta) | **PENDENTE** |
| Bateria | 100% / carregando | CONFIRMADO |
| Boot atual | 14/10/2026 (uptime ~9 dias em 23/10) | CONFIRMADO |
| Fuso | `SA Eastern Standard Time` (America/Belem adequado ao negócio) | CONFIRMADO |
| Memória em uso | ~4,4 GB livres de 11,8 GB com IDE/navegador abertos | CONFIRMADO |

**Achado H1 (hardware) — P1**
- **Afirmação:** o disco é um HDD de notebook de 5400 rpm, não SSD.
- **Evidência:** `Get-PhysicalDisk` → TOSHIBA MQ04ABF100, BUS_TYPE SATA, MEDIA_TYPE HDD.
- **Estado:** CONFIRMADO.
- **Impacto:** I/O é o gargalo clássico de Postgres + 8 containers no mesmo
  disco; risco de latência sob carga, boot lento e falha prematura de disco de
  notebook (mecânico, vibração/portátil).
- **Ação:** OPS-01E — troca HDD→SSD (SATA 2,5" ~R$250–350 por 480 GB–1 TB) ou
  máquinas com SSD; enquanto não ocorrer, piloto com perfil reduzido.
- **Prioridade:** P1.

**Achado H2 (hardware) — P2**
- **Afirmação:** RAM atual (12 GB, mistura 8+4) é suficiente só para piloto.
- **Evidência:** seção 02; limites da stack prod somam ≈4,75 GB (seção 08).
- **Estado:** CONFIRMADO.
- **Impacto:** no Windows 11 desktop (≈3–4 GB de base) + stack de 4,75 GB o
  folga aperta; HDD agrava swap.
- **Ação:** upgrade para 2×16 GB (slots livres para isso: 2 ocupados, máx 32)
  ou Ubuntu Server (≈300–500 MB de base) — decisão em OPS-01E.
- **Prioridade:** P2.

---

## 03. Esta máquina é o futuro Home Server?

- **Evidência a favor:** `relay/DEPLOY.md` documenta que o relay roda "no
  notebook da empresa (**o mesmo que roda o backend GasFlow**)"; o app GasFlow
  Desktop está instalado nesta máquina e **o backend de produção está rodando
  agora por ele** (seção 11). Esta é, portanto, a máquina que hoje **já é** o
  servidor de facto.
- **Evidência contra dedicar:** é um notebook (bateria/tampa/thermal), HDD,
  compartilhado com dev (VS Code, navegador, builds).
- **Estado:** **PENDENTE** — confirmação humana de que este equipamento (ou
  outro) será o servidor definitivo; se houver outro hardware, repetir seções
  02–07 nele.
- **Impacto:** dimensionamento e plano de rede desta fase valem para esta
  máquina; troca de hardware invalida seções 02/04/05.

---

## 04. Disco e armazenamento

- 932 GB brutos, 702 GB livres (~75%) — espaço **suficiente** por anos
  (base atual: 3,43 MB SQLite + imagens WA).
- Estado: Healthy (relatório resumido); SMART real (reallocated sectors, power-on
  hours, temp) **PENDENTE** (ferramenta com elevação — `smartctl`/CrystalDiskInfo).
- Única partição NTFS do sistema — sem separação dados/sistema.
- **Ação (OPS-01D):** instalar leitor SMART e registrar baseline antes de
  confiar dados de produção no HDD.

---

## 05. CPU e memória — capacidade

- i3-10110U (2C/4T) — suficiente para a carga-alvo do perfil reduzido
  (poucos usuários internos, ~dezenas de entregas/dia), **insuficiente** para
  Ollama local + serviços pesados simultâneos.
- RAM disponível hoje: 12 GB; upgrade máximo 32 GB (2 slots).
- **Matriz de sizing (seção 13)** define perfis.

---

## 06. Sistema operacional, virtualização e Docker

| Item | Estado | Evidência |
|---|---|---|
| SO | Windows 11 Home Single Language 10.0.26200 | `Get-ComputerInfo`/os |
| Docker Desktop | **instalado** (`C:\Program Files\Docker`), serviço `com.docker.service` **Stopped**, pipe do daemon ausente | `Get-Service`, erro de `docker version` |
| Compose CLI | v5.3.1 disponível (`docker compose config` funcional) | verificação anterior |
| WSL2 | habilitado; distros `Ubuntu-24.04` e `docker-desktop` **Stopped**; `wslservice` rodando | `wsl -l -v` |
| VirtualBox | instalado (adaptador host-only = "Ethernet 2") | adaptador presente |
| Virtualização firmware | `VirtualizationFirmwareEnabled=False` (inconsistente com WSL2 que exige VT-x) | `Win32_Processor` |
| Features Hyper-V/HVCI | checagem exigiu elevação → **não executada** | **PENDENTE** |
| Ollama | porta 11434 **não** escutando agora; não detectado | `netstat` |

**Achado D1 (Docker) — P1**
- **Afirmação:** o runtime alvo (Docker Desktop + WSL2) está instalado mas
  **nunca foi exercitado nesta auditoria**; o estado real ("abre, subindo a
  stack sem erro?") é desconhecido.
- **Evidência:** serviço parado, distros paradas, `docker version` falha por
  daemon off; apenas `config` estático foi validado (permitted read-only path).
- **Estado:** INSTALADO, funcionamento **PENDENTE**.
- **Impacto:** risco de surpresa em OPS-01A (versão, licença Docker Desktop
  Business, recursos WSL limitados pelo SO Home).
- **Ação:** OPS-01A — iniciar Docker Desktop (mudança de estado, fora da
  OPS-00) e subir stack com env dummy/smoke.
- **Prioridade:** P1.

**Achado D2 — P3**
- **Afirmação:** `VirtualizationFirmwareEnabled=False` com WSL2 ativo é
  inconsistente (indica VBS/HVCI ativo escondendo o flag, ou BIOS com VT-x
  desabilitado e distros antigas).
- **Evidência:** `Win32_Processor` vs `wsl -l -v` com 2 distros WSL2.
- **Estado:** INCONSISTENTE — confirmar no BIOS/`systeminfo` com elevação.
- **Impacto:** se VT-x estiver real desligado, Docker Desktop WSL2 pode falhar
  ao iniciar → bloqueia toda a stack.
- **Ação:** checagem com elevação na OPS-01A antes de qualquer plano de corte.
- **Prioridade:** P3 (mas barato de resolver — bloqueador se confirmado).

---

## 07. Rede

| Item | Estado |
|---|---|
| Wi-Fi (ativo) | link 72,2 Mbps, LAN privada `192.168.0.0/24`, gateway `192.168.0.x`, DNS do provedor (IPs mascarados), perfil do Wi-Fi = **Public** |
| Ethernet física | **desconectada** (sem cabo) |
| "Ethernet 2" 1 Gbps | = adaptador host-only do VirtualBox (`192.168.56.x`) — **virtual, não é NIC física** |
| Porta 8000 | `127.0.0.1` apenas (backend desktop) — não exposta |
| Firewall | perfis Domain/Private/Public **Enabled=True**, inbound `NotConfigured` (default do SO) |
| IP público / CGNAT | **PENDENTE** (não verificado nesta fase) |
| Latência/pacote/velocidade real do uplink | **PENDENTE** (medição em OPS-01C) |

**Achado N1 — P1**
- **Afirmação:** a conexão de produção é **Wi-Fi 72 Mbps** (rádio, 2,4/5 GHz
  dependente de vizinhança), e a NIC com fio está sem cabo.
- **Evidência:** `Get-NetAdapter`/`Get-NetIPConfiguration`.
- **Estado:** CONFIRMADO.
- **Impacto:** instabilidade de rádio = flap de túnel/sessão WA/latência de
  sync dos entregadores; servidor "portátil ligado no Wi-Fi" é o elo mais fraco.
- **Ação:** OPS-01C — cabeamento Ethernet (switch/roteador → máquina) como
  pré-requisito de piloto; Wi-Fi apenas fallback.
- **Prioridade:** P1.

**Achado N2 — P2**
- **Afirmação:** perfil de rede do Wi-Fi é **Public** e o firewall tem
  inbound default não configurado explicitamente.
- **Evidência:** `Get-NetConnectionProfile` (Public), `Get-NetFirewallProfile`.
- **Estado:** CONFIRMADO.
- **Impacto:** Public é o perfil correto para Wi-Fi público/desconhecido, mas
  exige regras explícitas quando expuser portas LAN (mobile).
- **Ação:** OPS-01D — regras de firewall dedicadas por porta, default block.
- **Prioridade:** P2.

---

## 08. Inventário Docker

### 08.1 `docker-compose.prod.yml` — alvo do Home Server

| Serviço | Imagem | Porta publicada | Memória (limit) | Restart | Healthcheck |
|---|---|---|---|---|---|
| postgres | `postgres:16-alpine` | **nenhuma** (interna) | 512M (L36) | unless-stopped | sim (L27) |
| redis | `redis:7-alpine` | **nenhuma** | 128M (L54) | unless-stopped | sim (L46) |
| backend | build local | **nenhuma** | 1G (L115) | unless-stopped | sim (L103) |
| frontend | build local | **`${FRONTEND_PORT:-80}:80`** (L128) | 256M (L135) | unless-stopped | — |
| whatsapp | build local | **nenhuma** (interna) | 2G (L187) | unless-stopped | sim (L178) |
| prometheus | `prom/prometheus:v2.54.1` | **nenhuma** | 512M (L212) | unless-stopped | sim (L204) |
| alertmanager | `prom/alertmanager:v0.27.0` | **nenhuma** | 128M (L225) | unless-stopped | — |
| grafana | `grafana/grafana:11.2.0` | **nenhuma** | 256M (L245) | unless-stopped | — |

- Rede `internal` bridge; volumes: `postgres_data`, `whatsapp_data`,
  `whatsapp_auth`, `baileys_auth`, `backups_data`, `prometheus_data`, `grafana_data`.
- **Só a porta 80 é publicada** — base SEGURA (SEC-01/02 herdada). ✔
- Backend executa `alembic upgrade head` no boot (L94) — migration automática.
- Soma dos limits = **4.864 MB ≈ 4,75 GB** (sem Ollama).

### 08.2 `docker-compose.yml` (dev) — NÃO usar publicamente

- `5432`, `6379`, `8000`, `5173` publicadas em `0.0.0.0` (L11/L33/L79/L109);
  whatsapp em loopback `127.0.0.1:3001` (L161, correção SEC-02).
- `METRICS_PUBLIC=true` default em dev.

### 08.3 Composes auxiliares

- `docker-compose.e2e.yml` — frontend `8080:80`, **somente testes/CI**.
- `docker-compose.osrm.yml` — OSRM `5000:5000` em 0.0.0.0, opt-in, dev tool
  (imagem `ghcr.io/project-osrm/osrm-backend:latest`).

### 08.4 Config imagens/deploy

- `backend/Dockerfile`: `python:3.14-slim`, usuário não-root `gasflow`,
  `apt-get upgrade` (base para Trivy), pip removido da imagem, healthcheck
  `curl /health`, expõe 8000. ✔
- `frontend/Dockerfile`: node build → nginx alpine; `frontend/nginx.conf`:
  porta 80, gzip, `client_max_body_size 16m`, strip `/api` (L31 `rewrite`),
  `/health|docs|openapi.json|redoc` direto (L46), `/ws` com Upgrade + 3600s
  (L56), SPA fallback `try_files` (L70). **Sem TLS** (terminar na borda). ✔
- Imagens GHCR disponíveis: `ghcr.io/<owner>/<repo>/gasflow-{backend,frontend,whatsapp}`
  (tags `latest`/`sha-*`), poupando build local no servidor (DEPLOY.md L104+).

**Achado O1 (compose prod) — P1**
- **Afirmação:** `.env.production.example` **não contém** `GRAFANA_ADMIN_PASSWORD`,
  exigido com `:?Set GRAFANA_ADMIN_PASSWORD` (compose L234) — o template, como
  está, **falha ao validar/subir** a stack.
- **Evidência:** `Select-String` no example (35 chaves, sem GRAFANA/METRICS/
  WORKERS/FRONTEND_PORT/ALERTS_WEBHOOK_SECRET) vs `:?Set` do compose (L24, 67,
  68, 73, 75, 148, 154, **234**).
- **Estado:** CONFIRMADO.
- **Impacto:** primeiro `docker compose config` do operador quebra; variáveis
  de observabilidade sem default documentado.
- **Ação:** completar o `.env.production.example` (+ comentários de
  `METRICS_PUBLIC`, `ALERTS_WEBHOOK_SECRET`, `BACKEND_WORKERS`, `FRONTEND_PORT`)
  na OPS-01A.
- **Prioridade:** P1.

**Achado O2 (observabilidade) — P1**
- **Afirmação:** o Prometheus raspa `backend:8000/metrics` e `whatsapp:3000/metrics`
  **sem credenciais**, mas em prod ambos exigem auth (`METRICS_PUBLIC=false`;
  backend sem chave no compose = default **False**; whatsapp explícito false na
  compose L151) → **401 nos dois jobs** → stack de monitoramento inútil no dia 1
  e alerta `BackendDown` (rules.yml) dispara falso.
- **Evidência:** `monitoring/prometheus.yml` (scrape_configs sem
  `authorization`/`headers`); `whatsapp/src/infrastructure-routes.ts:16-21`
  (fail-closed); `docker-compose.prod.yml` só com `METRICS_PUBLIC=false` no
  whatsapp; backend sem `METRICS_PUBLIC` no compose.
- **Estado:** CONFIRMADO (estático).
- **Impacto:** alertas/prometheus/grafana subem, mas **nada é coletado**;
  ruido de alerta no primeiro dia.
- **Ação:** OPS-01A — escolher: (a) `METRICS_PUBLIC=true` nos dois serviços
  (aceitável: nenhuma porta métrica é publicada fora da rede interna Docker) ou
  (b) credenciais no `prometheus.yml` (`authorization.credentials`/headers com
  a service key). Recomendação: (b) mantém fail-closed; (a) é mais simples.
- **Prioridade:** P1.

**Achado O3 (persistência WhatsApp) — P2**
- **Afirmação:** `WA_UPLOADS_DIR` default é `<cwd>/uploads` (`.env.example`
  comenta `./uploads`) e **nenhum volume** cobre `/app/uploads` no compose.
- **Evidência:** volumes do compose (seção 08.1) vs `.env.example`.
- **Estado:** CONFIRMADO.
- **Impacto:** mídia (áudio/foto/documento) enviada/recebida pelo gateway se
  perde ao recriar o container.
- **Ação:** OPS-01A — montar volume para o diretório de uploads do gateway.
- **Prioridade:** P2.

**Achado O4 (deploy) — P2**
- **Afirmação:** `alembic upgrade head` roda **automaticamente** no boot do
  backend (compose L94), sem etapa de backup prévio no fluxo.
- **Evidência:** compose L91-94; `backups_data` volume existe mas nada no
  fluxo de deploy o popula antes da migration.
- **Estado:** CONFIRMADO.
- **Impacto:** migration falhando a meio caminho = banco em estado
  indeterminado sem snapshot.
- **Ação:** OPS-01B — wrapper de deploy: backup (pg_dump) → `up -d` → smoke.
- **Prioridade:** P2.

**Achado O5 (logs) — P3**
- **Afirmação:** logs só em stdout dos containers, sem política de rotação
  declarada (driver json-file default do Docker).
- **Evidência:** nenhum `logging:` block no compose.
- **Estado:** CONFIRMADO.
- **Impacto:** disco do HDD enche com logs a longo prazo; sem persistência
  além do daemon.
- **Ação:** OPS-01D — `logging: json-file` com `max-size`/`max-file` por serviço.
- **Prioridade:** P3.

**Achado O6 — P3 (registro)**
- Dev compose publica Postgres/Redis/Backend em `0.0.0.0` e o OSRM em `0.0.0.0`;
  regra já existente: **nunca usar dev compose publicamente** — usar prod como
  base única (Fase OPS-01).

---

## 09. Arquitetura de rede proposta (plano)

```
                    Internet
                       │
              ┌────────▼─────────┐
              │  Cloudflare      │  (túnel de saída — sem abrir portas)
              │  Tunnel (HTTPS)  │
              └────────┬─────────┘
                       │ cloudflared (serviço Windows, saída 443)
┌──────────────────────▼──────────────────────────────────────────┐
│  HOME SERVER (notebook da empresa — Windows, ou futuro Ubuntu)  │
│                                                                  │
│  [host]  relay 127.0.0.1:8080 ──┐   desktop app ──┐             │
│                                 │                 │ 127.0.0.1:8000 (atual)│
│  ┌────────────── Docker: rede interna ────────────┴───────────┐ │
│  │  postgres  redis  backend:8000  whatsapp:3000              │ │
│  │  prometheus  alertmanager  grafana                         │ │
│  │  (nenhuma porta publicada exceto:)                         │ │
│  │  frontend nginx :80  ◄── única exposição (HTTP p/ LAN)     │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────┬──────────────────────────────┬───────────────────────┘
           │ Wi-Fi/cabeado LAN            │ túnel (opcional)
     ┌─────▼──────┐                 ┌─────▼──────┐
     │ Operadores │  portal web :80 │ Entregador │  modo LAN (direto) OU
     │ (PCs da    │                 │ (app RN)   │  modo cloud (relay+túnel)
     │  empresa)  │                 └────────────┘
     └────────────┘
```

**Políticas propostas (para OPS-01C, não aplicadas agora):**

1. Exposição pública mínima = **túnel de saída** (nada de port-forward/abrir
   roteador — regra vigente + possível CGNAT).
2. LAN: só `:80` (portal) + decisão pendente sobre `:8000` para o modo LAN do
   app (ver F3); regras de firewall por subnet, default block.
3. Grafana/Prometheus: acesso **somente via SSH/túnel** ou `docker exec` —
   nunca publicar.
4. TLS termina na borda (túnel) — nginx permanece HTTP interno.
5. Reservas DHCP por MAC para servidor/operadores (evita mudança de IP quebrar
   o app dos entregadores).

---

## 10. Acesso remoto — opções e bloqueios

| Opção | Custo | Portas | WS | Status no repo | Veredito |
|---|---|---|---|---|---|
| **Cloudflare Tunnel quick** (`trycloudflare.com`) | R$0 | nenhuma (saída 443) | ✔ nativo | **já usado/testado** (`relay/start-tunnel.bat`, logs) | ✔ piloto |
| Cloudflare Tunnel nomeado (fixo) | domínio ~US$10/ano (Cloudflare Registrar) | nenhuma | ✔ | documentado `relay/DEPLOY.md` §2b | ✔ produção **com custo de domínio** |
| Tailscale | free tier (verificar uso comercial/atual termo) | saída | ✔ | ausente | ⚠ verificar termos |
| WireGuard self-hosted | R$0 | **abrir porta/roteador** | ✔ | ausente | ✖ bloqueado (regra) + CGNAT? |
| Port-forward direto | R$0 | abrir porta | ✔ | — | ✖ bloqueado (regra) |

**Achado R1 — P1**
- **Afirmação:** URL **fixa** para produção (app entregador/portal fora da LAN)
  exige domínio (~US$10/ano) — **não é assumível num orçamento R$0**; a rota
  R$0 (quick tunnel) tem URL **efêmera** (muda a cada start).
- **Evidência:** `relay/DEPLOY.md` §2a/§2b (explicita a limitação).
- **Estado:** CONFIRMADO.
- **Impacto:** piloto local/LAN 100% viável sem custo; produção com URL fixa
  = decisão de orçamento.
- **Ação:** registrar decisão de domínio em OPS-01C; até lá, piloto LAN +
  quick tunnel para smoke de campo.
- **Prioridade:** P1 (bloqueia "produção", não piloto).

**Achado R2 — P2**
- **Afirmação:** CGNAT/IP público e estabilidade do uplink são **desconhecidos**.
- **Evidência:** não verificado (fora da auditoria read-only de rede).
- **Estado:** PENDENTE.
- **Impacto:** define se até relay-direto seria possível (mesmo que desejado).
- **Ação:** OPS-01C — medir IP público, NAT mapping e jitter.
- **Prioridade:** P2.

---

## 11. O que roda HOJE (estado real de produção)

| Componente | Estado agora | Evidência |
|---|---|---|
| Backend | **`gasflow-backend.exe`** do app **GasFlow Desktop** (`%LOCALAPPDATA%\Programs\GasFlow Desktop\resources\backend\`), `--host 127.0.0.1 --port 8000`, **healthy, uptime ~44 min, 118 MB** | processo PID 7804 + `GET /health` → 200 |
| Portal | servido **embutido pelo backend** (`FRONTEND_DIST` = `resources/frontend`) | `desktop/src/main/app-helpers.ts` `resolveFrontendDist` |
| Banco | **SQLite** `%APPDATA%\gasflow-desktop\gasflow.db` = **3,43 MB** + backups automáticos (`gasflow.db.backups/`, último 21/10) | filesystem |
| WhatsApp | sessão no userData do desktop (`whatsapp-data\app.db`, `Partitions\wa-web-primary`); gateway **NÃO está rodando agora** | `netstat`/`Get-Process` |
| Docker/Postgres | **parados** — a stack prod **nunca subiu nesta máquina** | serviços/distros Stopped |
| Desktop → backend | força `http://127.0.0.1:<porta extraída de gasflowApiUrl>` (default 8000) | `app-helpers.ts:12-19` |

**Achado A1 (arquitetura atual) — P1**
- **Afirmação:** produção hoje = **desktop + SQLite no notebook**; a stack
  Postgres/Docker do compose é **código pronto, nunca exercitado aqui**.
- **Evidência:** seção 11.
- **Estado:** CONFIRMADO.
- **Impacto:** a migração OPS-01 é um **corte real de plataforma**, não um
  deploy: inclui **SQLite → Postgres**, mudança de como o portal é servido e de
  quem fala com o backend.
- **Ação:** OPS-01B (migração de dados + rollback) com smoke e janela definida.
- **Prioridade:** P1.

**Achado A2 — P2**
- **Afirmação:** a atualização automática do app desktop
  (`gasflow-desktop-updater`) e os backups locais do SQLite dependem da máquina
  continuar sendo a estação do operador.
- **Evidência:** `%LOCALAPPDATA%\gasflow-desktop-updater`,
  `gasflow.db.backups\`.
- **Estado:** CONFIRMADO.
- **Impacto:** se a máquina virar "servidor", o desktop do operador precisa de
  outro host — duplicar papéis (servidor + estação) é arriscado para uptime.
- **Ação:** decisão de topo em OPS-01E (papel da máquina).
- **Prioridade:** P2.

---

## 12. Matriz de persistência (o que sobrevive a `docker compose down -v`)

| Dado | Volume/atual | Sobrevive recreate? | Sobrevive `down -v`? |
|---|---|---|---|
| Postgres | `postgres_data` | ✔ | ✖ (destrói) → precisa backup externo |
| Sessão WA (auth) | `whatsapp_auth`, `baileys_auth` | ✔ | ✖ **crítico** (re-qr-code) |
| Dados WA (mensagens) | `whatsapp_data` | ✔ | ✖ |
| Backups dentro do container | `backups_data` | ✔ | ✖ (mesmo disco = não é backup) |
| Métricas/Grafana | `prometheus_data`, `grafana_data` | ✔ | ✖ (dispensável: config-as-code) |
| Redis rate-limit | **sem volume** (efêmero por desenho, L44) | ✖ | ✖ aceitável |
| **Uploads mídia WA** | **sem volume** (F O3) | ✖ | ✖ **bug** |
| Logs | stdout (F O5) | ✖ | ✖ |
| SQLite hoje | `%APPDATA%\gasflow-desktop\gasflow.db` | ✔ (fora do Docker) | n/a — backup próprio |

---

## 13. Sizing — perfis de capacidade (estimativas, a validar em OPS-01A)

Memória **limit** declarados (piso contratado) — soma **4,75 GB**:

| Perfil | Máquina | Viabilidade estimada |
|---|---|---|
| **8 GB** | Ubuntu Server (≈0,5 GB base) | ✔ apertado mas plausível (4,75 + OS + margem ≈ 6,5 GB) |
| **8 GB** | Windows 11 (≈3–4 GB base) | ✖ sem folga (≈8,5–9 GB) |
| **12 GB (atual)** | Windows 11 | ⚠ piloto OK **sem Ollama**; HDD é gargalo antes da RAM |
| **16 GB** | Windows ou Linux | ✔ confortável com Ollama pequeno (3B) |
| **32 GB** (upgrade máx.) | qualquer | ✔ qualquer perfil futuro |

Por serviço (estimativa observada/conhecida, **PENDENTE de medição** em OPS-01A):
postgres 100–300 MB · redis <50 MB · backend 300–700 MB (2 workers) · whatsapp
150–600 MB (wwebjs/chromium) · nginx <30 MB · prometheus 200–400 MB · grafana
150–256 MB · alertmanager <50 MB.
CPU: i3-10110U atende perfil reduzido; **excluir Ollama** do perfil mínimo.

---

## 14. Backups — especificação (não executada nesta fase)

**RPO alvo proposto:** 24 h (dados transacionais) · **RTO:** 2 h.
**Retenção:** 7 diários + 4 semanais + 1 mensual (nunca tudo no mesmo disco).

| Origem | Método proposto | Onde | Prioridade |
|---|---|---|---|
| Postgres | `pg_dump` diário (script + agendador) antes de qualquer deploy | `backups_data` **+ cópia off-host** (pendente definir destino: HD externo/nuvem) | P0 |
| Sessão WA (`*_auth`) | tar semanal + após cada re-qrcode | idem | P0 |
| SQLite (atual) | manter backups automáticos existentes até o corte | `%APPDATA%...\gasflow.db.backups` | P0 (já existe) |
| Mídia WA (quando volume existir) | inclusa no tar de dados | — | P1 |
| Redis | não backup (efêmero por desenho) | — | — |
| Prometheus/Grafana | não backup (infra como código) | — | — |
| Config/.env/secrets | cópia versionada **fora do git** (gerenciador de segredos) | pendente | P1 |

**Teste de restore é critério de aceite** do plano (OPS-01D).

---

## 15. Segurança do host — plano (nada aplicado agora)

1. Conta de operação **não-admin** para serviços; admin só para manutenção.
2. Firewall: default inbound block explícito; abrir apenas `:80` (LAN) e, se
   aprovado F3, `:8000` restrito à subnet.
3. Docker Desktop/WSL2 e SO atualizados antes do corte (imagens com Trivy já no CI).
4. `relay/.env`, `.env.production`, sessão WA: fora do git (já estão), permissões
   restritas; nunca em logs/print (regra desta fase).
5. FastAPI `/docs` e `/metrics` protegidos (docs atrás de auth em prod — checar
   `DISABLE_DOCS`; metrics via O2).
6. TLS só na borda (túnel); nginx interno HTTP (documentado no `nginx.conf`).
7. BitLocker/criptografia do disco: **PENDENTE** (não verificável sem elevação).
8. Uptime/energia: impedir hibernação/sleep (servidor), considerar bateria/UPS
   — laptop é vulnerável a queda + HDD mecânico.

---

## 16. Integração v1.2.1 (app entregador + desktop + relay)

- **Mobile:** URL do servidor digitada pelo usuário e persistida; modos
  LAN/cloud/offline; WS deriva do `baseUrl`; contrato de rotas **não muda**
  com a migração (caminhos idênticos). Placeholder do login: `http://ip:8000`.
- **Modos:** LAN = direto ao backend (`/auth/login`, `/driver/*` na raiz);
  cloud = relay + túnel (já documentado, `relay-test.log`/`tunnel-test.log`
  existem); offline = fila local.
- **Valicação física do app** (GPS no aparelho real, painel, dispositivo em
  `adb`) **segue PENDENTE** desde o checkpoint 21/10 (aparelho fora do `adb`).
- **Relay:** roda no host (uvicorn `127.0.0.1:8080`), token em `relay/.env`,
  desktop força backend local (`127.0.0.1:<porta>`).

**Achado M1 — P1**
- **Afirmação:** o **modo LAN do app não funciona contra a stack prod**:
  a nginx só expõe `/api/*` (strip), `/health|docs…`, `/ws` e SPA fallback —
  `/auth/login`, `/auth/me`, `/driver/*` caem no `try_files` (retorna HTML de
  index) e `/api/v1/mobile/version` tem o prefixo `/api` **removido** →
  `/v1/mobile/version` → 404. E `backend:8000` **não é publicado** no compose
  prod.
- **Evidência:** `mobile/src/logic/api.ts:113,122,134,165,172,241` (rotas na
  raiz), `mobileUpdate.ts:58` (`/api/v1/...`), `frontend/nginx.conf:28-46,70`,
  `docker-compose.prod.yml` (sem porta do backend).
- **Estado:** CONFIRMADO (estático).
- **Impacto:** migração para compose prod **quebra o modo LAN dos entregadores**
  (e o quick test de saúde passaria falso — `/health` está no regex da nginx).
- **Ação:** OPS-01C — escolher: (a) publicar `backend:8000` restrito à LAN
  (firewall por subnet), (b) adicionar locations na nginx para `/auth`, `/driver`
  e passar `/api/v1` sem strip, ou (c) padronizar entregadores no modo cloud
  (relay+túnel). Recomendação: (a) para piloto (menor diff), (b) para produção.
- **Prioridade:** P1.

**Achado M2 — P2**
- **Afirmação:** o modo LAN pressupõe backend acessível **direto na porta 8000**,
  mas em produção a máquina "servidor" pode ficar sem o desktop aberto — hoje
  quem expõe 8000 é o processo do desktop.
- **Evidência:** `app-helpers.ts:18-19` (força `127.0.0.1`) + seção 11.
- **Estado:** CONFIRMADO.
- **Impacto:** dependendo de F3/F4, desktop e app podem exigir ajuste de
  configuração (`gasflowApiUrl`) pós-migração — URLs configuráveis, **contratos
  não quebram**.
- **Ação:** OPS-01B/01C — matriz de configs por papel (servidor/estação/app).
- **Prioridade:** P2.

---

## 17. Resumo de achados (prioridade)

| ID | Achado | Prioridade |
|---|---|---|
| H1 | HDD (não SSD) — gargalo I/O + confiabilidade | **P1** |
| D1 | Docker instalado, nunca exercitado (daemon parado) | **P1** |
| N1 | Produção em Wi-Fi 72 Mbps, NIC com fio sem cabo | **P1** |
| O1 | `.env.production.example` sem `GRAFANA_ADMIN_PASSWORD` → compose falha | **P1** |
| O2 | Prometheus raspa métricas autenticadas sem credencial → 401/dia 1 | **P1** |
| R1 | URL fixa de produção exige domínio pago (custo) | **P1** |
| A1 | Produção atual = desktop+SQLite; compose nunca subiu | **P1** |
| M1 | Modo LAN do app quebra contra stack prod (nginx/8000) | **P1** |
| H2 | RAM 12 GB limitada p/ Windows+stack; upgrade p/ 32 GB possível | P2 |
| N2 | Perfil Public + firewall default não explícito | P2 |
| O3 | Uploads mídia WA sem volume (efêmeros) | P2 |
| O4 | `alembic` no boot sem backup prévio | P2 |
| R2 | CGNAT/velocidade real desconhecidos | P2 |
| A2 | Papel servidor+estação na mesma máquina | P2 |
| M2 | `gasflowApiUrl`/8000 precisa de matriz de config por papel | P2 |
| D2 | Flag de virtualização inconsistente (WSL2 ok) | P3 |
| O5 | Logs stdout sem rotação | P3 |
| O6 | Dev compose/OSRM em 0.0.0.0 (nunca público) | P3 |

---

## 18. Plano OPS-01 (próximas fases — nenhuma executada)

- **OPS-01A — Homologação da stack** (máquina atual, janela controlada):
  iniciar Docker Desktop → validar VT-x/WSL (D2) → completar
  `.env.production.example` (O1) → decidir métricas (O2) → volume de uploads
  (O3) → `compose up` com env dummy → `scripts/smoke-test.sh` → medir RAM/CPU
  real por serviço (seção 13) → snapshots de imagem GHCR vs build local.
- **OPS-01B — Migração de dados e corte**: backup (pg_dump + tar sessão WA +
  SQLite) → migração SQLite→Postgres → wrapper de deploy com backup prévio
  (O4) → smoke pós-corte → rollback documentado.
- **OPS-01C — Rede e acesso**: cabeamento (N1) → decisão M1 (LAN mobile) →
  medição CGNAT/uplink (R2) → Cloudflare quick tunnel (piloto) → decisão de
  domínio (R1) → regras de firewall e reservas DHCP.
- **OPS-01D — Resiliência e segurança**: rotina de backup com teste de restore
  → rotação de logs (O5) → hardening do host (seção 15) → leitor SMART (04) →
  plano de energia/sleep.
- **OPS-01E — Decisão de hardware**: confirmação do papel da máquina (03/A2) →
  HDD→SSD (H1) → RAM 2×16 (H2) → se dedicar servidor: Ubuntu Server LTS +
  desktop movido para estação do operador.

**Critérios de aceite globais:** smoke verde na stack prod; app do entregador
validado em aparelho real (pendência herdada do checkpoint 21/10); backup com
restore testado; monitoramento coletando sem 401; nenhuma porta pública além
do túnel.

---

## 19. Pendências e decisões que dependem de terceiros

1. **Confirmar hardware do futuro servidor** (03) — esta máquina ou outra?
2. **Credenciais/segredos para `.env.production`** (fora do git, fornecidos
   pelo operador): `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, `MARCOS_GAS_API_KEY`,
   `GRAFANA_ADMIN_PASSWORD`, opcional `ALERTS_WEBHOOK_SECRET`.
3. **Orçamento de domínio** (R1) — US$~10/ano na Cloudflare p/ URL fixa.
4. **Aparelho Android físico** fora do `adb` → validação v1.2.1 em campo.
5. **SMART/criptografia** com elevação (04/15).
6. **Destino off-host dos backups** (14) — HD externo/nuvem/qual?
7. **Escolhas técnicas** a confirmar: métricas (O2: header vs público interno),
   LAN mobile (M1: porta 8000 vs locations nginx), sistema do servidor
   (manter Windows vs Ubuntu Server).

---

*Fim do relatório OPS-00 — auditoria somente leitura. Nenhum arquivo de código
alterado, nenhum commit criado, nenhum serviço iniciado ou modificado.*
