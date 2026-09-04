# GasFlow

Sistema operacional para depósitos de gás e água.

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
- ✅ WhatsApp Automation (whatsapp-web.js)
  - Conexão via QR Code
  - Gerenciamento de contatos
  - Listas de segmentação
  - CRM de clientes
  - Campanhas de broadcast

## Fluxo Principal

```
Cliente → Pedido → Entrega → Histórico
```

## Fluxo WhatsApp

```
Mensagem → Bot → Banco de Dados → Pedido
```

## Stack

### Backend (Python)
- FastAPI
- SQLAlchemy
- PostgreSQL
- Pydantic

### WhatsApp (Node.js)
- whatsapp-web.js
- Express
- SQLite (contatos/listas/campanhas)

## Setup

### Pré-requisitos
- Docker + Docker Compose
- OU Python 3.12+ e Node.js 20+

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


### Serviços

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

### Typecheck

```bash
# Backend
cd backend && python -m mypy app/

# WhatsApp
cd whatsapp && npm run typecheck
```

### Testes

```bash
# Backend
cd backend && python -m pytest -q          # ruff check app tests

# Frontend
cd frontend && npm test                     # npx tsc --noEmit

# WhatsApp
cd whatsapp && npm test

# E2E (stack completo real em Docker — ver docs/phase15/E2E.md)
docker compose -f docker-compose.e2e.yml up -d --build
cd e2e && npm ci && npx playwright install chromium && npx playwright test
```

## Licença

Projeto privado — GasFlow
