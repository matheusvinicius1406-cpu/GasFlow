<p align="center">
  <img src="frontend/public/favicon.svg" alt="Símbolo do GasFlow" width="88" height="88">
</p>

<h1 align="center">GasFlow</h1>

<p align="center">
  <b>Sistema operacional para depósitos de gás e água:</b> pedidos, entregas,<br>
  automação de WhatsApp, rastreamento em tempo real e app próprio do entregador.
</p>

<p align="center">
  <a href="https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/ci.yml"><img src="https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/build-push.yml"><img src="https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/build-push.yml/badge.svg" alt="Build & Push"></a>
  <a href="https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/e2e.yml"><img src="https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/e2e.yml/badge.svg" alt="E2E"></a>
  <a href="https://github.com/matheusvinicius1406-cpu/GasFlow"><img src="https://img.shields.io/badge/cobertura-57%25-yellowgreen" alt="Cobertura"></a>
  <a href="https://github.com/matheusvinicius1406-cpu/GasFlow/releases"><img src="https://img.shields.io/badge/version-1.2.1-blue" alt="Versão"></a>
</p>

<details>
<summary><b>Sumário</b></summary>

- [Visão geral](#visão-geral)
- [Aplicações do monorepo](#aplicações-do-monorepo)
- [Arquitetura](#arquitetura)
- [Início rápido](#início-rápido)
- [Funcionalidades](#funcionalidades)
- [Fluxos](#fluxos)
- [WhatsApp — integração e automação](#whatsapp--integração-e-automação)
- [Stack](#stack)
- [Desenvolvimento](#desenvolvimento)
- [Releases e versionamento](#releases-e-versionamento)
- [Documentação](#documentação)
- [Licença](#licença)

</details>

## Visão geral

Quatro aplicações cooperando sobre o mesmo domínio:

| Aplicação | Papel |
|-----------|-------|
| **Painel web** (`frontend/`) | React 19 + Vite — clientes, pedidos, produtos, entregadores, mapa de rastreio, Integrações e Automações. |
| **Desktop Windows** (`desktop/`) | Electron — o painel original embarcado com backend FastAPI, agente de impressão/etiqueta e serviço WhatsApp como subprocessos, com **auto-update** via GitHub Releases. |
| **App do Entregador** (`mobile/`) | React Native (Android) — rota do dia, ações de entrega e envio de localização, com **auto-update de APK** pelo `GET /mobile/version`. |
| **Serviço WhatsApp** (`whatsapp/`) | Node.js + Baileys — conexão da conta, contatos/CRM, listas, campanhas e automações (canal não-oficial embutido). |

O backend (`backend/`) é a espinha dorsal: API REST, domínio, persistência e
o `mobile_version.json` que alimenta o updater do app.

## Aplicações do monorepo

| Diretório | Stack | Papel | Versão |
|-----------|-------|-------|--------|
| `backend/` | Python 3.12+ · FastAPI · SQLAlchemy · Pydantic | API + domínio (DDD) + SQLite/PostgreSQL | serviço |
| `frontend/` | React 19 · Vite · TypeScript | Painel web (SPA) | **1.2.1** |
| `desktop/` | Electron 44 · electron-builder 26 | App Windows com backend embutido + auto-update | **1.2.1** |
| `mobile/` | React Native 0.76 | App Android do entregador + APK | **1.2.1** |
| `whatsapp/` | Node.js · Baileys · Express 5 | Conexão WhatsApp, CRM, campanhas | 1.1.7 |
| `agent/` | Node.js | Agente de integração (impressão/etiquetas) | 1.1.7 |
| `e2e/` | Playwright | Testes E2E sobre a stack real em Docker | 1.0.0-rc.3 |
| `relay/` · `monitoring/` | Go/Compose · Prometheus/Grafana | Relay de rastreio na nuvem e observabilidade | infra |
| `scripts/` · `docs/` · `auditoria/` | Python · Markdown | Ferramentas, specs e auditorias | — |

`frontend`, `desktop` e `mobile` são versionados **em lockstep** (mesma tag
`vX.Y.Z`).

## Arquitetura

**Domain-Driven Design (DDD)** com separação em 4 camadas:

```
backend/app/
├── domain/                    # Domínio (Entidades + Interfaces)
│   ├── client/               # Entidade Cliente + Repository Interface
│   ├── order/                # Entidade Pedido + Repository Interface
│   ├── product/              # Entidade Produto + Repository Interface
│   ├── delivery/             # Entidade Entregador + Repository Interface
│   └── whatsapp/             # Entidade WhatsApp + Repository Interface
│
├── application/               # Aplicação (Use Cases)
│   ├── client/               # CreateClient, GetClient, ListClients...
│   ├── order/                # CreateOrder, UpdateStatus, AssignDriver...
│   ├── product/              # CreateProduct, UpdateProduct...
│   ├── delivery/             # CreateDriver, ListDrivers...
│   └── whatsapp/             # HandleMessage, SendMessage...
│
├── infrastructure/            # Infraestrutura (Implementações)
│   ├── database/             # Connection, Session, InitDB + seeds
│   └── repositories/         # SQLAlchemy Models + Repository Implementations
│
├── presentation/              # Apresentação (API)
│   ├── api/                  # FastAPI Routes
│   └── schemas/              # Pydantic Schemas (Request/Response)
│
└── core/                      # Configurações
    └── config.py
```

## Início rápido

### Sem Docker — um comando

```bash
cd GasFlow
./start-dev.sh     # backend + WhatsApp + frontend, com health checks e navegador
```

No Windows, **duplo clique em `start-dev.cmd`**.

O script cria o `.env` de dev na primeira execução (login padrão
**admin / gasflow-dev**), instala dependências se faltarem, sobe os 3
serviços em background com logs em `logs/` e reaproveita serviços já no ar
(rodar de novo é seguro):

| Serviço | URL |
|---------|-----|
| Painel (frontend) | http://localhost:5173 |
| API + Swagger | http://localhost:8000/docs |
| WhatsApp (QR Code) | http://localhost:3001/connect |

Para parar tudo que o script iniciou:

```bash
./stop-dev.sh
```

### Com Docker

```bash
git clone https://github.com/matheusvinicius1406-cpu/GasFlow.git
cd GasFlow
docker-compose up -d       # subir
docker-compose ps          # status
```

### Produção

```bash
cp .env.production.example .env.production   # preencha as variáveis
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
./scripts/smoke-test.sh                      # validar
```

O backend aplica `alembic upgrade head` automaticamente no boot. Deploy,
atualização, rollback e imagens GHCR: **[DEPLOY.md](DEPLOY.md)**.
CI/CD em `.github/workflows/`.

### Setup manual (sem Docker)

```bash
# 1. Backend (Python)
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # SQLite para desenvolvimento
uvicorn app.main:app --reload --port 8000

# 2. WhatsApp (Node.js)
cd whatsapp
npm install && npm run build
npm run dev                     # ou npm start em produção
```

### App do Entregador (APK)

A receita de build (caminho ASCII, JDK 17, `newArchEnabled=false`) está em
**[`mobile/android/BUILD.md`](mobile/android/BUILD.md)**; a versão vive em
`mobile/android/app/build.gradle` (`versionName` + `versionCode`).

## Funcionalidades

**Operação**

- ✅ Clientes com código permanente, múltiplos telefones e endereço (com
  enriquecimento por IA a partir do nome do contato)
- ✅ Pedidos com status (`PENDING → CONFIRMED → PREPARING → DELIVERING →
  DELIVERED`), estoque baixado automaticamente ao criar pedido
- ✅ Produtos com código único, tipo (GÁS/ÁGUA), preço e estoque
- ✅ Entregadores com CRUD no painel e ações `/driver/*` no app
- ✅ Rastreamento em tempo real (mapa do painel + telemetria do app)
- ✅ Roteirização com otimização de sequência (OR-Tools) e sugestão de
  despacho — flags `DELIVERY_SMART_ROUTING_ENABLED` /
  `DELIVERY_SMART_DISPATCH_ENABLED`
- ✅ Notas/etiquetas via impressão RAW no Windows (agente desktop)

**WhatsApp e automação**

- ✅ Conexão via QR Code (Baileys — canal não-oficial embutido)
- ✅ Sincronização de contatos 1:1 para o CRM + import/export `.vcf`
- ✅ Listas de segmentação, CRM de clientes e campanhas de broadcast
- ✅ Bot responde automaticamente e clientes pedem por mensagem
- ✅ Reativação de inativos com template e confirmação de endereço
- ✅ Anti-ban: caps por minuto/hora, cooldown por destinatário, warmup
  progressivo e quiet hours

**Plataforma**

- ✅ App Desktop Windows com auto-update (GitHub Releases)
- ✅ App Android do entregador com auto-update de APK
- ✅ Multiusuário com RBAC (roles/permissões) e audit
- ✅ Logs estruturados, métricas Prometheus/Grafana e relay para a nuvem

## Fluxos

```
Cliente → Pedido → Entrega → Histórico
```

```
Mensagem → Bot → Banco de Dados → Pedido
```

## WhatsApp — integração e automação

### Sincronização de contatos (WhatsApp → CRM)

O serviço WhatsApp empurra os contatos 1:1 da conta para o CRM do backend:

- **Automático no boot** do serviço (30s após subir) e **ao conectar** a
  conta (QR escaneado/reconexão, ~8s após `ready` para os contatos carregarem);
- **Manual** via `POST /api/whatsapp/crm-sync` (no serviço) ou
  `POST /whatsapp/crm-sync` (proxy no backend);
- O botão **"Sincronizar WhatsApp"** na tela de Contatos dispara os dois.

O envio é em lotes (`BATCH_SYNC_SIZE`, default 100) para
`POST /clients/contacts/sync-batch`, autenticado por `X-GasFlow-Key`
(somente serviço; **sem** fallback JWT). O upsert é idempotente por telefone:
contato novo cria cliente com placeholders (`Contato <tel>`, endereço
"A definir"); existente apenas enriquece (nome só preenche placeholder,
código do CRM nunca muda).

### Import/Export .vcf

- **Importar**: tela de Contatos → "Importar .vcf" (ou `POST
  /clients/contacts/import-vcf`). Upsert por telefone, mesmo contrato acima.
- **Exportar**: tela de Contatos → "Exportar .vcf" (ou `GET
  /clients/contacts/export-vcf`) — gera arquivo com nome, telefone e endereço.

### Enriquecimento por IA

Contatos vindos do WhatsApp cujo nome embute endereço (ex.: "Maria - Rua
Flores, 123, Centro") podem ser enriquecidos via `POST
/clients/contacts/{codigo}/enrich`: o LLM extrai rua/número/complemento/bairro
e grava no CRM. Falha do LLM = no-op seguro.

### Reativação de inativos

Mensagens automáticas para clientes OPTED_IN sem interação há N dias,
solicitando confirmação do endereço:

1. Ative em **Configurações › Sistema › WhatsApp**
   (`whatsapp_reactivate_enabled`), ajuste `whatsapp_reactivate_days` e o
   `whatsapp_reactivate_template` (variáveis `{{nome}} {{rua}} {{numero}}
   {{complemento}} {{bairro}}`);
2. Dispare em **Contatos › "Reativar inativos"** (ou `POST
  /clients/contacts/reactivate`, com `dry_run=true` para pré-visualizar);
3. As mensagens entram na fila de automações (PENDING, idempotente por
   cliente/dia) e são enviadas pelo executor — ou em background com
   `AUTOMATION_POLL_SECONDS>0` no backend, ou por cron externo chamando
   `POST /whatsapp-automation/process-pending`.

Clientes que respondem têm `last_interaction_at` atualizado (saem da lista
de inativos) e a IA pode corrigir o endereço na própria conversa (tool
`update_client_address`, com confirmação).

### Variáveis de ambiente relevantes

| Variável | Onde | Default | Função |
|----------|------|---------|--------|
| `BATCH_SYNC_SIZE` | serviço WhatsApp | `100` | Tamanho do lote do push ao CRM |
| `GASFLOW_BACKEND_URL` | serviço WhatsApp | — | Base do backend (push de contatos e mensagens recebidas) |
| `GASFLOW_SERVICE_KEY` | serviço WhatsApp | — | Enviada como `X-GasFlow-Key` (mesmo valor de `MARCOS_GAS_API_KEY`) |
| `WHATSAPP_SERVICE_KEY` / `MARCOS_GAS_API_KEY` | backend | — | Chave esperada pelo backend nas chamadas do serviço |
| `AUTOMATION_POLL_SECONDS` | backend | `0` (off) | Intervalo do executor de automações em background |
| `DELIVERY_SMART_ROUTING_ENABLED` | backend | `false` | Liga a Fase 8 (otimização de sequência com OR-Tools). Desligado, o endpoint `/route/optimize` responde 409 |
| `DELIVERY_SMART_DISPATCH_ENABLED` | backend | `false` | Liga a Fase 9 (scorer de despacho no `/dispatch/suggest`). Desligado, mantém o cálculo inline atual |
| `ROUTING_PROVIDER` | backend | `haversine` | Provedor de roteamento: `haversine` (zero infra) ou `osrm` (self-hosted) |
| `OSRM_BASE_URL` | backend | `""` | URL do OSRM (ex.: `http://osrm:5000`). Sem URL, cai no haversine |
| `DISPATCH_LOAD_FULL_DELIVERIES` | backend | `4` | Entregas concorrentes que "enchem" o entregador (denominador do load no scorer) |

### Segurança e rate limiting do serviço

Variáveis relevantes no `whatsapp/.env` (ou nas settings do Desktop):

| Variável | Default | Descrição |
|----------|---------|-----------|
| `MARCOS_GAS_API_KEY` | *(vazio)* | Chave service-to-service (backend ↔ serviço). **Obrigatória quando `ENVIRONMENT=production`** — o boot do serviço aborta (`process.exit(1)`) se ausente, para não expor QR/contatos na rede. |
| `ENVIRONMENT` | `development` | Ativa o modo de segurança acima. |
| `WA_UPLOADS_DIR` | `<cwd>/uploads` | Diretório allowlist para `mediaPath` no envio de mídia — caminhos fora dele são rejeitados (400). Nunca aponte para a raiz do projeto. |
| `WA_MINUTE_CAP` / `WA_HOURLY_CAP` | 20 / 200 | Caps de volume do anti-ban (por conta). |
| `WA_QUIET_HOURS_START` / `WA_QUIET_HOURS_END` | 22 / 7 | Janela noturna sem envios de campanha. |

Comportamento atual:

- `POST /api/whatsapp/accounts/:id/messages` (e o alias `/send` usado pelas
  automações) passam pelo anti-ban: caps por minuto/hora + cooldown por
  destinatário. Bloqueio retorna **429** com cabeçalho **`Retry-After`**.
- Campanhas usam warmup progressivo (50→1000/dia) e quiet hours.
- Automações consultam o `marketing_status` do cliente no serviço:
  `OPTED_OUT`/`SUPPRESSED`/`BLOCKED` não recebem mensagens, e erro na consulta
  é **fail-closed** (não envia).

## Stack

| Camada | Tecnologias |
|--------|-------------|
| Backend | Python · FastAPI · SQLAlchemy · Pydantic · PostgreSQL/SQLite · Alembic · PyInstaller (`gasflow-backend.exe` embutido no Desktop) |
| Frontend | React 19 · Vite · TypeScript |
| Desktop | Electron 44 · electron-builder 26 (NSIS + blockmap) · electron-updater (auto-update via GitHub Releases) |
| App do entregador | React Native 0.76 (Android) |
| WhatsApp | Node.js · Baileys · Express 5 · SQLite |
| Testes | pytest (backend) · Vitest (frontend) · node:test (mobile/desktop) · Playwright (e2e) |
| Infra | Docker/Docker Compose · GH Actions · Prometheus/Grafana · relay de rastreio |

## Desenvolvimento

### Typecheck

```bash
cd backend  && python -m mypy app/
cd whatsapp && npm run typecheck
cd desktop  && npm run typecheck
cd mobile   && npm run typecheck
cd frontend && npm run build      # tsc -b roda como parte do build
```

### Testes

```bash
cd backend  && python -m pytest -q
cd frontend && npm test           # vitest
cd whatsapp && npm test
cd desktop  && npm test           # node:test
cd mobile   && npm test           # node:test (lógica pura)
```

### Lint (formato obrigatório)

```bash
python -m ruff check . ; python -m ruff format --check .
```

### E2E (stack completa real em Docker)

```bash
docker compose -f docker-compose.e2e.yml up -d --build
cd e2e && npm ci && npx playwright install chromium && npx playwright test
```

### Identidade visual

O símbolo do projeto (launcher Android, PNGs do app, `icon.png`/`icon.ico` do
desktop e `favicon.svg` do web) é gerado por **um** script a partir da mesma
geometria — após mudar a paleta ou o desenho:

```bash
python scripts/generate_brand_icons.py
```

A UI do app do entregador segue o design system escuro em `mobile/src/theme`
(tokens espelhados do `frontend/src/index.css`).

## Releases e versionamento

- **Versão**: `frontend/`, `desktop/` e `mobile/` em lockstep (ex.: 1.2.1).
  Bump nos três `package.json` + locks, `mobile/android/app/build.gradle`
  (`versionName` + `versionCode`), `mobile/src/logic/config.ts` e
  `mobile_version.json` (+ fallback em `backend/app/presentation/api/mobile_version.py`).
- **Tag `vX.Y.Z`** dispara o `release.yml`: builda o instalador
  (`GasFlow Desktop Setup <versão>.exe` + `latest.yml` + `*.blockmap`) e
  publica a Release.
- **Auto-update do desktop**: apps instalados checam o canal `latest` 15s
  após abrir (e a cada 6h), baixam e instalam ao clicar em "Reiniciar e
  instalar" (ou ao fechar). Gerador local: `cd desktop && npm run dist`.
- **Auto-update do APK**: anexar `app-release.apk` na Release — o
  `GET /mobile/version` lê `mobile_version.json` e o app baixa o
  `download_url` (`releases/latest/download/app-release.apk`).
- **CHANGELOG**: seções `## [X.Y.Z] - data` no estilo Keep a Changelog
  (ver [CHANGELOG.md](CHANGELOG.md)).

Detalhes do updater: [`desktop/README.md`](desktop/README.md#auto-update-electron-updater--github-releases).

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [CHANGELOG.md](CHANGELOG.md) | Histórico de releases |
| [DEPLOY.md](DEPLOY.md) | Deploy, atualização, rollback, GHCR, troubleshooting |
| [docs/STATUS_E_PLANO.md](docs/STATUS_E_PLANO.md) | Status do projeto e plano mestre |
| [docs/CHECKPOINT_2026_10_21.md](docs/CHECKPOINT_2026_10_21.md) | Último checkpoint de trabalho |
| [mobile/android/BUILD.md](mobile/android/BUILD.md) | Receita de build do APK |
| [release-v1.2.0-spec.md](release-v1.2.0-spec.md) | Spec de release (modelo) |
| `.github/workflows/` | CI, E2E, build de imagens e release |

## Licença

Projeto privado — GasFlow
