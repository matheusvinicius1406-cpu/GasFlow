# GasFlow — FASE 0: Auditoria Arquitetural (Refinada)

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).


**Data:** 26/08/2026
**Auditor:** Buffy (Codebuff)
**Status:** COMPLETO ✅
**Versão:** 2.0

---

## 1. Visão Geral

O GasFlow é um sistema operacional para revendas de gás e água. O repositório atual contém:

- **Backend Python/FastAPI** com arquitetura DDD (4 camadas)
- **WhatsApp Service Node.js** com whatsapp-web.js
- **Docker Compose** com 3 serviços
- **Zero frontend** (nenhuma tela de UI)
- **Zero testes** (nenhum teste automatizado)

---

## 2. Árvore Atual do Repositório

```
GasFlow/                                    (79 arquivos total)
├── backend/                                (61 arquivos Python)
│   ├── app/
│   │   ├── domain/                         # 🏛️ Camada de Domínio
│   │   │   ├── client/
│   │   │   │   ├── entity.py              # ✅ Client entity com validações
│   │   │   │   └── repository.py          # ✅ Interface abstrata
│   │   │   ├── order/
│   │   │   │   ├── entity.py              # ✅ Order + OrderStatus enum + transições
│   │   │   │   └── repository.py
│   │   │   ├── product/
│   │   │   │   ├── entity.py              # ✅ Product com controle estoque
│   │   │   │   └── repository.py
│   │   │   ├── delivery/
│   │   │   │   ├── entity.py              # ✅ DeliveryDriver
│   │   │   │   └── repository.py
│   │   │   └── whatsapp/
│   │   │       ├── entity.py              # ✅ Conversation + Message + Status enum
│   │   │       └── repository.py
│   │   │
│   │   ├── application/                    # 📋 Camada de Aplicação
│   │   │   ├── client/use_cases.py        # ✅ 5 Use Cases (CRUD)
│   │   │   ├── order/use_cases.py         # ✅ 5 Use Cases (CRUD + validação)
│   │   │   ├── product/use_cases.py       # ✅ 5 Use Cases (CRUD)
│   │   │   ├── delivery/use_cases.py      # ✅ 4 Use Cases (CRUD)
│   │   │   └── whatsapp/use_cases.py      # ✅ 3 Use Cases (bot flow)
│   │   │
│   │   ├── infrastructure/                 # 🔧 Camada de Infraestrutura
│   │   │   ├── database/
│   │   │   │   ├── base.py                # ✅ DeclarativeBase
│   │   │   │   ├── connection.py           # ✅ Engine + SessionLocal
│   │   │   │   ├── dependencies.py         # ✅ get_db()
│   │   │   │   └── init_db.py             # ✅ create_all()
│   │   │   └── repositories/
│   │   │       ├── client_model.py         # ✅ SQLAlchemy model
│   │   │       ├── client_repository.py    # ✅ Repository impl
│   │   │       ├── order_model.py          # ✅
│   │   │       ├── order_repository.py     # ✅
│   │   │       ├── product_model.py        # ✅
│   │   │       ├── product_repository.py   # ✅
│   │   │       ├── delivery_model.py       # ✅
│   │   │       ├── delivery_repository.py  # ✅
│   │   │       ├── whatsapp_model.py       # ✅
│   │   │       └── whatsapp_repository.py  # ✅
│   │   │
│   │   ├── presentation/                   # 🖥️ Camada de Apresentação
│   │   │   ├── api/
│   │   │   │   ├── health.py              # ✅ GET /health
│   │   │   │   ├── clients.py             # ✅ CRUD endpoints
│   │   │   │   ├── orders.py              # ✅ CRUD + status + assign
│   │   │   │   ├── products.py            # ✅ CRUD endpoints
│   │   │   │   ├── delivery.py            # ✅ CRUD endpoints
│   │   │   │   └── whatsapp.py            # ✅ Bridge para Node.js
│   │   │   └── schemas/
│   │   │       ├── client.py              # ✅ Pydantic schemas
│   │   │       ├── order.py
│   │   │       ├── product.py
│   │   │       ├── delivery.py
│   │   │       └── whatsapp.py
│   │   │
│   │   ├── core/
│   │   │   └── config.py                  # ✅ Settings (básico)
│   │   │
│   │   └── main.py                        # ✅ FastAPI app + CORS + routers
│   │
│   ├── requirements.txt                    # ✅ 7 dependências
│   └── Dockerfile                          # ✅ Python 3.12
│
├── whatsapp/                               (12 arquivos TypeScript)
│   ├── src/
│   │   ├── provider/
│   │   │   ├── types.ts                   # ✅ Interface abstrata
│   │   │   └── wwebjs-provider.ts         # ✅ Implementação concreta
│   │   ├── server.ts                      # ✅ Express server
│   │   ├── routes.ts                      # ✅ Todas as rotas
│   │   ├── db.ts                          # ✅ SQLite + schemas
│   │   ├── auth.ts                        # ✅ API key middleware
│   │   ├── broadcast.ts                   # ✅ Worker de campanhas
│   │   ├── sync.ts                        # ✅ Sincronização contatos
│   │   ├── dedupe.ts                      # ✅ Deduplicação
│   │   ├── list-seed.ts                   # ✅ Seeds de listas
│   │   ├── connect-page.ts                # ✅ QR Code HTML page
│   │   └── normalize.ts                   # ✅ Phone normalization
│   ├── package.json                       # ✅ 3 deps + 5 devDeps
│   ├── tsconfig.json                      # ✅ TypeScript config
│   └── Dockerfile                         # ✅ Node 20 + Chromium
│
├── docker-compose.yml                      # ✅ 3 services
├── docs/                                   # ✅ 6 arquivos .md
└── README.md                               # ✅ Atualizado
```

---

## 3. Stack Detectada

### Backend (Python)

| Componente | Versão | Status | Notas |
|------------|--------|--------|-------|
| Python | 3.12+ | ✅ | Requerido por pydantic v2 |
| FastAPI | latest | ✅ | framework web async |
| SQLAlchemy | 2.x | ✅ | ORM principal |
| Pydantic | 2.x | ✅ | Validação de schemas |
| uvicorn | latest | ✅ | ASGI server |
| httpx | latest | ✅ | HTTP client (WhatsApp bridge) |
| python-dotenv | latest | ✅ | .env loading |
| psycopg2-binary | latest | ✅ | PostgreSQL adapter |

### WhatsApp (Node.js)

| Componente | Versão | Status | Notas |
|------------|--------|--------|-------|
| Node.js | 20+ | ✅ | LTS |
| TypeScript | 5.8 | ✅ | Type safety |
| whatsapp-web.js | 1.26.0 | ✅ | WhatsApp Web API |
| Express | 4.21 | ✅ | HTTP server |
| qrcode | 1.5.4 | ✅ | QR Code generation |
| tsx | 4.20 | ✅ | Dev runner |

### Infraestrutura

| Componente | Versão | Status | Notas |
|------------|--------|--------|-------|
| Docker | 3.9 | ✅ | Containerização |
| Docker Compose | 3.9 | ✅ | Orquestração |
| PostgreSQL | 16 | ✅ | Banco principal |
| SQLite | built-in | ✅ | WhatsApp + dev fallback |

---

## 4. Análise de Dependências

### Dependências por Camada

```
Domain → Apenas stdlib (dataclasses, datetime, enum, abc)
    ↓
Application → Domain (entidades + interfaces)
    ↓
Infrastructure → Application + SQLAlchemy + Domain
    ↓
Presentation → FastAPI + Pydantic + Infrastructure + Application
```

### Verificação de Circular Dependencies

**Resultado:** ✅ NENHUMA dependência circular detectada

```
Domain ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← (zero dependências externas)
    ↑
Application ← ← ← ← ← ← ← ← ← ← ← ← ← (apenas Domain)
    ↑
Infrastructure ← ← ← ← ← ← ← ← ← ← ← ← (Application + SQLAlchemy)
    ↑
Presentation ← ← ← ← ← ← ← ← ← ← ← ← (FastAPI + Infrastructure)
```

### Dependências WhatsApp (Node.js)

```
whatsapp-web.js → puppeteer → chromium
Express → http
qrcode → canvas (optional)
```

---

## 5. Módulos Existentes vs Blueprint

### Matriz de Cobertura

| # | Módulo Blueprint | Status | Arquivos | Avaliação |
|---|------------------|--------|----------|-----------|
| M01 | Dashboard | ❌ NÃO EXISTE | 0 | Precisa criar do zero |
| M02 | Pedidos | ✅ EXISTE | 6 | Domain + App + Infra + API |
| M03 | Clientes | ⚠️ PARCIAL | 6 | Falta: tipos, CPF/CNPJ, múltiplos endereços |
| M04 | WhatsApp | ⚠️ PARCIAL | 12+5 | Service pronto, bot no Python, bridge básico |
| M05 | CRM | ❌ NÃO EXISTE | 0 | Precisa criar pipeline + tags + notas |
| M06 | Produtos | ⚠️ PARCIAL | 6 | Falta: SKU, categoria, custo, fornecedor |
| M07 | Estoque | ❌ NÃO EXISTE | 0 | Só Product.estoque, sem InventoryMovement |
| M08 | Entregas | ❌ NÃO EXISTE | 0 | Só DeliveryDriver, sem Delivery entity |
| M09 | Motoristas | ⚠️ PARCIAL | 4 | DeliveryDriver existe, sem veículo/dashboard |
| M10 | Rotas | ❌ NÃO EXISTE | 0 | Precisa criar Route + RouteStop |
| M11 | Financeiro | ❌ NÃO EXISTE | 0 | Precisa criar Payment + Finance |
| M12 | Relatórios | ❌ NÃO EXISTE | 0 | Precisa criar dashboards |
| M13 | Inteligência | ❌ NÃO EXISTE | 0 | Precisa criar insights/alertas |
| — | Frontend | ❌ NÃO EXISTE | 0 | Nenhuma tela |
| — | Auth | ❌ NÃO EXISTE | 0 | Sem autenticação |

### Legenda
- ✅ **EXISTE** — Módulo implementado e funcional
- ⚠️ **PARCIAL** — Módulo existe mas incompleto
- ❌ **NÃO EXISTE** — Módulo não foi criado ainda

---

## 6. Banco de Dados

### Tabelas Backend (PostgreSQL/SQLite)

```sql
-- ✅ IMPLEMENTADO
clients (
    id INTEGER PRIMARY KEY,
    codigo VARCHAR UNIQUE NOT NULL,    -- Código permanente 000001
    nome VARCHAR NOT NULL,
    telefone VARCHAR NOT NULL,
    telefone_secundario VARCHAR,
    rua VARCHAR NOT NULL,
    numero VARCHAR NOT NULL,
    complemento VARCHAR,
    referencia VARCHAR,
    bairro VARCHAR NOT NULL,
    observacoes VARCHAR,
    ativo BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
)

products (
    id INTEGER PRIMARY KEY,
    codigo VARCHAR UNIQUE NOT NULL,
    nome VARCHAR NOT NULL,
    tipo VARCHAR NOT NULL,             -- GAS / AGUA
    preco FLOAT NOT NULL,
    estoque INTEGER DEFAULT 0,
    ativo BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
)

orders (
    id INTEGER PRIMARY KEY,
    codigo VARCHAR UNIQUE NOT NULL,
    client_codigo VARCHAR NOT NULL,
    product VARCHAR NOT NULL,          -- Product codigo
    quantity INTEGER DEFAULT 1,
    value FLOAT DEFAULT 0.0,
    address_snapshot VARCHAR,
    status VARCHAR DEFAULT 'PENDING',
    payment_method VARCHAR,
    delivery_driver_codigo VARCHAR,
    created_at DATETIME
)

delivery_drivers (
    id INTEGER PRIMARY KEY,
    codigo VARCHAR UNIQUE NOT NULL,
    nome VARCHAR NOT NULL,
    telefone VARCHAR NOT NULL,
    placa VARCHAR,
    ativo BOOLEAN DEFAULT TRUE,
    created_at DATETIME
)
```

### Tabelas WhatsApp (SQLite)

```sql
-- ✅ IMPLEMENTADO
contacts (id, phone, jid, name, push_name, business_name, is_business, is_group, ...)
lists (id, name, description, ...)
list_contacts (list_id, contact_id, ...)
customers (id, contact_id, customer_status, ...)
contact_preferences (customer_id, marketing_status, source, ...)
campaigns (id, name, message, list_id, status, protection, ...)
campaign_recipients (campaign_id, customer_id, status, attempts, ...)
whatsapp_conversations (id, phone_number, client_codigo, status, last_message, ...)
whatsapp_messages (id, conversation_id, direction, message_type, content, ...)
```

### Tabelas FALTANTES (Blueprint)

```sql
-- ❌ NÃO IMPLEMENTADO

-- M03 - Clientes (expansão)
addresses (
    id, customer_id, label, rua, numero, complemento, referencia, bairro,
    latitude, longitude, is_primary, created_at
)
customer_tags (customer_id, tag_id, ...)
customer_notes (id, customer_id, content, author, created_at)

-- M02 - Pedidos (expansão)
order_items (
    id, order_id, product_id, quantity, unit_price, subtotal, discount
)

-- M06 - Produtos (expansão)
product_categories (id, name, description, ...)
product_suppliers (id, name, phone, email, ...)

-- M07 - Estoque
inventory_movements (
    id, product_id, type, quantity, reference, notes, created_by, created_at
)
-- type: ENTRADA, SAIDA, AJUSTE, DEVOLUCAO, TRANSFERENCIA, RESERVA

-- M08 - Entregas
vehicles (id, plate, model, year, capacity, driver_id, ...)
deliveries (
    id, order_id, driver_id, vehicle_id, route_id, status,
    eta, proof_photo, proof_signature, notes, started_at, completed_at
)

-- M10 - Rotas
routes (id, driver_id, vehicle_id, status, total_distance, started_at, completed_at)
route_stops (id, route_id, order_id, stop_order, latitude, longitude, status, eta)

-- M11 - Financeiro
payments (
    id, order_id, amount, method, status, reference, paid_at, created_at
)
financial_transactions (
    id, type, amount, description, category, reference, created_at
)
-- type: RECEITA, DESPESA

-- M13 - Segurança
users (id, email, password_hash, name, role, tenant_id, active, ...)
roles (id, name, permissions, ...)
audit_logs (id, user_id, action, entity, entity_id, payload, ip, created_at)

-- M05 - CRM
tags (id, name, color, ...)
tasks (id, customer_id, title, description, status, due_date, assigned_to, ...)
```

---

## 7. APIs Existentes

### Backend (FastAPI) — 18 endpoints

```
GET  /                                    → Root info
GET  /health                              → Health check
── Clients ──
GET  /clients/                            → List all
POST /clients/                            → Create
GET  /clients/{codigo}                    → Get by code
PUT  /clients/{codigo}                    → Update
PATCH /clients/{codigo}/disable           → Disable
── Orders ──
GET  /orders/                             → List (optional status filter)
POST /orders/                             → Create
GET  /orders/{codigo}                     → Get by code
PATCH /orders/{codigo}/status             → Update status
PATCH /orders/{codigo}/assign-driver      → Assign driver
── Products ──
GET  /products/                           → List all
POST /products/                           → Create
GET  /products/{codigo}                   → Get by code
PUT  /products/{codigo}                   → Update
PATCH /products/{codigo}/disable          → Disable
── Delivery ──
GET  /delivery-drivers/                   → List all
POST /delivery-drivers/                   → Create
GET  /delivery-drivers/{codigo}           → Get by code
PATCH /delivery-drivers/{codigo}/disable  → Disable
── WhatsApp (Bridge) ──
GET  /whatsapp/status                     → Session status
GET  /whatsapp/health                     → WhatsApp health
GET  /whatsapp/qr                         → QR Code
POST /whatsapp/start                      → Start session
POST /whatsapp/logout                     → Logout
GET  /whatsapp/contacts                   → List contacts
POST /whatsapp/contacts/sync              → Sync contacts
GET  /whatsapp/customers                  → List CRM customers
POST /whatsapp/customers/{id}/promote     → Promote contact
POST /whatsapp/customers/{id}/opt-in      → Opt-in
POST /whatsapp/customers/{id}/opt-out     → Opt-out
GET  /whatsapp/lists                      → List lists
POST /whatsapp/lists                      → Create list
POST /whatsapp/lists/seed                 → Seed lists
GET  /whatsapp/campaigns                  → List campaigns
POST /whatsapp/campaigns                  → Create campaign
POST /whatsapp/campaigns/{id}/start       → Start campaign
POST /whatsapp/campaigns/{id}/pause       → Pause campaign
POST /whatsapp/campaigns/{id}/cancel      → Cancel campaign
GET  /whatsapp/campaigns/{id}/results     → Campaign results
```

### WhatsApp (Node.js) — 20+ endpoints

```
GET  /api/health
GET  /api/whatsapp/status
GET  /api/whatsapp/qr
POST /api/whatsapp/start
POST /api/whatsapp/logout
GET  /api/whatsapp/health
POST /api/contacts/sync
POST /api/contacts/dedupe
GET  /api/contacts
GET  /api/contacts/:id
GET  /api/customers
GET  /api/customers/:id
POST /api/customers/:contactId/promote
PUT  /api/customers/:id/status
POST /api/customers/sync
POST /api/customers/:id/opt-in
POST /api/customers/:id/opt-out
GET  /api/lists
POST /api/lists
POST /api/lists/seed
GET  /api/lists/:id/contacts
POST /api/lists/:id/contacts/:contactId
DELETE /api/lists/:id/contacts/:contactId
GET  /api/lists/:id/customers
POST /api/lists/:id/customers/:customerId
DELETE /api/lists/:id/customers/:customerId
POST /api/lists/:id/sync
GET  /api/campaigns
POST /api/campaigns
GET  /api/campaigns/:id
POST /api/campaigns/:id/preview
POST /api/campaigns/:id/start
POST /api/campaigns/:id/pause
POST /api/campaigns/:id/cancel
GET  /api/campaigns/:id/recipients
GET  /api/campaigns/:id/results
GET  /connect                              → QR Code HTML page
```

---

## 8. Telas Existentes

| Tela | Status | Notas |
|------|--------|-------|
| WhatsApp Connect (QR) | ✅ | HTML inline em connect-page.ts |
| Dashboard | ❌ | Não existe |
| Pedidos | ❌ | Só API |
| Pedido detalhado | ❌ | Não existe |
| Clientes | ❌ | Só API |
| Cliente detalhado | ❌ | Não existe |
| WhatsApp | ❌ | Só API |
| Conversa | ❌ | Não existe |
| Entregas | ❌ | Não existe |
| Mapa | ❌ | Não existe |
| Motoristas | ❌ | Só API |
| Produtos | ❌ | Só API |
| Estoque | ❌ | Não existe |
| Financeiro | ❌ | Não existe |
| Relatórios | ❌ | Não existe |
| Configurações | ❌ | Não existe |

**Total: 1 tela (QR Code), 15 telas faltando**

---

## 9. Testes Existentes

| Tipo | Status | Arquivos |
|------|--------|----------|
| Backend Python (pytest) | ❌ NENHUM | 0 |
| WhatsApp Node.js (tsx test) | ⚠️ DIRETÓRIO EXISTE | 4 arquivos detectados |
| Frontend (vitest/jest) | ❌ NÃO EXISTE | 0 |

**Status: 🔴 CRÍTICO — Zero testes automatizados no backend**

---

## 10. Automação WhatsApp

### Funcionalidades Implementadas ✅

| Feature | Status | Arquivo |
|---------|--------|---------|
| Conexão via QR Code | ✅ | wwebjs-provider.ts |
| Sessão persistente (LocalAuth) | ✅ | wwebjs-provider.ts |
| Sincronização de contatos | ✅ | sync.ts |
| Deduplicação de contatos | ✅ | dedupe.ts |
| Listas de segmentação | ✅ | db.ts |
| CRM básico (customers) | ✅ | db.ts + routes.ts |
| Campanhas de broadcast | ✅ | routes.ts + broadcast.ts |
| Worker com rate limiting | ✅ | broadcast.ts |
| Proteção anti-spam | ✅ | broadcast.ts |
| Página QR Code (HTML) | ✅ | connect-page.ts |
| Health check | ✅ | routes.ts |
| Autenticação API key | ✅ | auth.ts |
| Bot de pedidos | ✅ | whatsapp_service.py (Python) |
| Provider pattern | ✅ | provider/types.ts |

### O que NÃO existe na automação

| Feature | Status | Prioridade |
|---------|--------|------------|
| Transcrição de áudio | ❌ | Média |
| Mídia (fotos, docs) | ❌ | Média |
| Templates de mensagem | ❌ | Baixa |
| Webhooks configuráveis | ❌ | Baixa |
| Múltiplas contas WhatsApp | ❌ | Baixa |
| Integração direta com banco Python | ⚠️ | Alta (via bridge) |

---

## 11. Diagramas de Arquitetura

### 11.1 Arquitetura Atual

```
┌─────────────────────────────────────────────────────────────┐
│                        GASFLOW                              │
├─────────────────────┬───────────────────────────────────────┤
│                     │                                       │
│   FRONTEND          │           BACKEND                      │
│   (NÃO EXISTE)      │                                       │
│                     │   ┌─────────────────────────────┐     │
│                     │   │      FastAPI (Python)        │     │
│                     │   │  ┌──────────────────────┐   │     │
│                     │   │  │     Presentation      │   │     │
│                     │   │  │  API Routes+Schemas   │   │     │
│                     │   │  └──────────┬───────────┘   │     │
│                     │   │             │                │     │
│                     │   │  ┌──────────▼───────────┐   │     │
│                     │   │  │     Application       │   │     │
│                     │   │  │     Use Cases         │   │     │
│                     │   │  └──────────┬───────────┘   │     │
│                     │   │             │                │     │
│                     │   │  ┌──────────▼───────────┐   │     │
│                     │   │  │      Domain           │   │     │
│                     │   │  │  Entities+Interfaces  │   │     │
│                     │   │  └──────────────────────┘   │     │
│                     │   │             │                │     │
│                     │   │  ┌──────────▼───────────┐   │     │
│                     │   │  │   Infrastructure      │   │     │
│                     │   │  │  SQLAlchemy+Repos     │   │     │
│                     │   │  └──────────┬───────────┘   │     │
│                     │   └─────────────┼───────────────┘     │
│                     │                 │                      │
│                     │   ┌─────────────▼───────────────┐     │
│                     │   │      WhatsApp Service        │     │
│                     │   │      (Node.js/TS)            │     │
│                     │   │  ┌─────────────────────┐    │     │
│                     │   │  │  Provider (wwebjs)   │    │     │
│                     │   │  └──────────┬──────────┘    │     │
│                     │   └─────────────┼───────────────┘     │
│                     │                 │                      │
├─────────────────────┴─────────────────┼─────────────────────┤
│                                       │                      │
│              ┌────────────────────────▼──────────────────┐  │
│              │              PostgreSQL                    │  │
│              │  (Backend) + SQLite (WhatsApp)             │  │
│              └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 11.2 Arquitetura Alvo (Blueprint)

```
┌─────────────────────────────────────────────────────────────┐
│                        GASFLOW                              │
├──────────────────┬──────────────────────┬───────────────────┤
│                  │                      │                   │
│   FRONTEND       │       API            │     WORKERS       │
│   React/Vite     │    FastAPI           │    BullMQ         │
│   Tailwind       │                      │                   │
│   shadcn/ui      │   ┌──────────┐      │   ┌──────────┐   │
│                  │   │ customers│      │   │ WhatsApp  │   │
│   ┌──────────┐   │   │ orders   │      │   │ Inventory │   │
│   │Dashboard │   │   │ products │      │   │ Delivery  │   │
│   │Pedidos   │   │   │inventory │      │   │ Finance   │   │
│   │Clientes  │   │   │deliveries│      │   │ Reports   │   │
│   │WhatsApp  │   │   │ drivers  │      │   └──────────┘   │
│   │Entregas  │   │   │ routes   │      │                   │
│   │Motoristas│   │   │ whatsapp │      │                   │
│   │Produtos  │   │   │ payments │      │                   │
│   │Estoque   │   │   │ finance  │      │                   │
│   │Financeiro│   │   │ reports  │      │                   │
│   │Relatórios│   │   │intellig. │      │                   │
│   │Inteligên.│   │   └──────────┘      │                   │
│   │Config    │   │         │            │                   │
│   └──────────┘   │         │            │                   │
│                  │         │            │                   │
├──────────────────┴─────────┼────────────┴───────────────────┤
│                            │                                 │
│         ┌──────────────────▼──────────────────┐             │
│         │           PostgreSQL                 │             │
│         │           Redis                      │             │
│         │           Storage                    │             │
│         └──────────────────────────────────────┘             │
│                                                              │
│         ┌──────────────────────────────────────┐             │
│         │        Event / Audit Layer            │             │
│         └──────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### 11.3 Fluxo Principal

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  CLIENTE  │───▶│ WhatsApp │───▶│ GASFLOW  │───▶│ PEDIDO   │
└──────────┘    │ Telefone │    │ Identif. │    │ Criado   │
                │ Web      │    │ Cliente  │    └────┬─────┘
                │ Balcão   │    │ Interp.  │         │
                └──────────┘    └──────────┘         ▼
                                              ┌──────────┐
                                              │VALIDAÇÃO │
                                              └────┬─────┘
                                                   │
                                        ┌──────────▼──────────┐
                                        │     PAGAMENTO       │
                                        └──────────┬──────────┘
                                                   │
                                        ┌──────────▼──────────┐
                                        │      DESPACHO       │
                                        └──────────┬──────────┘
                                                   │
                                        ┌──────────▼──────────┐
                                        │    ROTA + MOTORISTA  │
                                        └──────────┬──────────┘
                                                   │
                                        ┌──────────▼──────────┐
                                        │      ENTREGA        │
                                        └──────────┬──────────┘
                                                   │
                              ┌─────────────────────┼─────────────────────┐
                              │                     │                     │
                    ┌─────────▼─────────┐ ┌─────────▼─────────┐ ┌─────────▼─────────┐
                    │     ESTOQUE       │ │    FINANCEIRO     │ │       CRM         │
                    └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
                              │                     │                     │
                              └─────────────────────┼─────────────────────┘
                                                    │
                                         ┌──────────▼──────────┐
                                         │    INTELIGÊNCIA     │
                                         └─────────────────────┘
```

---

## 12. Decisões de Design

### Decisão 1: Manter Python/FastAPI (não migrar para Node.js)

**Decisão:** Manter o backend em Python/FastAPI.

**Justificativa:**
- O backend Python já está funcional e bem estruturado (DDD)
- FastAPI é performático e moderno (async, auto-docs)
- SQLAlchemy é maduro e confiável
- Pydantic v2 é rápido e tipado
- Migrar para Node.js/Fastify quebraria código funcional (Regra Zero)

**Trade-off:**
- Blueprint sugere Node.js/TypeScript/Fastify
- Mas: "NÃO migre automaticamente se o projeto existente já possuir arquitetura funcional"
- Python é mais lento que Node.js em I/O, mas para esta operação é suficiente

### Decisão 2: WhatsApp como Service separado

**Decisão:** Manter WhatsApp como microservice Node.js separado.

**Justificativa:**
- whatsapp-web.js só funciona com Node.js (puppeteer)
- Já está funcional e testado
- Bridge via HTTP (FastAPI → WhatsApp) é limpo e desacoplado
- Provider pattern permite trocar implementação futuramente

**Trade-off:**
- Dois backends = mais complexidade operacional
- Mas: Docker Compose resolve isso facilmente

### Decisão 3: SQLite para WhatsApp

**Decisão:** Manter SQLite para dados do WhatsApp.

**Justificativa:**
- whatsapp-web.js usa SQLite nativamente
- Dados de contatos/campanhas não precisam de PostgreSQL
- Mais simples para deploy
- Sincronização via API bridge

**Trade-off:**
- Não escala para múltiplas instâncias
- Mas: para revenda de gás, é suficiente

### Decisão 4: DDD com 4 camadas

**Decisão:** Manter arquitetura DDD com domain/application/infrastructure/presentation.

**Justificativa:**
- Separação clara de responsabilidades
- Domain puro (sem dependências externas)
- Testabilidade (cada camada pode ser testada isoladamente)
- Facilita manutenção e evolução

**Trade-off:**
- Mais arquivos que arquitetura em camadas tradicional
- Mas: benefícios de manutenção superam custo inicial

### Decisão 5: Códigos permanentes (000001)

**Decisão:** Manter sistema de códigos permanentes para clientes/pedidos.

**Justificativa:**
- Regra de negócio específica do Marcos Gás
- Código nunca muda, mesmo com mudanças de telefone/endereço
- Formato: 6 dígitos sequenciais
- Facilita identificação rápida

### Decisão 6: Bot de pedidos no Python

**Decisão:** Bot de pedidos via WhatsApp fica no backend Python, não no Node.js.

**Justificativa:**
- Bot precisa acessar banco de pedidos (PostgreSQL)
- Python já tem acesso direto ao banco
- Node.js só sincroniza contatos/campanhas

**Trade-off:**
- Bridge HTTP adiciona latência
- Mas: para operação de revenda, é desprezível

---

## 13. Riscos Detalhados

| # | Risco | Severidade | Probabilidade | Impacto | Mitigação |
|---|-------|------------|---------------|---------|-----------|
| R1 | Sem autenticação | 🔴 Alta | Alta | Qualquer um acessa API | Implementar JWT + RBAC |
| R2 | Sem testes | 🔴 Alta | Alta | Bugs em produção | Criar testes antes de features |
| R3 | Sem frontend | 🔴 Alta | Alta | Não há UI para usar | Criar React/Vite/Tailwind |
| R4 | SQLite WhatsApp não escala | 🟡 Média | Baixa | Multi-instance quebra | Manter para MVP |
| R5 | Dois backends | 🟡 Média | Baixa | Complexidade operacional | Docker Compose resolve |
| R6 | Sem audit logs | 🟡 Média | Média | Não rastreia operações | Implementar antes de prod |
| R7 | Sem rate limiting | 🟡 Média | Média | Abuso de API | Implementar com FastAPI |
| R8 | Config.py sem .env | 🟡 Média | Baixa | Hardcoded values | Adicionar load_dotenv |
| R9 | WhatsApp sem webhook verification | 🟡 Média | Baixa | Webhooks falsos | Implementar validação |
| R10 | Sem event sourcing | 🟢 Baixa | Baixa | Difícil rastrear mudanças | Fase avançada |

---

## 14. Débitos Técnicos

| # | Débito | Prioridade | Esforço | Arquivo |
|---|--------|------------|---------|---------|
| D1 | Sem autenticação/autorização | 🔴 Alta | Médio | Novo módulo |
| D2 | Sem testes automatizados | 🔴 Alta | Médio | tests/ |
| D3 | Sem frontend | 🔴 Alta | Grande | frontend/ |
| D4 | Config.py sem .env loading | 🟡 Média | Baixo | core/config.py |
| D5 | Sem validação webhook WhatsApp | 🟡 Média | Baixo | whatsapp bridge |
| D6 | WhatsApp SQLite ≠ PostgreSQL | 🟡 Média | Médio | whatsapp/db.ts |
| D7 | Sem rate limiting | 🟡 Média | Baixo | main.py |
| D8 | Sem CORS production config | 🟡 Média | Baixo | main.py |
| D9 | __init__.py vazios (5 arquivos) | 🟢 Baixa | Baixo | infrastructure/ |
| D10 | Sem event sourcing | 🟢 Baixa | Grande | Novo módulo |

---

## 15. Matriz de Gaps (Recalibrada)

| Área | Atual | Alvo | Gap | Ação | Prioridade | Fase |
|------|-------|------|-----|------|------------|------|
| **Frontend** | Nada | React/Vite/Tailwind/shadcn | 🔴 CRÍTICO | Criar do zero | MÁXIMA | 1 |
| **Auth** | Nada | JWT + RBAC | 🔴 CRÍTICO | Implementar | MÁXIMA | 1 |
| **Design System** | Nada | shadcn/ui components | 🔴 CRÍTICO | Criar base | MÁXIMA | 1 |
| **Dashboard** | Nada | KPIs + Charts | 🔴 CRÍTICO | Criar | ALTA | 2 |
| **Pedidos (expandir)** | API básica | Itens + Desconto + Taxa | 🟡 MÉDIO | Expandir | ALTA | 3 |
| **Clientes (expandir)** | API básica | Tipos + CPF + Endereços | 🟡 MÉDIO | Expandir | ALTA | 3 |
| **WhatsApp (integrar)** | Bridge básico | Bot + Campanhas | 🟡 MÉDIO | Integrar | MÉDIA | 4 |
| **Estoque** | Product.estoque | InventoryMovements | 🔴 CRÍTICO | Criar módulo | ALTA | 5 |
| **Entregas** | DeliveryDriver | Delivery + Vehicle | 🔴 CRÍTICO | Criar módulos | ALTA | 6 |
| **Rotas** | Nada | Route + Stops | 🔴 CRÍTICO | Criar módulo | MÉDIA | 7 |
| **Financeiro** | Nada | Payments + Finance | 🔴 CRÍTICO | Criar módulo | MÉDIA | 8 |
| **Relatórios** | Nada | Dashboards | 🟡 MÉDIO | Criar módulo | MÉDIA | 9 |
| **Inteligência** | Nada | Insights + Alerts | 🟢 BAIXO | Criar módulo | BAIXA | 10 |
| **Testes** | 0 | 80%+ coverage | 🔴 CRÍTICO | Criar testes | MÁXIMA | contínuo |
| **Docker (prod)** | Dev | Produção-ready | 🟡 MÉDIO | Otimizar | MÉDIA | 12 |
| **CI/CD** | Nada | GitHub Actions | 🟡 MÉDIO | Configurar | MÉDIA | 12 |
| **Logs** | print() | Structured logging | 🟡 MÉDIO | Implementar | MÉDIA | 12 |

---

## 16. Código Morto / Inútil

| Arquivo | Status | Ação | Justificativa |
|---------|--------|------|---------------|
| backend/app/utils/__init__.py | ❌ Vazio | Remover | Não tem conteúdo |
| backend/app/core/__init__.py | ⚠️ Vazio | Manter | Marker de pacote |

**Total: 1 arquivo morto (utils/__init__.py)**

---

## 17. Incompatibilidades com Blueprint

| Blueprint Item | Status Atual | Compatível? | Ação |
|----------------|--------------|-------------|------|
| Stack: Node.js/TypeScript/Fastify | Python/FastAPI | ⚠️ Diferente | Manter Python (funcional) |
| Stack: React/Vite/Tailwind/shadcn | Nada | ❌ Incompatível | Criar frontend |
| Redis | Nada | ⚠️ Ausente | Adicionar quando necessário |
| BullMQ | Nada | ⚠️ Ausente | Adicionar quando necessário |
| WebSocket | Nada | ⚠️ Ausente | Adicionar para real-time |
| Multi-tenant | Nada | ⚠️ Ausente | Adicionar após MVP |
| RBAC | Nada | ❌ Incompatível | Implementar antes de produção |
| Event sourcing | Nada | ⚠️ Ausente | Fase avançada |
| Audit logs | Nada | ❌ Incompatível | Implementar antes de produção |
| API versioning (/v1/) | Nada | ⚠️ Ausente | Adicionar |

---

## 18. Resumo Executivo

### O que EXISTE e FUNCIONA ✅

| Componente | Status | Notas |
|------------|--------|-------|
| Backend Python/FastAPI | ✅ Sólido | DDD implementado |
| Domain Entities | ✅ Sólido | 5 domínios com validações |
| Use Cases | ✅ Sólido | 22 use cases |
| Repository Pattern | ✅ Sólido | Interfaces + Implementações |
| SQLAlchemy Models | ✅ Sólido | 4 tabelas backend |
| API Endpoints | ✅ Sólido | 18+ endpoints |
| WhatsApp Service | ✅ Sólido | Provider pattern |
| WhatsApp Bot | ✅ Sólido | Bot de pedidos |
| Docker Compose | ✅ Funcional | 3 serviços |

### O que FALTA (CRÍTICO) 🔴

| Componente | Status | Impacto |
|------------|--------|---------|
| Frontend (React) | ❌ NÃO EXISTE | Sistema sem UI |
| Autenticação | ❌ NÃO EXISTE | Segurança comprometida |
| Testes | ❌ NENHUM | Qualidade comprometida |
| Dashboard | ❌ NÃO EXISTE | Sem visão operacional |
| Estoque (módulo) | ❌ NÃO EXISTE | Controle incompleto |
| Entregas (módulo) | ❌ NÃO EXISTE | Logística incompleta |
| Financeiro | ❌ NÃO EXISTE | Sem controle financeiro |

### O que está PARCIAL ⚠️

| Componente | Status | O que falta |
|------------|--------|-------------|
| Clientes | ⚠️ PARCIAL | Tipos, CPF/CNPJ, múltiplos endereços |
| Produtos | ⚠️ PARCIAL | SKU, categoria, custo, fornecedor |
| Motoristas | ⚠️ PARCIAL | Veículo, dashboard |
| WhatsApp | ⚠️ PARCIAL | Integração profunda com backend |

---

## 19. Plano de Implementação

### FASE 1 — Arquitetura + Design System + Auth
**Status:** NÃO INICIADO
**Duração estimada:** 2-3 dias
**Ações:**
1. Criar frontend React/Vite/Tailwind/shadcn
2. Implementar autenticação JWT no backend
3. Criar Design System (componentes base)
4. Configurar RBAC básico
5. Adicionar testes unitários para domínios

### FASE 2 — Application Shell + Dashboard
**Status:** NÃO INICIADO
**Duração estimada:** 1-2 dias
**Ações:**
1. Criar shell da aplicação (sidebar, routing)
2. Implementar Dashboard com KPIs
3. Conectar frontend ao backend

### FASE 3 — Clientes + Produtos
**Status:** NÃO INICIADO
**Duração estimada:** 2-3 dias
**Ações:**
1. Expandir API de clientes (tipos, endereços, tags)
2. Expandir API de produtos (SKU, categorias, fornecedores)
3. Criar telas de CRUD no frontend

### FASE 4 — Pedidos + WhatsApp
**Status:** NÃO INICIADO
**Duração estimada:** 3-4 dias
**Ações:**
1. Expandir pedidos (itens múltiplos, desconto, taxa)
2. Integrar WhatsApp bot com backend
3. Criar telas de pedidos

### FASE 5 — Estoque
**Status:** NÃO INICIADO
**Duração estimada:** 2 dias
**Ações:**
1. Criar módulo InventoryMovement
2. Controlar entradas/saídas/ajustes
3. Criar telas de estoque

### FASE 6 — Entregas + Motoristas
**Status:** NÃO INICIADO
**Duração estimada:** 3-4 dias
**Ações:**
1. Criar entidade Delivery
2. Criar entidade Vehicle
3. Expandir motoristas

### FASE 7 — Rotas
**Status:** NÃO INICIADO
**Duração estimada:** 2-3 dias
**Ações:**
1. Criar entidade Route
2. Criar entidade RouteStop
3. Integração com mapas

### FASE 8 — Financeiro
**Status:** NÃO INICIADO
**Duração estimada:** 2-3 dias
**Ações:**
1. Criar módulo Payments
2. Criar módulo Finance
3. Contas a receber/pagar

### FASE 9 — Relatórios
**Status:** NÃO INICIADO
**Duração estimada:** 2 dias
**Ações:**
1. Dashboards de vendas
2. Dashboards operacionais
3. Exportação

### FASE 10 — Inteligência
**Status:** NÃO INICIADO
**Duração estimada:** 2-3 dias
**Ações:**
1. Previsão de demanda
2. Alertas automáticos
3. Insights

### FASE 11 — Automação
**Status:** NÃO INICIADO
**Duração estimada:** 1-2 dias
**Ações:**
1. Automações avançadas
2. Webhooks
3. Integrações

### FASE 12 — Hardening + Deploy
**Status:** NÃO INICIADO
**Duração estimada:** 2-3 dias
**Ações:**
1. Testes completos
2. Segurança
3. Deploy produção
4. CI/CD
5. Monitoramento

---

## 20. Critérios de Sucesso

### FASE 0 (Esta auditoria)
- ✅ Árvore do repositório mapeada
- ✅ Stack detectada
- ✅ Arquitetura atual documentada
- ✅ Módulos existentes identificados
- ✅ Banco de dados documentado
- ✅ APIs existentes listadas
- ✅ Telas existentes listadas
- ✅ Testes existentes listados
- ✅ Dependências analisadas
- ✅ WhatsApp documentado
- ✅ Riscos identificados
- ✅ Duplicações identificadas
- ✅ Código morto identificado
- ✅ Débitos técnicos listados
- ✅ Incompatibilidades mapeadas
- ✅ Diagramas criados
- ✅ Decisões de design documentadas
- ✅ Matriz de gaps recalibrada

### Próxima fase (FASE 1)
- Frontend React criado e funcionando
- Autenticação JWT implementada
- Design System com componentes base
- Testes unitários para domínios
- typecheck passando sem erros

---

**Documento produzido por:** Buffy (Codebuff)
**Data:** 26/08/2026
**Status:** FASE 0 COMPLETA ✅
**Próximo passo:** FASE 1 — Arquitetura + Design System + Auth
