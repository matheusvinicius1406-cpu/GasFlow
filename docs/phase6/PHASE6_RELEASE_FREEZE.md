# Phase 6 Release Freeze

## Baseline

- **Commit before:** `53953cf530f45e23090d8d088f4915389e5f5089`
- **Commit after:** pending (this freeze commit)
- **Branch:** main

## Scope

**CRM Core** — Customer 360, Customer Identity, Relationship Management

## Included in Phase 6

- Client entity (canonical, single)
- ClientModel with UNIQUE(telefone), indexes
- ClientRepository with search, pagination
- ClientUseCases (Create, Get, List, Update, Disable, Customer360)
- Client schemas (Create, Update, Response, ListResponse, Customer360Response)
- Client API (POST, GET, GET/360, GET/orders, PUT, PATCH/disable, legacy)
- Phone normalization (`normalize_phone()`)
- Phone uniqueness (DB constraint + app-level check)
- Order → Client FK (ForeignKey + PRAGMA foreign_keys=ON)
- Soft delete (ativo field, preserves history)
- Customer 360 (derived metrics from orders)
- Search (server-side, ILIKE, parameterized)
- Pagination (server-side, LIMIT/OFFSET)
- Mass assignment protection
- Frontend: CustomersPage, CustomerDetailPage, CustomerFormPage
- Frontend: API hooks, API client, TypeScript types
- CRM tests (test_crm.py — 21 tests)
- Order domain tests (test_order_domain.py — 33 tests)
- Phase 6 validation tests (test_phase6_validation.py — 32 tests)
- Documentation: PHASE6_FINAL_VALIDATION.md, PHASE6_ADVERSARIAL_REVIEW.md

## Excluded from Phase 6 (Phase 7 work)

- Inventory domain entity
- StockMovement entity
- Inventory repository
- Inventory API
- Inventory schemas
- Inventory use cases
- Inventory frontend (InventoryPage, InventoryDetailPage)
- Inventory tests (test_inventory.py)
- Order → Inventory integration
- Product minimum_quantity field
- All inventory-related hooks, types, API client methods

## Phase 7 work intentionally excluded

Phase 7 (Inventory Core) implementation exists in the working tree as untracked files.
These are preserved but NOT included in this commit.
Working tree after commit will contain Phase 7 files ready for future staging.

## Validation

- Backend tests: 132/132 pass ✅
- Frontend TypeScript: clean on Phase 6 code ✅
- Frontend build: succeeds ✅
- Docker config: valid ✅
- Security scan: zero secrets ✅
- Adversarial review: 16/18 PASS, 2 NOT VERIFIED ✅
