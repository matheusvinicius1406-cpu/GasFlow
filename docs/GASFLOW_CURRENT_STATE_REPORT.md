# GASFLOW CURRENT STATE REPORT

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).

# Auditoria Completa — 2026-08-29

---

## 1. ESTADO GERAL

| Indicador | Valor |
|-----------|-------|
| Branch | `main` |
| HEAD | `a1cec33` |
| Backend tests | **859 passed, 0 failed** |
| Frontend tests | **37 passed** |
| Frontend build | **PASS** (0 TS errors) |
| WhatsApp tests | **38 passed** |
| WhatsApp typecheck | **FAIL** (1 error) |
| Working tree | Clean |

---

## 2. BACKEND

### 2.1 Arquitetura

```
FastAPI + SQLAlchemy + DDD
├── domain/          (22 módulos) — entidades, interfaces, regras
├── application/     (10 módulos) — casos de uso, orquestração
├── infrastructure/  (18 módulos) — repos, providers, DB, stores
└── presentation/    (22 endpoints) — API REST, middleware, schemas
```

### 2.2 Módulos Existentes

| Módulo | Domain | Application | Infrastructure | Presentation |
|--------|--------|-------------|----------------|--------------|
| Auth/RBAC | ✅ Models | ✅ AuthService | ⚠️ In-memory | ✅ Endpoints |
| Clients | ✅ Entity | ✅ UseCases | ✅ SQLAlchemy | ✅ CRUD |
| Orders | ✅ Entity | ✅ UseCases | ✅ SQLAlchemy | ✅ CRUD |
| Products | ✅ Entity | ✅ UseCases | ✅ SQLAlchemy | ✅ CRUD |
| Inventory | ✅ Entity | ✅ UseCases | ✅ SQLAlchemy | ✅ CRUD |
| Financial | ✅ 5 models | ✅ UseCases | ✅ SQLAlchemy | ✅ Endpoints |
| Payments | ✅ Models | ✅ PaymentService | ⚠️ In-memory | ✅ Endpoints |
| Delivery | ✅ Entity | ✅ UseCases | ✅ SQLAlchemy | ✅ Endpoints |
| Driver API | ✅ Entity | — | ✅ SQLAlchemy | ✅ Endpoints |
| Dispatch | ✅ Engine | ✅ Service | ⚠️ Mixed | ✅ Endpoints |
| WhatsApp | ✅ Entity | ✅ Gateway | ✅ SQLAlchemy | ✅ Endpoints |
| AI/Copilot | ✅ Provider | ✅ Engine | ⚠️ Mock only | ✅ Endpoints |
| Audio | ✅ Provider | ✅ Gateway | ⚠️ Mock only | ✅ Endpoints |
| Automation | ✅ Models | ✅ Engines | ⚠️ In-memory | ✅ Endpoints |
| Vehicles | ✅ Entity | — | ✅ SQLAlchemy | ✅ Endpoints |
| CRM | ✅ — | ✅ — | ✅ — | ✅ — |
| Dashboard | — | — | — | ✅ Reads |
| Reports | — | — | — | ✅ Reads |
| Printing | — | — | ✅ ESC/POS | ✅ Endpoints |

### 2.3 Repositórios SQLAlchemy (20)

| Repository | Tabela | TenantMixin | Status |
|-----------|--------|-------------|--------|
| SQLAlchemyClientRepository | clients | ✅ | PRODUCTION_READY |
| SQLAlchemyOrderRepository | orders | ✅ | PRODUCTION_READY |
| SQLAlchemyOrderItemRepository | order_items | ✅ | PRODUCTION_READY |
| SQLAlchemyProductRepository | products | ✅ | PRODUCTION_READY |
| SQLAlchemyInventoryRepository | inventory | ✅ | PRODUCTION_READY |
| SQLAlchemyPaymentRepository | payments | ✅ | PRODUCTION_READY |
| SQLAlchemyReceivableRepository | receivables | ✅ | PRODUCTION_READY |
| SQLAlchemyExpenseRepository | expenses | ✅ | PRODUCTION_READY |
| SQLAlchemyCashMovementRepository | cash_movements | ✅ | PRODUCTION_READY |
| SQLAlchemyFinancialLedgerRepository | financial_ledger | ✅ | PRODUCTION_READY |
| SQLAlchemyDeliveryPersistenceRepository | delivery_records | ✅ | PRODUCTION_READY |
| SQLAlchemyDriverLocationRepository | driver_locations | — | PRODUCTION_READY |
| SQLAlchemyOutboxRepository | outbox_entries | — | PRODUCTION_READY |
| SQLAlchemyDriverSessionRepository | driver_sessions | — | PRODUCTION_READY |
| SQLAlchemyIdempotencyRepository | idempotency_keys | — | PRODUCTION_READY |
| SQLAlchemyDeliveryDriverRepository | delivery_drivers | ✅ | PRODUCTION_READY |
| SQLAlchemyWhatsAppRepository | whatsapp_* | ✅ | PRODUCTION_READY |
| SQLAlchemyConversationRepository | ai_conversations | — | PRODUCTION_READY |
| SQLAlchemyMessageRepository | ai_messages | — | PRODUCTION_READY |

---

## 3. FRONTEND

### 3.1 Stack

- React 19 + Vite + TypeScript + Tailwind
- Axios (apiClient com interceptors)
- React Router (20+ rotas)

### 3.2 Telas Existentes (17)

| Tela | Rota | Status | Endpoint Backend |
|------|------|--------|------------------|
| Login | /login | ✅ FUNCIONAL | /api/auth/login |
| Dashboard | / | ✅ FUNCIONAL | /api/orders, /api/clients |
| Orders | /orders | ✅ FUNCIONAL | /api/orders |
| Order Form | /orders/new | ✅ FUNCIONAL | POST /api/orders |
| Order Detail | /orders/:codigo | ✅ FUNCIONAL | /api/orders/:codigo |
| Customers | /customers | ✅ FUNCIONAL | /api/clients |
| Customer Form | /customers/new | ✅ FUNCIONAL | POST /api/clients |
| Customer Detail | /customers/:codigo | ✅ FUNCIONAL | /api/clients/:codigo |
| Products | /products | ✅ FUNCIONAL | /api/products |
| Product Form | /products/new | ✅ FUNCIONAL | POST /api/products |
| Product Detail | /products/:codigo | ✅ FUNCIONAL | /api/products/:codigo |
| Inventory | /inventory | ✅ FUNCIONAL | /api/inventory |
| Finance | /finance | ✅ FUNCIONAL | /api/finance/* |
| Deliveries | /deliveries | ✅ FUNCIONAL | /api/deliveries |
| Drivers | /drivers | ✅ FUNCIONAL | /api/delivery/drivers |
| Driver Login | /driver/login | ✅ FUNCIONAL | /api/driver/v1/auth/login |
| Driver Home | /driver | ✅ FUNCIONAL | /api/driver/v1/* |
| WhatsApp | /whatsapp | ✅ FUNCIONAL | /api/whatsapp/* |
| Intelligence | /intelligence | ⚠️ MOCK | /api/ai/* (mock) |
| Reports | /reports | ✅ FUNCIONAL | /api/reports/* |
| Settings | /settings | ✅ FUNCIONAL | /api/auth/* |
| AI Copilot | — | ⚠️ MOCK | /api/ai/chat (mock) |

---

## 4. DRIVER APP (entregadorGasFlow)

| Item | Status |
|------|--------|
| Repositório separado | ✅ github.com/matheusvinicius1406-cpu/entregadorGasFlow |
| Consome /api/driver/v1 | ✅ |
| Backend é autoridade | ✅ |

---

## 5. DRIVER API

| Endpoint | Método | Existe | Auth | Tenant | Teste | Status |
|----------|--------|--------|------|--------|-------|--------|
| /api/driver/v1/auth/login | POST | ✅ | ❌ | — | ✅ | FUNCIONAL |
| /api/driver/v1/auth/logout | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/me | GET | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/deliveries | GET | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/deliveries/:id | GET | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/deliveries/:id/accept | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/deliveries/:id/start | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/deliveries/:id/arrive | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/deliveries/:id/complete | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/deliveries/:id/fail | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/routes | GET | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/routes/current | GET | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/location | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/proofs | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |
| /api/driver/v1/sync | POST | ✅ | ✅ Bearer | ✅ | ✅ | FUNCIONAL |

---

## 6. DATABASE

### 6.1 Tabelas (20+)

| Tabela | Modelo | FKs | Índices | Unique |
|--------|--------|-----|---------|--------|
| clients | ClientModel | — | ✅ | `(tenant_id, telefone)` |
| orders | OrderModel | client_id | ✅ | `(tenant_id, codigo)` |
| order_items | OrderItemModel | order_id, product_id | ✅ | — |
| products | ProductModel | — | ✅ | `(tenant_id, codigo)` |
| inventory | InventoryModel | product_id | ✅ | `(tenant_id, product_codigo)` |
| stock_movements | StockMovementModel | product_id | ✅ | — |
| payments | PaymentModel | order_id | ✅ | `idempotency_key` |
| receivables | ReceivableModel | order_id | ✅ | — |
| expenses | ExpenseModel | — | ✅ | — |
| cash_movements | CashMovementModel | — | ✅ | — |
| financial_ledger | FinancialLedgerModel | — | ✅ | — |
| delivery_records | DeliveryRecord | — | ✅ | `(tenant_id, idempotency_key)` |
| delivery_drivers | DeliveryDriverModel | — | ✅ | `(tenant_id, codigo)` |
| driver_locations | DriverLocationRecord | — | ✅ | — |
| driver_sessions | DriverSessionRecord | — | ✅ | `token` |
| idempotency_keys | IdempotencyKeyRecord | — | ✅ | `key` |
| outbox_entries | OutboxEntry | — | ✅ | — |
| whatsapp_conversations | WhatsAppConversationModel | — | ✅ | `(account_id, phone_number)` |
| whatsapp_messages | WhatsAppMessageModel | conversation_id | ✅ | `provider_message_id` |
| ai_conversations | ConversationModel | — | ✅ | — |
| ai_messages | AIMessageModel | conversation_id | ✅ | — |
| vehicles | VehicleModel | — | ✅ | — |
| vehicle_capacities | VehicleCapacityModel | vehicle_id | ✅ | — |
| vehicle_loads | VehicleLoadModel | vehicle_id | ✅ | — |

### 6.2 Migrations

| Migration | Descrição | Status |
|-----------|-----------|--------|
| a074610b4bbb | Initial schema | ✅ |
| b001_scope_client_phone_unique_by_tenant | Phone uniqueness per tenant | ✅ |

### 6.3 Engine

- **Dev/Test:** SQLite (WAL mode, FK enforcement)
- **Prod:** PostgreSQL 16 (docker-compose.yml)

---

## 7. AUTH

| Item | Status | Detalhes |
|------|--------|----------|
| AuthService | ⚠️ IN-MEMORY | `_users`, `_sessions`, `_tenants` em dicts |
| Login | ✅ | bcrypt, rate limiting, lockout |
| RBAC | ✅ | SystemRole, ROLE_PERMISSIONS |
| TenantContext | ✅ | user_id, tenant_id, role, permissions |
| Sessions | ⚠️ IN-MEMORY | Perdem-se no restart |
| Admin default | 🔴 admin123 | `config.py:25` |
| Driver auth | ✅ PERSISTENTE | `driver_sessions` table |

---

## 8. MULTI-TENANCY

| Entidade | tenant_id | Isolation | Teste |
|----------|-----------|-----------|-------|
| clients | ✅ | ✅ Unique per tenant | ✅ PASS |
| orders | ✅ | ✅ | ✅ PASS |
| products | ✅ | ✅ | ✅ PASS |
| inventory | ✅ | ✅ | ✅ PASS |
| payments | ✅ | ✅ | ✅ PASS |
| receivables | ✅ | ✅ | ✅ PASS |
| expenses | ✅ | ✅ | ✅ PASS |
| cash_movements | ✅ | ✅ | ✅ PASS |
| financial_ledger | ✅ | ✅ | ✅ PASS |
| delivery_records | ✅ | ✅ | ✅ PASS |
| delivery_drivers | ✅ | ✅ | ✅ PASS |
| driver_locations | ✅ | ✅ | ✅ PASS |
| driver_sessions | ✅ | ✅ | ✅ PASS |
| idempotency_keys | ✅ | ⚠️ Global key | ⚠️ |
| outbox_entries | ✅ | ✅ | ✅ PASS |
| whatsapp_conversations | ✅ | ✅ | ✅ PASS |

---

## 9. WHATSAPP

| Item | Status |
|------|--------|
| Gateway (whatsapp-web.js) | ✅ FUNCIONAL |
| Multi-account | ✅ |
| Auth (QR Code) | ✅ |
| Sessions (SQLite) | ✅ |
| Reconnect | ✅ |
| Receive messages | ✅ |
| Send messages | ✅ |
| Contacts | ✅ |
| Customers | ✅ |
| Lists | ✅ |
| Campaigns | ✅ |
| Broadcast | ✅ |
| Deduplication | ✅ |
| Normalize phone | ✅ |
| Health check | ✅ |
| TypeScript build | ❌ 1 erro (`listSentMessages` not imported) |

---

## 10. PAGAMENTOS

| Item | Status |
|------|--------|
| Domain models | ✅ Payment, PaymentMethod, PixConfig |
| PaymentService | ⚠️ IN-MEMORY |
| SQLAlchemy repository | ✅ (payments table) |
| PIX config per tenant | ✅ Domain model |
| PIX static generation | ❌ NÃO IMPLEMENTADO |
| PIX QR Code | ❌ NÃO IMPLEMENTADO |
| Payment confirmation | ❌ Manual only |

---

## 11. PIX

| Item | Status |
|------|--------|
| Domain model (PixConfig) | ✅ |
| PixKeyType enum | ✅ (CPF, CNPJ, EMAIL, PHONE, EVP) |
| PaymentMethod PIX | ✅ |
| Static PIX generation | ❌ |
| BR Code payload | ❌ |
| QR Code generation | ❌ |
| pypix library | ❌ Não instalado |
| qrcode library | ❌ Não instalado no backend |

---

## 12. PEDIDOS

| Item | Status |
|------|--------|
| Order entity | ✅ |
| OrderItem entity | ✅ |
| CRUD completo | ✅ |
| Status machine | ✅ |
| Decimal para valores | ✅ |
| Imutabilidade pós-finalização | ✅ |
| Audit trail | ✅ (created_at, updated_at) |

---

## 13. ENTREGAS

| Item | Status |
|------|--------|
| Delivery entity | ✅ |
| State machine | ✅ PENDING→ASSIGNED→EN_ROUTE→ARRIVED→DELIVERED/FAILED |
| DeliveryRecord (DB) | ✅ |
| Driver assignment | ✅ |
| GPS tracking | ✅ |
| Proof of delivery | ✅ (DB) |
| Optimistic locking | ✅ |
| Timeline (JSON) | ✅ |
| Outbox events | ✅ |

---

## 14. DISPATCH

| Item | Status |
|------|--------|
| DispatchEngine (domain) | ✅ |
| AssignmentService | ✅ Transactional |
| Capacity check | ✅ |
| Tenant scoping | ✅ |
| In-memory store (candidates) | ⚠️ Category A |
| OR-Tools integration | ❌ |
| OSRM integration | ❌ |
| ETA estimation | ❌ |
| Route optimization | ❌ |

---

## 15. REALTIME

| Item | Status |
|------|--------|
| WebSocket server | ✅ |
| Event types | ✅ |
| Tenant isolation | ✅ |
| Online users tracking | ✅ |
| Broadcast | ✅ |

---

## 16. IA

| Item | Status |
|------|--------|
| LLMProvider interface | ✅ |
| MockLLMProvider | ⚠️ MOCK |
| OllamaProvider | ❌ NÃO IMPLEMENTADO |
| AI engine | ✅ |
| Intent classification | ✅ (pattern-based mock) |
| Tool selection | ✅ (mock) |
| Conversation memory | ✅ (DB) |
| Feature flag AI_ENABLED | ❌ |

---

## 17. STT (Speech-to-Text)

| Item | Status |
|------|--------|
| SpeechToTextProvider interface | ✅ |
| MockSTTProvider | ⚠️ MOCK |
| FasterWhisperProvider | ❌ NÃO IMPLEMENTADO |
| Audio download | ✅ |
| Duration limit | ✅ (120s) |
| Fallback | ✅ |

---

## 18. TTS (Text-to-Speech)

| Item | Status |
|------|--------|
| TextToSpeechProvider interface | ✅ |
| MockTTSProvider | ⚠️ MOCK |
| PiperTTSProvider | ❌ NÃO IMPLEMENTADO |
| Output format | ⚠️ Fake OGG |
| Fallback | ✅ |

---

## 19. FISCAL (NFC-e)

| Item | Status |
|------|--------|
| NFC-e domain | ❌ |
| NFC-e application | ❌ |
| NFC-e infrastructure | ❌ |
| XML generation | ❌ |
| SEFAZ transmission | ❌ |
| Certificate handling | ❌ |
| QR Code NFC-e | ❌ |
| nfelib/PyNFe | ❌ Não instalado |

---

## 20. ANALYTICS

| Item | Status |
|------|--------|
| Dashboard (vendas, pedidos) | ✅ Básico |
| Reports page | ✅ Básico |
| Metabase | ❌ |
| BI avançado | ❌ |
| Previsão de demanda | ❌ |
| Churn detection | ❌ |
| Anomalias financeiras | ❌ |

---

## 21. TESTES

### 21.1 Backend (21 arquivos)

| Arquivo | Testes | Status |
|---------|--------|--------|
| test_phase6_validation.py | 34 | ✅ |
| test_phase7_final.py | 34 | ✅ |
| test_phase7_1_validation.py | 48 | ✅ |
| test_cross_tenant_isolation.py | 20 | ✅ |
| test_tenant_isolation.py | 24 | ✅ |
| test_financial.py | 47 | ✅ |
| test_inventory.py | 23 | ✅ |
| test_order_domain.py | 33 | ✅ |
| test_delivery.py | 30 | ✅ |
| test_delivery_persistence.py | 18 | ✅ |
| test_driver_api.py | 93 | ✅ |
| test_persistence_validation.py | 17 | ✅ |
| test_security.py | 42 | ✅ |
| test_auth_middleware.py | 22 | ✅ |
| test_crm.py | 21 | ✅ |
| test_whatsapp_gateway.py | 38 | ✅ |
| test_whatsapp_hardening.py | 24 | ✅ |
| test_ai.py | 25 | ✅ |
| test_audio.py | 30 | ✅ |
| test_automation.py | 20 | ✅ |
| **TOTAL** | **859** | **859 passed, 0 failed** |

### 21.2 Frontend (6 arquivos)

| Arquivo | Testes | Status |
|---------|--------|--------|
| Button.test.tsx | 1 | ✅ |
| orders.test.tsx | 6 | ✅ |
| DashboardPage.test.tsx | 10 | ✅ |
| DriversPage.test.tsx | 8 | ✅ |
| SettingsPage.test.tsx | 10 | ✅ |
| App.test.tsx | 2 | ✅ |
| **TOTAL** | **37** | **37 passed** |

### 21.3 WhatsApp

| Arquivo | Testes | Status |
|---------|--------|--------|
| provider-manager.test.ts | 38 | ✅ |

---

## 22. BUILD

| Componente | Build | Status |
|-----------|-------|--------|
| Backend (Python) | — | ✅ Sem erros |
| Frontend (Vite) | `npm run build` | ✅ PASS |
| Frontend (TypeScript) | `tsc --noEmit` | ✅ PASS |
| WhatsApp (TypeScript) | `tsc --noEmit` | ❌ 1 erro |
| WhatsApp (Vite) | `npm run build` | ✅ PASS |

---

## 23. SEGURANÇA

| Item | Status | Severidade |
|------|--------|------------|
| Auth in-memory (users) | 🔴 | ALTO |
| admin123 default | 🔴 | ALTO |
| bcrypt password hashing | ✅ | — |
| Rate limiting (login) | ✅ | — |
| Account lockout | ✅ | — |
| Constant-time comparison | ✅ | — |
| Tenant isolation | ✅ | — |
| RBAC | ✅ | — |
| SQL injection (ORM) | ✅ Protegido | — |
| Secrets in Git | ⚠️ .env exists | MÉDIO |
| CORS | ⚠️ Não verificado | MÉDIO |
| CSRF | ⚠️ Não verificado | MÉDIO |
| Input validation (Pydantic) | ✅ | — |
| No secrets in frontend | ✅ | — |

---

## 24. DÍVIDA TÉCNICA

| # | Item | Severidade | Descrição |
|---|------|-----------|-----------|
| 1 | Auth in-memory | ALTO | AuthService usa dicts — perde dados no restart |
| 2 | admin123 default | ALTO | config.py:25 — fallback de senha |
| 3 | PaymentService in-memory | ALTO | Pagamentos em dict — não persiste |
| 4 | delivery_ops shared_store | MÉDIO | create_delivery/write_routes ainda usam dict |
| 5 | dispatch shared_store | MÉDIO | candidates em memória |
| 6 | 38x `except Exception` | MÉDIO | Genérico demais |
| 7 | WhatsApp typecheck | MÉDIO | `listSentMessages` não importado |
| 8 | Sem CI/CD | MÉDIO | Nenhum GitHub Actions |
| 9 | Sem docker-compose.prod | MÉDIO | Apenas docker-compose.yml |
| 10 | Sem LGPD export/delete | MÉDIO | — |
| 11 | datetime.utcnow() deprecated | BAIXO | Python 3.14 |
| 12 | ESLint não instalado | BAIXO | — |
| 13 | Routes em memória | BAIXO | Category A justificado |

---

## 25. PRIORIDADES

### P0 — Segurança / Integridade

| # | Item | Status | Ação |
|---|------|--------|------|
| 1 | Auth in-memory | 🔴 | Migrar users/sessions/tenants/roles para DB |
| 2 | admin123 default | 🔴 | Fail fast em produção sem ADMIN_PASSWORD |
| 3 | PaymentService in-memory | 🔴 | Migrar para SQLAlchemy |

### P1 — Backend/Frontend quebrado

| # | Item | Status | Ação |
|---|------|--------|------|
| 4 | WhatsApp typecheck | 🟡 | Importar `listSentMessages` |
| 5 | delivery_ops shared_store | 🟡 | Migrar create_delivery/write_routes |
| 6 | dispatch shared_store | 🟡 | Migrar candidates |

### P2 — PIX / WhatsApp / Driver

| # | Item | Status | Ação |
|---|------|--------|------|
| 7 | PIX estático | ❌ | Implementar pypix + qrcode |
| 8 | CI/CD | ❌ | GitHub Actions |
| 9 | docker-compose.prod | ❌ | Criar |

### P3 — IA / STT / TTS

| # | Item | Status | Ação |
|---|------|--------|------|
| 10 | Ollama provider | ❌ | Implementar |
| 11 | FasterWhisper provider | ❌ | Implementar |
| 12 | Piper TTS provider | ❌ | Implementar |

### P4 — Analytics / Avançado

| # | Item | Status | Ação |
|---|------|--------|------|
| 13 | NFC-e | ❌ | Fase 18 |
| 14 | OR-Tools | ❌ | Fase 21 |
| 15 | OSRM | ❌ | Fase 21 |
| 16 | Metabase | ❌ | Fase 22 |
| 17 | LGPD | ❌ | Fase 15.16 |
| 18 | PWA | ❌ | Fase 22+ |

---

## 26. CLASSIFICAÇÃO DAS IDEIAS DO ULTRAPROMPT

| Ideia | Classificação | Justificativa |
|-------|---------------|---------------|
| DDD + Clean Architecture | **USE NOW** | Já implementado e funcionando |
| Multi-tenancy | **USE NOW** | Já implementado, testado |
| Provider pattern (AI, STT, TTS) | **USE NOW** | Interfaces já existem |
| Event Bus + Outbox | **USE NOW** | Já implementado |
| WebSocket realtime | **USE NOW** | Já implementado |
| Auth in-memory → DB | **USE NOW** | Crítico — P0 |
| PaymentService → DB | **USE NOW** | Crítico — P0 |
| admin123 removal | **USE NOW** | Crítico — P0 |
| PIX estático | **ADAPT** | Domain models existem, falta implementação |
| Ollama provider | **ADAPT** | Interface existe, falta implementação |
| FasterWhisper provider | **ADAPT** | Interface existe, falta implementação |
| Piper TTS provider | **ADAPT** | Interface existe, falta implementação |
| CI/CD (GitHub Actions) | **ADAPT** | Pipeline mínimo necessário |
| docker-compose.prod | **ADAPT** | docker-compose.yml base existe |
| LGPD export/delete | **LATER** | Importante mas não bloqueante |
| OR-Tools | **LATER** | Fase 21 — depois de dispatch estável |
| OSRM | **LATER** | Fase 21 |
| Metabase | **LATER** | Fase 22 — BI separado |
| NFC-e | **LATER** | Fase 18 — requer gate humano |
| PWA | **LATER** | Fase 22+ |
| IoT | **EXPERIMENT** | Futuro distante |
| SaaS avançado | **LATER** | Fase 22+ |
| WeatherProvider | **EXPERIMENT** | Futuro |
| B2B | **LATER** | Fase 22+ |
| Churn/Anomaly detection | **LATER** | Fase 22+ |
| Baileys (WhatsApp) | **REJECT** | whatsapp-web.js funciona, não trocar sem necessidade |

---

## 27. RISCOS

### Arquitetura
- Auth in-memory é o maior risco — restart destrói todos os usuários e sessões
- PaymentService in-memory — pagamentos se perdem no restart
- delivery_ops ainda usa shared_store para criação de entregas

### Dados
- `admin123` como default — qualquer pessoa que não configure variável de ambiente fica com senha fraca
- Sem backup strategy documentada

### Produção
- Sem CI/CD — nenhum gate automático
- Sem docker-compose.prod — deploy manual
- Sem health check automatizado
- Sem monitoring/logging em produção

### Segurança
- CORS não verificado
- Sem rate limiting em endpoints além de login
- Sem HTTPS enforcement documentado

---

## 28. O QUE NÃO EXISTE (GAPS)

| Gap | Prioridade | Esforço |
|-----|-----------|---------|
| Auth persistente (users) | P0 | M |
| PaymentService persistente | P0 | M |
| PIX estático | P2 | M |
| Ollama provider | P3 | M |
| FasterWhisper provider | P3 | M |
| Piper TTS provider | P3 | M |
| CI/CD | P2 | S |
| docker-compose.prod | P2 | S |
| LGPD export/delete | P2 | M |
| NFC-e | P4 | G |
| OR-Tools dispatch | P4 | G |
| OSRM routing | P4 | M |
| Metabase BI | P4 | S |
| PWA client | P4 | G |
| Coupon system | P2 | M |
| CouponRedemption | P2 | M |

---

## 29. RECOMENDAÇÃO DE ORDEM

```
1. Auth in-memory → DB (P0)
2. PaymentService in-memory → DB (P0)
3. admin123 removal (P0)
4. WhatsApp typecheck fix (P1)
5. delivery_ops shared_store cleanup (P1)
6. CI/CD GitHub Actions (P2)
7. docker-compose.prod (P2)
8. PIX estático (P2)
9. Coupon system (P2)
10. Ollama provider (P3)
11. FasterWhisper provider (P3)
12. Piper TTS provider (P3)
13. LGPD (P2)
14. NFC-e 18a (P4)
15. OR-Tools (P4)
```

---

## 30. CONCLUSÃO

O GasFlow possui uma base sólida com **859 testes passando**, arquitetura DDD consistente, multi-tenancy verificado, e 17 telas funcionais. Os maiores riscos são a autenticação in-memory (P0), o PaymentService in-memory (P0), e a ausência de CI/CD (P2). As interfaces para providers (AI, STT, TTS) já existem — falta implementar as versões reais. O PIX estático tem domain models prontos mas falta a geração de payload e QR Code.

**Estado geral: ESTÁVEL com riscos conhecidos em P0.**
