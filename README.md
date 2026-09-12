# GasFlow

Sistema operacional para depósitos de gás e água.

[![CI](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/ci.yml)
[![Build & Push](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/build-push.yml/badge.svg)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/build-push.yml)
[![Coverage](https://img.shields.io/badge/cobertura-57%25-yellowgreen)](https://github.com/matheusvinicius1406-cpu/GasFlow)
[![E2E](https://img.shields.io/badge/E2E-8%2F8-brightgreen)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.1.2-blue)](https://github.com/matheusvinicius1406-cpu/GasFlow/releases)

## Arquitetura

**Domain-Driven Design (DDD)** com separação em 4 camadas:

```
backend/app/
├── domain/                    # 🏛️ Domínio (Entidades + Interfaces)
│   ├── client/               # Entidade Cliente + Repository Interface
│   ├── order/                # Entidade Pedido + Repository Interface
│   ├── product/              # Entidade Produto + Repository Interface
│   ├── delivery/             # Entidade Entregador + Repository Interface
│   └── whatsapp/             # Entidade WhatsApp + Repository Interface
│
├── application/               # 📋 Aplicação (Use Cases)
│   ├── client/               # CreateClient, GetClient, ListClients...
│   ├── order/                # CreateOrder, UpdateStatus, AssignDriver...
│   ├── product/              # CreateProduct, UpdateProduct...
│   ├── delivery/             # CreateDriver, ListDrivers...
│   └── whatsapp/             # HandleMessage, SendMessage...
│
├── infrastructure/            # 🔧 Infraestrutura (Implementações)
│   ├── database/             # Connection, Session, InitDB
│   └── repositories/         # SQLAlchemy Models + Repository Implementations
│
├── presentation/              # 🖥️ Apresentação (API)
│   ├── api/                  # FastAPI Routes
│   └── schemas/              # Pydantic Schemas (Request/Response)
│
└── core/                      # ⚙️ Configurações
    └── config.py
```

## Funcionalidades

- ✅ API REST (FastAPI)
- ✅ Banco de dados (PostgreSQL)
- ✅ Clientes com código permanente
- ✅ Pedidos com status
- ✅ Produtos com estoque
- ✅ Entregadores
- ✅ WhatsApp Automation (Baileys — canal não-oficial embutido)
  - Conexão via QR Code
  - Gerenciamento de contatos
  - Listas de segmentação
  - CRM de clientes
  - Campanhas de broadcast
- ✅ App Desktop Windows (Electron) — backend, agente e WhatsApp embutidos, com auto-update

## Fluxo Principal

```
Cliente → Pedido → Entrega → Histórico
```

## Fluxo WhatsApp

```
Mensagem → Bot → Banco de Dados → Pedido
```

## Contatos, CRM e Reativação

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

## Stack

### Backend (Python)
- FastAPI
- SQLAlchemy
- PostgreSQL
- Pydantic
- PyInstaller (backend embutido no Desktop como `gasflow-backend.exe`)

### WhatsApp (Node.js)
- Baileys (substituiu o whatsapp-web.js — ver docs/phase16/BAILEYS_MIGRATION.md)
- Express 5
- SQLite (contatos/listas/campanhas)

### Frontend (React)
- React 19 + Vite
- TypeScript

### Desktop (Electron)
- Electron 44 + TypeScript
- electron-builder 26 (instalador NSIS + blockmap)
- electron-updater (auto-update via GitHub Releases)
- Backend FastAPI embutido (PyInstaller) + agente de integração + serviço WhatsApp como subprocessos

## Setup

### Pré-requisitos
- Docker + Docker Compose
- OU Python 3.12+ e Node.js 20+ (as imagens Docker oficiais usam `python:3.14-slim` e `node:26-slim`)

### Início rápido (sem Docker — um comando)

```bash
cd GasFlow
./start-dev.sh     # sobe backend + WhatsApp + frontend, espera os health checks e abre o navegador
```

No Windows também dá para dar **duplo clique em `start-dev.cmd`**.

O script:
- cria o `.env` de dev na primeira execução (login padrão **admin / gasflow-dev**);
- instala dependências se faltarem;
- sobe os 3 serviços em background com logs em `logs/`:

| Serviço | URL |
|---------|-----|
| Painel (frontend) | http://localhost:5173 |
| API + Swagger | http://localhost:8000/docs |
| WhatsApp (QR Code) | http://localhost:3001/connect |

- reaproveita serviços que já estão no ar (rodar de novo é seguro);
- abre o navegador (Brave se instalado, senão o padrão).

Para parar tudo que o script iniciou:

```bash
./stop-dev.sh
```

### Com Docker (Recomendado)

```bash
# Clonar o repositório
git clone https://github.com/matheusvinicius1406-cpu/GasFlow.git
cd GasFlow

# Iniciar todos os serviços (ambiente de dev)
docker-compose up -d

# Verificar status
docker-compose ps
```

### Produção

```bash
# 1. Ambiente de produção (Postgres + migrations + nginx)
cp .env.production.example .env.production   # preencha as variáveis

# 2. Subir a stack de produção
#    O backend aplica `alembic upgrade head` automaticamente no boot.
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

# 3. Validar a instalação
./scripts/smoke-test.sh
```

Consulte **[DEPLOY.md](DEPLOY.md)** para deploy, atualização, rollback,
imagens GHCR e troubleshooting. CI/CD em `.github/workflows/`.

### Serviços (dev)

| Serviço | URL | Descrição |
|---------|-----|-----------|
| API Backend | http://localhost:8000 | FastAPI - API principal |
| Docs API | http://localhost:8000/docs | Swagger UI |
| WhatsApp | http://localhost:3001 | Serviço WhatsApp |
| WhatsApp Connect | http://localhost:3001/connect | QR Code de conexão |
| PostgreSQL | localhost:5432 | Banco de dados |

### Setup Manual (Sem Docker)

#### 1. Backend (Python)

```bash
cd backend

# Criar virtualenv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar banco (SQLite para desenvolvimento)
cp .env.example .env

# Iniciar servidor
uvicorn app.main:app --reload --port 8000
```

#### 2. WhatsApp Service (Node.js)

```bash
cd whatsapp

# Instalar dependências
npm install

# Compilar TypeScript
npm run build

# Iniciar em desenvolvimento
npm run dev

# OU iniciar em produção
npm start
```

## Uso

### 1. Conectar WhatsApp

1. Acesse http://localhost:3001/connect
2. Clique em "Gerar QR Code"
3. Escaneie o QR Code com seu WhatsApp
4. A sessão será salva automaticamente

### 2. Sincronizar Contatos

```bash
# Via API Bridge (FastAPI)
curl -X POST http://localhost:8000/whatsapp/contacts/sync

# Ou diretamente no serviço WhatsApp
curl -X POST http://localhost:3001/api/contacts/sync
```

### 3. Criar Campanha

```bash
# Criar campanha
curl -X POST http://localhost:8000/whatsapp/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Promoção de Gás",
    "message": "Oferta especial: Gás 13kg por R$89,90!",
    "list_id": 1
  }'

# Iniciar envio
curl -X POST http://localhost:8000/whatsapp/campaigns/1/start
```

## Estrutura de Domínios

### Cliente
- Todo cliente possui código único (ex: 000001)
- Código nunca muda
- Um cliente pode ter mais de um telefone

### Pedido
- Todo pedido pertence a um cliente
- Status: PENDING → CONFIRMED → PREPARING → DELIVERING → DELIVERED
- Nenhum pedido é apagado

### Produto
- Todo produto possui código único
- Possui nome, tipo (GÁS/ÁGUA), preço e estoque
- Estoque é baixado automaticamente ao criar pedido

### WhatsApp
- Bot responde automaticamente
- Clientes podem fazer pedidos via mensagem
- Campanhas respeitam opt-in/opt-out
- Proteção contra spam (rate limiting)

## Desenvolvimento

## Configuração do Serviço WhatsApp (segurança)

O serviço Node (`whatsapp/`) controla conexão, campanhas e envios. Variáveis
relevantes no `whatsapp/.env` (ou nas settings do Desktop):

| Variável | Default | Descrição |
|----------|---------|-----------|
| `MARCOS_GAS_API_KEY` | *(vazio)* | Chave service-to-service (backend ↔ serviço). **Obrigatória quando `ENVIRONMENT=production`** — o boot do serviço aborta (`process.exit(1)`) se ausente, para não expor QR/contatos na rede. |
| `ENVIRONMENT` | `development` | Ativa o modo de segurança acima. |
| `WA_UPLOADS_DIR` | `<cwd>/uploads` | Diretório allowlist para `mediaPath` no envio de mídia — caminhos fora dele são rejeitados (400). Nunca aponte para a raiz do projeto. |
| `WA_MINUTE_CAP` / `WA_HOURLY_CAP` | 20 / 200 | Caps de volume do anti-ban (por conta). |
| `WA_QUIET_HOURS_START` / `WA_QUIET_HOURS_END` | 22 / 7 | Janela noturna sem envios de campanha. |

### Rate limiting e opt-out (comportamento atual)

- `POST /api/whatsapp/accounts/:id/messages` (e o alias `/send` usado pelas
  automações) passam pelo anti-ban: caps por minuto/hora + cooldown por
  destinatário. Bloqueio retorna **429** com cabeçalho **`Retry-After`**.
- Campanhas usam warmup progressivo (50→1000/dia) e quiet hours.
- Automações (FASE 14) consultam o `marketing_status` do cliente no serviço:
  `OPTED_OUT`/`SUPPRESSED`/`BLOCKED` não recebem mensagens, e erro na consulta
  é **fail-closed** (não envia).

### Logs estruturados

O `setup_logging()` do backend é idempotente — múltiplos módulos podem chamá-lo
sem duplicar linhas no stdout.

### Typecheck

```bash
# Backend
cd backend && python -m mypy app/

# WhatsApp
cd whatsapp && npm run typecheck

# Desktop
cd desktop && npm run typecheck

# Frontend (tsc -b roda como parte do build)
cd frontend && npm run build
```

### Testes

```bash
# Backend
cd backend && python -m pytest -q          # ruff check app tests

# Frontend
cd frontend && npm test                     # vitest

# WhatsApp
cd whatsapp && npm test

# Desktop
cd desktop && npm test

# E2E (stack completo real em Docker — ver docs/phase15/E2E.md)
docker compose -f docker-compose.e2e.yml up -d --build
cd e2e && npm ci && npx playwright install chromium && npx playwright test
```

## Auto-update (app Desktop Windows)

O app Desktop se atualiza sozinho via `electron-updater` + GitHub Releases:

1. **Bump** da versão em `desktop/package.json` + commit.
2. **Push de tag** `v<versão>` → o workflow `release.yml` builda o instalador
   (`GasFlow Desktop Setup <versão>.exe` + `latest.yml` + `*.blockmap`) e
   publica na Release.
3. Apps instalados checam o canal `latest` 15s após abrir (e a cada 6h),
   baixam e instalam ao clicar em "Reiniciar e instalar" (ou ao fechar).

Para gerar o instalador localmente:

```bash
cd desktop && npm run dist    # builda frontend/agent/whatsapp/backend e empacota o NSIS
```

Detalhes e logs: [`desktop/README.md`](desktop/README.md#auto-update-electron-updater--github-releases).

## Licença

Projeto privado — GasFlow
