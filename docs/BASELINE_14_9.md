# BASELINE 14.9 — Auditoria Obrigatória do GasFlow

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).


**Data:** 2026-08-29
**Branch:** `main`
**HEAD:** `45f4bca` feat(delivery): database persistence, GPS tracking, outbox, and driver app enhancements
**Commits ahead of origin:** 1

---

## 1. Arquitetura Real

| Camada | Tecnologia | Status |
|--------|-----------|--------|
| Backend | FastAPI + SQLAlchemy + DDD | ✅ Funcional |
| Frontend | React 19 + Vite + TypeScript + Tailwind | ⚠️ Build falha |
| WhatsApp | whatsapp-web.js + Express + TypeScript | ⚠️ Typecheck falha |
| Database | SQLite (dev) / PostgreSQL (prod Docker) | ✅ Funcional |
| Auth | In-memory (bcrypt + RBAC + sessions) | ✅ Funcional |
| Docker | docker-compose.yml (4 services) | ✅ Configurado |
| CI/CD | Nenhum | ❌ Não existe |
| Android | Nenhum | ❌ Não existe |

### Diretórios Principais
- `backend/app/` — Domain, Application, Infrastructure, Presentation (DDD)
- `frontend/src/features/` — 16 módulos (dashboard, orders, customers, products, inventory, finance, deliveries, drivers, driver, whatsapp, ai, intelligence, reports, settings, auth)
- `whatsapp/src/` — Server, routes, provider, db, broadcast, dedupe

---

## 2. Testes e Builds

### Backend (pytest)
```
835 passed, 4 failed — 66.88s
```
**Falhas:**
- `test_cross_tenant_isolation.py::TestClientIsolation::test_tenant_a_creates_client` — 409 Conflict (unique constraint global em `telefone`)
- `test_cross_tenant_isolation.py::TestClientIsolation::test_tenant_b_creates_client` — mesmo erro
- `test_tenant_isolation.py::TestTenantFiltering::test_delivery_filtered_by_tenant` — `AttributeError: 'dict' object has no attribute 'tenant_id'`
- `test_tenant_isolation.py::TestTenantFiltering::test_create_and_read_client_tenant_scoped` — mesmo tipo de erro

**Causa raiz:** `ClientModel` tem `UniqueConstraint("telefone", name="uq_clients_telefone")` — globally unique, não por tenant. Dois tenants não podem criar clientes com mesmo telefone.

### Frontend
| Check | Resultado |
|-------|-----------|
| `npm run build` | ❌ FALHOU — 13 erros TypeScript |
| `npm run lint` | ❌ ESLint não instalado |
| `npm run test` | ✅ 37/37 pass |

**Erros TypeScript:**
- `DriverHomePage.tsx`: imports não usados (Phone, AlertTriangle, History, User, ChevronRight), variável `profile` não usada
- `DriversPage.tsx`: import `Clock` não usado, `statusConfig` possivelmente undefined (x3), `age_seconds` não existe no tipo

### WhatsApp
| Check | Resultado |
|-------|-----------|
| `npm test` | ✅ 38/38 pass |
| `npx tsc --noEmit` | ❌ FALHOU — `Cannot find name 'listSentMessages'` em routes.ts:272 |

---

## 3. Banco de Dados

### Engine
- **Dev:** SQLite com WAL mode + FK enforcement
- **Prod (Docker):** PostgreSQL 16 Alpine

### Tabelas (models SQLAlchemy)

| Tabela | Model | tenant_id | Unique Constraints | Índices |
|--------|-------|-----------|-------------------|---------|
| `clients` | ClientModel | ✅ | `(tenant_id, codigo)`, **`telefone` (GLOBAL!)** | telefone, tipo, ativo, email |
| `orders` | OrderModel | ✅ | `(tenant_id, codigo)` | codigo, client_codigo |
| `order_items` | OrderItemModel | — | — | — |
| `products` | ProductModel | ✅ | `(tenant_id, codigo)` | — |
| `delivery_drivers` | DeliveryDriverModel | ✅ | `(tenant_id, codigo)` | codigo |
| `inventory` | InventoryModel | ✅ | `(tenant_id, product_codigo)` | product_codigo |
| `stock_movements` | StockMovementModel | — | `(reference_type, reference_id, product_codigo, type)` | product, created, reference |
| `payments` | PaymentModel | ✅ | `idempotency_key` unique | order, status, created |
| `receivables` | ReceivableModel | ✅ | — | customer, order, status, due_date |
| `expenses` | ExpenseModel | ✅ | — | category, date, status |
| `cash_movements` | CashMovementModel | ✅ | — | type, created, reference |
| `financial_ledger` | FinancialLedgerModel | ✅ | — | event_type, created, reference |
| `whatsapp_conversations` | WhatsAppConversationModel | ✅ | `(account_id, phone_number)` | status |
| `whatsapp_messages` | WhatsAppMessageModel | — | `provider_message_id` unique | conversation+created |
| `delivery_records` | DeliveryRecord | ✅ | `(tenant_id, idempotency_key)` | tenant+status, tenant+driver, order |
| `driver_locations` | DriverLocationRecord | ✅ | — | tenant+driver |
| `outbox_entries` | OutboxEntry | ✅ | — | status+created, tenant |
| `vehicles` | VehicleModel | ✅ | — | — |
| `vehicle_capacities` | VehicleCapacityModel | — | — | — |
| `vehicle_loads` | VehicleLoadModel | — | — | — |

### BUG CRÍTICO: Unique Constraint Global
- `ClientModel`: `UniqueConstraint("telefone", name="uq_clients_telefone")` é **global**, não por tenant
- Dois tenants não podem criar clientes com o mesmo telefone → 409 Conflict
- **Impacto:** Multi-tenancy quebrado para clientes com telefone duplicado entre filiais

### Migrações
- Apenas 1 migration: `a074610b4bbb_initial_schema.py`
- Auto-create via `init_db()` no startup (Base.metadata.create_all)

---

## 4. Multi-Tenancy

### Implementação
- `TenantMixin` em repositories filtra por `tenant_id`
- `TenantContext` extraído do token JWT via `get_tenant_context()`
- Todos os models principais têm coluna `tenant_id`

### Testes de Isolamento
| Teste | Resultado |
|-------|-----------|
| Client creation per tenant | ❌ FALHA (unique constraint global) |
| Delivery filtering per tenant | ❌ FALHA (dict vs object mismatch) |
| Cross-tenant isolation (outros) | ✅ Passa |

### Problemas
1. **`telefone` unique é global** — FALHA de isolamento
2. **`delivery_ops.py:111`** — `d.tenant_id` em dict (não object) → crash
3. **Auth service é in-memory** — dados de autenticação perdem-se no restart

---

## 5. Frontend — Rotas e Telas

| Rota | Componente | Status |
|------|-----------|--------|
| `/login` | LoginPage | ✅ Funcional |
| `/driver/login` | DriverLoginPage | ✅ Funcional |
| `/driver` | DriverHomePage | ⚠️ TS errors |
| `/` | DashboardPage | ✅ Funcional |
| `/orders` | OrdersPage | ✅ Funcional |
| `/orders/new` | OrderFormPage | ✅ Funcional |
| `/orders/:codigo` | OrderDetailPage | ✅ Funcional |
| `/customers` | CustomersPage | ✅ Funcional |
| `/customers/new` | CustomerFormPage | ✅ Funcional |
| `/customers/:codigo` | CustomerDetailPage | ✅ Funcional |
| `/products` | ProductsPage | ✅ Funcional |
| `/products/new` | ProductFormPage | ✅ Funcional |
| `/products/:codigo` | ProductDetailPage | ✅ Funcional |
| `/whatsapp` | WhatsAppPage | ✅ Funcional |
| `/deliveries` | DeliveriesPage | ✅ Funcional |
| `/drivers` | DriversPage | ⚠️ TS errors |
| `/inventory` | InventoryPage | ✅ Funcional |
| `/inventory/:productCodigo` | InventoryDetailPage | ✅ Funcional |
| `/finance` | FinancePage | ✅ Funcional |
| `/reports` | ReportsPage | ✅ Funcional |
| `/intelligence` | IntelligencePage | ✅ Funcional |
| `/settings` | SettingsPage | ✅ Funcional |

---

## 6. API — Endpoints

### Backend API (22 routers registrados)

| Router | Prefixo | Auth | Tenant | Status |
|--------|---------|------|--------|--------|
| health | `/health` | ❌ público | ❌ | ✅ |
| auth | `/auth` | ❌ login público | ❌ | ✅ |
| clients | `/clients` | ✅ | ✅ | ⚠️ unique bug |
| orders | `/orders` | ✅ | ✅ | ✅ |
| products | `/products` | ✅ | ✅ | ✅ |
| inventory | `/inventory` | ✅ | ✅ | ✅ |
| finance | `/finance` | ✅ | ✅ | ✅ |
| payments | `/payments` | ✅ | ✅ | ✅ |
| delivery | `/delivery-drivers` | ✅ | ✅ | ✅ |
| delivery_ops | `/delivery` | ✅ | ⚠️ | ⚠️ dict bug |
| dispatch | `/delivery/dispatch` | ✅ | ⚠️ | ⚠️ in-memory |
| whatsapp | `/whatsapp` | ✅ | ✅ | ✅ |
| whatsapp_gateway | `/whatsapp/gateway` | API key | ✅ | ✅ |
| ai | `/ai` | ✅ | ✅ | ⚠️ mock |
| audio | `/audio` | ✅ | ✅ | ⚠️ mock |
| automation | `/automation` | ✅ | ✅ | ⚠️ mock |
| driver_api | `/api/driver` | driver auth | ✅ | ✅ |
| driver_v1 | `/api/v1/driver` | driver auth | ✅ | ✅ |
| printer | `/printer` | ✅ | — | ✅ |
| reports | `/reports` | ✅ | — | ✅ |
| operations | `/operations` | — | — | ⚠️ in-memory |
| communication | `/communication` | — | — | ✅ |

### Observações
- **Duplicação:** Routers registrados tanto no root (`/`) quanto em `/api/v1/`
- **In-memory stores:** `driver_api.py`, `delivery_ops.py`, `dispatch.py`, `operations.py` ainda usam `shared_store` (dict em memória)
- **Mocks em produção:** `ai.py`, `audio.py`, `whatsapp_gateway.py` importam `MockLLMProvider`/`MockSTTProvider` — sem feature flag para desativar

---

## 7. Dívida Técnica

### Crítico
| Item | Local | Descrição |
|------|-------|-----------|
| Admin password default | `config.py:25,67` | `admin123` como default em 2 lugares |
| Unique constraint global | `client_model.py` | `telefone` único global, não por tenant |
| Auth in-memory | `auth_service.py` | Todos os dados de auth em dict Python |

### Alto
| Item | Local | Descrição |
|------|-------|-----------|
| In-memory stores | shared_store.py, delivery_ops, driver_api, dispatch, operations | Dados se perdem no restart |
| Frontend build quebrado | DriversPage.tsx, DriverHomePage.tsx | 13 erros TypeScript |
| WhatsApp typecheck quebrado | routes.ts:272 | `listSentMessages` não definido |
| delivery_ops dict bug | delivery_ops.py:111 | `d.tenant_id` em dict, não object |
| Mocks sem feature flag | ai.py, audio.py | MockLLMProvider importado direto |

### Médio
| Item | Local | Descrição |
|------|-------|-----------|
| `except Exception` genérico | 46 ocorrências em backend | Catch-all pode mascarar erros |
| `datetime.utcnow()` deprecated | Vários arquivos | Python 3.14 deprecation warning |
| ESLint não instalado | Frontend | `npm run lint` falha |
| Sem CI/CD | Repositório | Nenhum GitHub Actions |
| Sem docker-compose.prod.yml | Raiz | Apenas compose para dev |
| Sem LGPD | Backend | Nenhum endpoint de export/delete de dados |
| Sem coupon/cupom | Backend/Frontend | Módulo não existe ainda |
| Sem NFC-e | Backend | Nenhum código fiscal |
| Sem Android | Repositório | Nenhum app mobile |

### Baixo
| Item | Local | Descrição |
|------|-------|-----------|
| Product.estoque legacy | product_model.py | Campo ainda existe, Order não usa |
| 46 `pass` em domain interfaces | domain/ | Interface methods sem implementação |
| Deprecation warnings | whatsapp repositories, gateway | `utcnow()` sem timezone |
| CORS default origins | config.py | 10 localhost origins hardcoded |

---

## 8. Features Realmente Existentes vs Parciais vs Mock

| Feature | Status | Detalhes |
|---------|--------|----------|
| Auth + RBAC + Tenancy | ✅ Real | In-memory, mas funcional |
| Clientes CRUD + 360 | ✅ Real | Unique constraint bug |
| Pedidos CRUD | ✅ Real | Funcional |
| Produtos CRUD | ✅ Real | Funcional |
| Estoque (inventory + movements) | ✅ Real | Atomic, idempotente |
| Financeiro (payments, receivables, expenses, cash, ledger) | ✅ Real | Decimal, auditável |
| Entregadores (CRUD + login + delivery workflow) | ✅ Real | Mistura in-memory + DB |
| WhatsApp bot (conversas, pedidos, takeover) | ✅ Real | Funcional |
| WhatsApp gateway (backend ↔ whatsapp service) | ✅ Real | API key auth |
| Dashboard | ✅ Real | Chama endpoints reais |
| Relatórios | ✅ Real | Financeiro + entregas |
| Impressão ESC/POS | ✅ Real | Print agent funcional |
| Pagamentos (métodos, PIX config) | ✅ Real | CRUD funcional |
| Dispatch inteligente | ⚠️ Parcial | Lógica existe, dados in-memory |
| Roteirização VRP | ⚠️ Parcial | Estrutura existe, sem OR-Tools |
| WebSocket realtime | ✅ Real | Event bus + bridge |
| Outbox (event delivery) | ✅ Real | DB persistence |
| IA de texto (copilot) | ⚠️ Mock | MockLLMProvider, sem Ollama |
| IA de áudio (STT/TTS) | ⚠️ Mock | MockSTTProvider/TTSProvider |
| Automações | ⚠️ Mock | Workflow engine existe, sem provider real |
| CRM avançado | ✅ Real | Customer 360, segmentação |
| Campanhas WhatsApp | ⚠️ Parcial | Broadcast existe, sem rate limit |
| Cupom de desconto | ❌ Não existe | — |
| NFC-e | ❌ Não existe | — |
| App Android | ❌ Não existe | — |
| LGPD | ❌ Não existe | — |
| CI/CD | ❌ Não existe | — |
| docker-compose.prod.yml | ❌ Não existe | — |

---

## 9. Riscos Arquiteturais

| Risco | Nível | Mitigation |
|-------|-------|-----------|
| Auth in-memory → perde dados no restart | ALTO | Mover para DB (Fase 15) |
| In-memory stores → dados voláteis | ALTO | delivery_persistence_repository já existe, falta migrar driver_api/delivery_ops |
| Unique constraint global telefone | CRÍTICO | Corrigir para `(tenant_id, telefone)` |
| Frontend não builda | ALTO | Corrigir erros TypeScript (Fase 15) |
| Sem CI/CD | MÉDIO | Adicionar GitHub Actions (Fase 15) |
| Mocks sem flag | MÉDIO | Adicionar feature flags (Fase 16) |
| `except Exception` genérico | MÉDIO | Refinar por módulo |
| Segredo admin123 como default | ALTO | Falhar boot sem env var (Fase 15) |

---

## 10. Bloqueadores da Fase 15

### Itens que a Fase 15 planeja fazer mas já estão feitos:
- ✅ `requirements.txt` com dependências básicas (fastapi, sqlalchemy, bcrypt, etc.)
- ✅ Docker Compose com Postgres
- ✅ Health endpoint
- ✅ Security headers middleware
- ✅ Logging estruturado

### Itens que a Fase 15 precisa ajustar/corrigir:
1. **`admin123` como default** — Fase 15 quer remover; precisa implementar falha de boot sem segredo
2. **`docker-compose.prod.yml`** — Não existe; precisa criar
3. **LGPD** — Não existe; precisa criar endpoints de export/delete
4. **CI/CD** — Não existe; precisa criar GitHub Actions
5. **Frontend build quebrado** — Precisa corrigir antes de CI
6. **Unique constraint global** — Fase 15 pode corrigir como parte de "fundação técnica"

### Itens que mudaram de forma que invalida o plano original:
- A Fase 15 original assume auth em DB, mas auth ainda é in-memory — precisa incluir migração de auth para DB
- O `delivery_persistence_repository` já existe — não precisa criar do zero, só integrar ao driver_api

---

## 11. DECISÃO

**Baseline estabelecido. Parar aqui.**

- **Crítico:** 1 (unique constraint global)
- **Alto:** 5 (auth in-memory, in-memory stores, frontend build, whatsapp typecheck, delivery_ops bug)
- **Médio:** 6
- **Baixo:** 4
- **Tests:** 835/839 backend ✅ | 37/37 frontend ✅ | 38/38 whatsapp ✅
- **Build:** Frontend ❌ | WhatsApp typecheck ❌

**Próximo passo:** Apresentar este relatório ao humano e aguardar aprovação antes de iniciar a Fase 15.
