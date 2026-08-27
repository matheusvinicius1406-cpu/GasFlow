# FASE 6 — FINAL VALIDATION

## STATUS

**APPROVED** ✅

## BASELINE

- **branch:** main
- **commit:** 53953cf530f45e23090d8d088f4915389e5f5089
- **working tree:** Phase 7 inventory changes present (uncommitted)
- **validation date:** 2026-08-27

## DATABASE

| Constraint | Status | Evidence |
|-----------|--------|----------|
| UNIQUE(telefone) | **PASS** | `UniqueConstraint("telefone", name="uq_clients_telefone")` in client_model.py:40 |
| FK(Order→Client) | **PASS** | `ForeignKey("clients.codigo")` in order_model.py:17 |
| FK(OrderItem→Order) | **PASS** | `ForeignKey("orders.codigo")` in order_item_model.py:16 |
| PRAGMA foreign_keys=ON | **PASS** | connection.py:24, verified via `PRAGMA foreign_keys` query |
| Index telefone | **PASS** | `ix_clients_telefone` in client_model.py |
| Index tipo | **PASS** | `ix_clients_tipo` in client_model.py |
| Index ativo | **PASS** | `ix_clients_ativo` in client_model.py |
| Index email | **PASS** | `ix_clients_email` in client_model.py |

## CUSTOMER

| Field | Type | Required | Indexed | Normalized |
|-------|------|----------|---------|------------|
| codigo | String(6) | ✅ | ✅ unique | — |
| nome | String | ✅ | — | — |
| telefone | String | ✅ | ✅ unique+index | ✅ normalize_phone() |
| telefone_secundario | String | — | — | ✅ normalize_phone() |
| email | String | — | ✅ index | — |
| tipo | String | — | ✅ index | — |
| rua | String | ✅ | — | — |
| numero | String | ✅ | — | — |
| bairro | String | ✅ | ✅ (via search) | — |
| complemento | String | — | — | — |
| referencia | String | — | — | — |
| observacoes | String | — | — | — |
| ativo | Boolean | ✅ | ✅ index | — |
| created_at | DateTime | ✅ | — | — |
| updated_at | DateTime | ✅ | — | — |

**Canonical entity:** `Client` (app/domain/client/entity.py)
**No duplicates found:** No Customer, CrmCustomer, or CrmPerson entities exist.

## PHONE NORMALIZATION

**Canonical function:** `normalize_phone()` in `app/domain/client/entity.py`

| Input | Output | Status |
|-------|--------|--------|
| `+55 11 99999-9999` | `5511999999999` | ✅ |
| `(11) 99999-9999` | `11999999999` | ✅ |
| `11999999999` | `11999999999` | ✅ |
| `00551199999999` | `551199999999` | ✅ |
| `""` | `""` | ✅ |
| `11-99999-9999` | `11999999999` | ✅ |

**Separation:** Normalization (backend) ≠ WhatsApp validation (whatsapp/normalize.ts) ≠ display formatting (frontend formatPhone).

## PHONE UNIQUENESS — DATABASE GATE

**Status:** RESOLVED ✅

- DB-level: `UniqueConstraint("telefone", name="uq_clients_telefone")` enforced
- App-level: `CreateClientUseCase` checks via `buscar_por_telefone()` before insert
- Repository: `client_repository.py:85` catches `IntegrityError` with clean message
- Race condition: DB constraint is the safety net; app-level check is best-effort

## ORDER → CLIENT FK

**Status:** RESOLVED ✅

- `ForeignKey("clients.codigo")` on `OrderModel.client_codigo`
- PRAGMA foreign_keys=ON enforced on every connection
- Test confirms: order with non-existent client raises IntegrityError
- No orphan orders possible

## SOFT DELETE

**Status:** PASS ✅

- `PATCH /clients/{codigo}/disable` sets `ativo=False`
- Orders preserved after client disable
- Customer 360 still works for disabled clients
- History fully preserved

## CUSTOMER 360

**Status:** PASS ✅ (with known gap)

| Field | Source | Status |
|-------|--------|--------|
| total_orders | Order count | ✅ Derived |
| total_spent | Sum of order totals | ✅ Derived |
| average_ticket | total_spent / total_orders | ✅ Derived |
| first_order_at | Min(order.created_at) | ✅ Derived |
| last_order_at | Max(order.created_at) | ✅ Derived |
| days_since_last_order | (now - last_order_at).days | ✅ Derived |
| favorite_product | — | ⚠️ NOT_IMPLEMENTED (always None) |

**Known gap:** `favorite_product` is not calculated from order items. Classified as NOT_IMPLEMENTED / LOW priority.

## METRICS

- All metrics derived from orders via `get_customer_metrics()`
- No manual metric storage
- Cancelled orders ARE included in metrics (current behavior — documented)
- Frontend cannot write derived fields (mass assignment protected)

## SEARCH

**Status:** PASS ✅

- Server-side via `ILIKE` (case-insensitive)
- Fields: nome, codigo, telefone, bairro, email
- Parameterized queries (no SQL injection)
- Special characters handled safely
- Empty search returns all

## PAGINATION

**Status:** PASS ✅

- Server-side via SQL LIMIT/OFFSET
- Contract: page, page_size, total, total_pages, items
- API validation: `page >= 1`, `1 <= page_size <= 100`
- Repository handles arbitrary values safely

## MASS ASSIGNMENT

**Status:** PASS ✅

- `ClientCreate` excludes: codigo, ativo, created_at, updated_at, total_orders, total_spent, etc.
- `ClientUpdate` excludes: codigo, created_at, updated_at, derived fields
- `Customer360Response` is read-only
- Adversarial test confirms no derived field is writable

## API CONTRACT

| Endpoint | Method | Status |
|----------|--------|--------|
| GET /clients/ | paginated list | ✅ |
| GET /clients/legacy | all active (backward compat) | ✅ |
| GET /clients/{codigo} | single client | ✅ |
| GET /clients/{codigo}/360 | customer 360 | ✅ |
| GET /clients/{codigo}/orders | client orders | ✅ |
| POST /clients/ | create | ✅ |
| PUT /clients/{codigo} | update | ✅ |
| PATCH /clients/{codigo}/disable | soft delete | ✅ |

## FRONTEND

| Component | Status |
|-----------|--------|
| CustomersPage (list) | ✅ search, pagination, filters, loading, empty, error |
| CustomerDetailPage (360) | ✅ metrics, tabs, orders, address, notes |
| CustomerFormPage (create/edit) | ✅ validation, types, all fields |
| API hooks | ✅ useCustomers, useCustomer360, useCreateCustomer, etc. |
| API client | ✅ All endpoints, no secrets |
| TypeScript types | ✅ Client, Customer360, PaginatedResponse |

## FRONTEND/BACKEND CONTRACT

- snake_case used consistently (backend → frontend)
- Dates serialized as ISO strings
- Numbers: float for money, int for quantities
- null used for optional fields (not undefined)

## CUSTOMER ↔ WHATSAPP BOUNDARY

**Status:** PASS ✅

- CRM code contains zero WhatsApp imports
- Frontend API client contains zero `localhost:3001` references
- No `MARCOS_GAS_API_KEY` in frontend
- No `whatsapp-web.js` in CRM code

## PERFORMANCE

| Area | Status | Evidence |
|------|--------|----------|
| N+1 on Customer360 | **PASS** | Single query with `.all()` aggregation |
| N+1 on customer list | **PASS** | Single query with LIMIT/OFFSET |
| Search N+1 | **PASS** | Single query with ILIKE |
| Indexes | **PASS** | telefone, tipo, ativo, email indexed |

## SECURITY

| Check | Status |
|-------|--------|
| SQL injection | **PASS** — parameterized queries throughout |
| Mass assignment | **PASS** — schemas restrict writable fields |
| IDOR | **PASS** — codigo-based access (no sequential IDs exposed) |
| Secrets in frontend | **PASS** — zero found |
| Stack trace exposure | **NOT VERIFIED** — depends on deployment config |

## TEST RESULTS

| Suite | Count | Status |
|-------|-------|--------|
| test_crm.py | 21 | ✅ All pass |
| test_order_domain.py | 33 | ✅ All pass |
| test_inventory.py | 46 | ✅ All pass |
| test_phase6_validation.py | 32 | ✅ All pass |
| **Total backend** | **132** | **✅ All pass** |
| Frontend TypeScript | — | ✅ Compiles clean |
| Frontend build | — | ✅ Builds successfully |
| Docker config | — | ✅ Valid (deprecation warning on `version`) |

## ADVERSARIAL REVIEW

| # | Test | Result | Evidence |
|---|------|--------|----------|
| 1 | Same phone twice | **PASS** | UniqueConstraint prevents; test confirms IntegrityError |
| 2 | Same phone concurrent | **PASS** | DB constraint is safety net; test confirms |
| 3 | Different phone format | **PASS** | normalize_phone() catches; test confirms |
| 4 | Non-existent client | **PASS** | 404 returned; FK prevents orphan |
| 5 | Orphan order | **PASS** | FK constraint enforced; test confirms |
| 6 | Alter metric | **PASS** | Schemas exclude derived fields |
| 7 | Alter codigo | **PASS** | Not in ClientUpdate schema |
| 8 | Large page_size | **PASS** | API limits to 100; repo handles gracefully |
| 9 | SQL injection | **PASS** | Parameterized queries; special chars return 0 results |
| 10 | Mass assignment | **PASS** | Adversarial test confirms |
| 11 | Disabled client | **PASS** | ativo=False preserves everything |
| 12 | Customer360 no orders | **PASS** | Returns zeroed metrics |
| 13 | Customer360 many orders | **PASS** | Metrics calculated correctly |
| 14 | Cancelled order | **PASS** | Included in metrics (documented behavior) |
| 15 | WhatsApp offline | **NOT VERIFIED** | Requires running WhatsApp service |
| 16 | WhatsApp endpoint direct | **PASS** | CRM code has zero WhatsApp references |
| 17 | Secret in bundle | **PASS** | Grep confirms zero secrets |
| 18 | WhatsApp regression | **NOT VERIFIED** | Requires WhatsApp test suite |

## NOT VERIFIED

- WhatsApp runtime regression (requires running WhatsApp service)
- WhatsApp offline behavior
- Docker runtime (config valid, not tested)
- Fresh database install with real SQLite file
- Authorization/auth (deferred to Phase 13)
- Audit log mechanism (deferred)

## RISK REGISTER

| Level | Risk | Status |
|-------|------|--------|
| ~~CRITICAL~~ | — | None |
| ~~HIGH~~ | — | None |
| ~~MEDIUM~~ | UNIQUE(telefone) | **RESOLVED** — constraint exists and tested |
| ~~MEDIUM~~ | FK(Order→Client) | **RESOLVED** — constraint exists and tested |
| LOW | favorite_product not implemented | Documented, low priority |
| LOW | Auth not implemented | Deferred to Phase 13 |

## BLOCKERS

None.

## DECISION

**FASE 6 — APPROVED** ✅

All critical criteria met:
- ✅ Customer model valid and canonical
- ✅ Phone normalization canonical
- ✅ DB uniqueness enforced
- ✅ Concurrency protection (DB constraint)
- ✅ Search server-side
- ✅ Pagination server-side
- ✅ Customer 360 with derived metrics
- ✅ Order relation with FK
- ✅ Soft delete preserves history
- ✅ Mass assignment protected
- ✅ Frontend complete
- ✅ 132 tests pass
- ✅ TypeScript clean
- ✅ Build succeeds
- ✅ Docker config valid
- ✅ Security scan clean
- ✅ Adversarial review passed
- ✅ No blockers, no critical, no high risks

**FASE 6 = CONGELADA**
**FASE 7 = READY**
