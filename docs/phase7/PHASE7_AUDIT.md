# FASE 7 — INVENTORY CORE — AUDIT REPORT

## Status: AUDITED — READY FOR IMPLEMENTATION

## Baseline

- **Branch:** main
- **HEAD:** `3976ca0` (release: freeze phase 6 CRM core)
- **Working tree:** 8 untracked Phase 7 files (NOT committed)

---

## 1. CURRENT STATE

### Files Inventory

| File | Layer | Status |
|------|-------|--------|
| `domain/inventory/entity.py` | Domain | Untracked — well-structured |
| `domain/inventory/stock_movement.py` | Domain | Untracked — well-structured |
| `domain/inventory/repository.py` | Domain | Untracked — clean interface |
| `application/inventory/use_cases.py` | Application | Untracked — functional but NOT transactional |
| `infrastructure/repositories/inventory_model.py` | Infrastructure | Untracked — correct schema |
| `infrastructure/repositories/inventory_repository.py` | Infrastructure | Untracked — functional |
| `presentation/api/inventory.py` | Presentation | Untracked — functional endpoints |
| `presentation/schemas/inventory.py` | Presentation | Untracked — clean schemas |
| `tests/test_inventory.py` | Tests | Untracked — 46 tests, ALL unit with fakes |
| `frontend/InventoryDetailPage.tsx` | Frontend | Untracked — complete UI |

### Committed files that were MODIFIED (Phase 7 changes, NOT in HEAD)

| File | Modification | In HEAD? |
|------|-------------|----------|
| `order/use_cases.py` | Inventory integration | ✅ Reverted to HEAD |
| `product/entity.py` | minimum_quantity field | ✅ Reverted to HEAD |
| `product_model.py` | minimum_quantity column | ✅ Reverted to HEAD |
| `product_repository.py` | minimum_quantity handling | ✅ Reverted to HEAD |
| `main.py` | inventory router | ✅ Reverted to HEAD |
| `orders.py` | inventory repo injection | ✅ Reverted to HEAD |
| `init_db.py` | inventory model import | ✅ Reverted to HEAD |
| `frontend/App.tsx` | inventory route | ✅ Reverted to HEAD |
| `frontend/hooks.ts` | inventory hooks | ✅ Reverted to HEAD |
| `frontend/client.ts` | inventory API | ✅ Reverted to HEAD |
| `frontend/types.ts` | inventory types | ✅ Reverted to HEAD |
| `frontend/InventoryPage.tsx` | full inventory page | ✅ Reverted to HEAD |
| `frontend/index.ts` | InventoryDetailPage export | ✅ Reverted to HEAD |

---

## 2. CRITICAL FINDING — DUAL SOURCE OF TRUTH

### Problem

**Product.estoque** (committed in HEAD) and **Inventory.quantity** (untracked) represent the same concept: current stock.

| Source | Entity | Model | In HEAD? |
|--------|--------|-------|----------|
| Product.estoque | `Product.estoque` | `ProductModel.estoque` | ✅ Yes |
| Inventory.quantity | `Inventory.quantity` | `InventoryModel.quantity` | ❌ No (untracked) |

### Current State (HEAD)

- `Product.estoque` is the **active** source of truth
- Order creation in HEAD calls `product.baixar_estoque()` directly
- `Product.baixar_estoque()` and `Product.repor_estoque()` are stock operations
- No synchronization exists between Product.estoque and Inventory.quantity

### Risk Level: **CRITICAL**

If both Product.estoque and Inventory.quantity are active simultaneously:
- They will diverge
- Stock will be inconsistent
- Reports will be wrong
- No single source of truth

### Resolution Required

**Architecture decision:** Choose ONE source of truth.

**Recommended:** Inventory = sole source of truth for stock quantity.

Migration path:
1. When Inventory is committed, Product.estoque must be deprecated
2. Order flow must use Inventory (not Product.baixar_estoque)
3. Product.estoque can remain for backward compatibility but must NOT be the authority
4. Eventually: Product.estoque = 0 always, all stock in Inventory

---

## 3. DOMAIN MODEL AUDIT

### Inventory Entity

**Status:** ✅ Well-structured

| Aspect | Finding |
|--------|---------|
| Validation | ✅ quantity >= 0, minimum >= 0 |
| Operations | ✅ entry(), exit(), adjust(), set_minimum() |
| No negative balance | ✅ exit() raises ValueError |
| Stock status derived | ✅ IN_STOCK/LOW_STOCK/OUT_OF_STOCK computed, not stored |
| No DB rules in entity | ✅ Pure domain logic |

**Gap:** `maximum_quantity` field exists but has no business logic enforcing it.

### StockMovement Entity

**Status:** ✅ Well-structured

| Aspect | Finding |
|--------|---------|
| Immutable | ✅ No update/delete methods |
| Convention | ✅ quantity always positive, type defines direction |
| Direction property | ✅ +1 for ENTRY/RETURN, -1 for SALE/LOSS |
| Reference tracking | ✅ reference_type + reference_id |
| Balance tracking | ✅ balance_before + balance_after |
| Validation | ✅ quantity > 0 (except ADJUSTMENT), reason required |

**Gap:** `signed_quantity` property has inconsistent behavior for ADJUSTMENT (returns positive even when adjustment is negative).

---

## 4. SOURCE OF TRUTH ARCHITECTURE

### Decision Required

**Option A:** Product = authority (current HEAD state)
- Simple, but no history/audit trail
- No stock movement ledger
- Order uses `product.baixar_estoque()` directly

**Option B:** Inventory = authority (Phase 7 proposal)
- Single source of truth
- StockMovement provides audit trail
- Order uses Inventory service
- Product.estoque deprecated

**Option C:** Dual (current untracked state)
- DANGEROUS — two sources that will diverge
- NOT acceptable

**Recommended: Option B**

```
Product (cadastro)
   │
   │ identity (codigo, nome, tipo, preco)
   ▼
Inventory (saldo atual)
   │
   ├── quantity
   ├── minimum_quantity
   └── maximum_quantity
        │
        ▼
StockMovement (ledger)
   ├── ENTRY
   ├── SALE
   ├── ADJUSTMENT
   ├── LOSS
   └── RETURN
```

---

## 5. TRANSACTION BOUNDARY — CRITICAL GAP

### Current State

The use cases perform multiple separate operations:

```python
# AddStockUseCase.execute()
inventory = self.repository.get_or_create(...)  # SELECT
new_balance = inventory.entry(quantity)           # Domain logic
self.repository.update_quantity(...)              # UPDATE + COMMIT
movement = StockMovement(...)
movement = self.repository.register_movement(...) # INSERT + COMMIT
```

**Problem:** Two separate commits. If the second fails, the first is committed.

### Required

Single transaction:

```python
BEGIN
  validate
  UPDATE inventory SET quantity = ?
  INSERT INTO stock_movements (...)
COMMIT
```

On error: ROLLBACK both.

### Current State: **NOT ATOMIC**

---

## 6. ORDER INTEGRATION — NOT COMMITTED

### Current HEAD

```python
# order/use_cases.py (HEAD)
product.baixar_estoque(quantity)  # Modifies Product.estoque
self.product_repo.atualizar(product)
```

Stock is deducted at **Order creation time** (PENDING status).

### Phase 7 Proposal (untracked)

```python
# order/use_cases.py (Phase 7)
# Stock deducted when order is CONFIRMED
# Stock returned when order is CANCELLED
```

### Critical Questions

1. **When is stock deducted?** At creation (PENDING) or confirmation (CONFIRMED)?
   - HEAD: At creation
   - Phase 7 proposal: At confirmation
   - **Decision needed**

2. **Who deducts stock?** Product or Inventory?
   - HEAD: Product.baixar_estoque()
   - Phase 7 proposal: RemoveStockUseCase
   - **Decision needed**

3. **Is the Phase 7 Order integration safe?**
   - It uses app-level idempotency (reference_type + reference_id)
   - No DB-level unique constraint on (reference_type, reference_id)
   - **Race condition possible**

---

## 7. IDEMPOTENCY — APP LEVEL ONLY

### Current Implementation

```python
# RemoveStockUseCase.execute()
if reference_type and reference_id:
    existing = self.repository.get_movement_by_reference(reference_type, reference_id)
    if existing:
        raise ValueError("Movimento já registrado")
```

### Problem

This is check-then-insert — NOT atomic. Two concurrent requests can both pass the check.

### Required

DB-level constraint: `UNIQUE(reference_type, reference_id)` where both are NOT NULL.

Or: Use a single transaction with SELECT FOR UPDATE.

---

## 8. CONCURRENCY — NO DB LOCKS

### Test Scenario

```
Stock = 10
Order A: 7 units
Order B: 7 units (simultaneous)
```

### Current Behavior

Both read stock=10. Both see sufficient. Both deduct. Stock becomes -4.

### Required

Atomic operation: `UPDATE inventory SET quantity = quantity - 7 WHERE quantity >= 7`

Or: SELECT FOR UPDATE + validate + update in single transaction.

### Current Status: **NOT SAFE**

---

## 9. SQLITE CONFIGURATION

### Current State

```python
# connection.py
PRAGMA foreign_keys = ON  ✅
```

### Missing

- `journal_mode = WAL` — needed for concurrent reads
- `busy_timeout` — needed for concurrent writes
- `synchronous = NORMAL` — performance optimization

### Risk

Without WAL, SQLite serializes all writes. With multiple simultaneous Orders, requests will timeout.

---

## 10. DATABASE CONSTRAINTS

### InventoryModel

| Constraint | Status |
|-----------|--------|
| UNIQUE(product_codigo) | ✅ |
| FK → products.codigo | ✅ |
| quantity NOT NULL | ✅ |
| minimum_quantity NOT NULL | ✅ |

### StockMovementModel

| Constraint | Status |
|-----------|--------|
| FK → products.codigo | ✅ |
| Index product_codigo | ✅ |
| Index created_at | ✅ |
| Index (reference_type, reference_id) | ✅ |
| UNIQUE(reference_type, reference_id) | ❌ MISSING — needed for idempotency |

---

## 11. MINIMUM STOCK

**Status:** ✅ Implemented in Inventory entity

- `minimum_quantity` field on Inventory
- `stock_status` property derives IN_STOCK/LOW_STOCK/OUT_OF_STOCK
- Not stored redundantly

**Gap:** `minimum_quantity` is on Inventory entity but NOT on the committed Product entity. When Phase 7 is committed, Product needs `minimum_quantity` migration or Inventory becomes the sole authority.

---

## 12. FRONTEND AUDIT

### Committed (HEAD)

- `InventoryPage.tsx`: **ModulePlaceholder** — just a stub
- No inventory hooks, API client, or types

### Untracked (Phase 7)

- `InventoryDetailPage.tsx`: Complete detail page with movements, entry, adjustment
- Full InventoryPage with search, filters, status cards

### Gap

The untracked frontend references hooks (`useInventoryItem`, `useInventoryMovements`, etc.) that exist in the reverted `hooks.ts`. When Phase 7 is committed, these hooks must be included.

---

## 13. API AUDIT

### Endpoints

| Endpoint | Method | Status |
|----------|--------|--------|
| GET /inventory/ | List | ✅ Implemented |
| GET /inventory/{product_codigo} | Get by product | ✅ Implemented |
| GET /inventory/{product_codigo}/movements | Movements | ✅ Implemented |
| POST /inventory/{product_codigo}/entries | Add stock | ✅ Implemented |
| POST /inventory/{product_codigo}/adjustments | Adjust | ✅ Implemented |
| PATCH /inventory/{product_codigo}/minimum | Set minimum | ✅ Implemented |
| DELETE | — | ❌ Not needed (soft delete via adjustment) |

### Security

- ✅ Frontend cannot send balance_before/balance_after
- ✅ Backend calculates all derived values
- ✅ Schemas restrict writable fields

---

## 14. TEST QUALITY AUDIT

### Current Tests: 46 total

| Category | Count | Type | Quality |
|----------|-------|------|---------|
| Entity validation | 16 | Unit (in-memory) | ✅ Good |
| StockMovement validation | 8 | Unit (in-memory) | ✅ Good |
| Use cases with FakeRepo | 16 | Unit (fake) | ⚠️ No DB |
| Schema validation | 7 | Unit | ✅ Good |
| Mass assignment | 1 | Unit | ✅ Good |
| API boundary | 1 | Static analysis | ✅ Good |

### Missing Tests

| Category | Status |
|----------|--------|
| Integration (real DB) | ❌ None |
| Concurrency (parallel) | ❌ None |
| Transaction rollback | ❌ None |
| Order→Inventory integration | ❌ None |
| Fresh DB install | ❌ None |
| Migration from Product.estoque | ❌ None |

### Critical Gap

**All use case tests use FakeInventoryRepo.** They don't test:
- Real SQL execution
- Transaction boundaries
- Constraint enforcement
- Concurrent access

---

## 15. DATA MIGRATION PLAN

### Current State

- Product.estoque has existing data in production
- Inventory table does not exist yet
- No migration strategy defined

### Required Migration

```markdown
1. Create inventory table
2. For each product with estoque > 0:
   - INSERT INTO inventory (product_codigo, quantity)
   - VALUES (product.codigo, product.estoque)
   - Create INITIAL_BALANCE StockMovement
3. Deprecate Product.estoque (set to 0 or remove)
4. Update Order flow to use Inventory
5. Verify all stock matches before/after
```

### Risks

- Data loss if migration fails midway
- No rollback strategy defined
- No verification step

---

## 16. PERFORMANCE

| Area | Status | Issue |
|------|--------|-------|
| Inventory list | ⚠️ | Loads ALL inventories, filters in Python |
| Movements | ✅ | Paginated with LIMIT/OFFSET |
| N+1 | ✅ | No N+1 detected |
| Indexes | ✅ | product_codigo, created_at, reference indexed |

**Gap:** `list_all()` loads all rows then filters by `stock_status` in Python. Should use SQL CASE WHEN for efficiency at scale.

---

## 17. ARCHITECTURE TARGET

```
Product (identity — nome, tipo, preco)
   │
   │ FK
   ▼
Inventory (current stock)
   │
   ├── quantity (single source of truth)
   ├── minimum_quantity
   └── maximum_quantity
        │
        │ 1:N
        ▼
StockMovement (immutable ledger)
   ├── ENTRY (compra/reposição)
   ├── SALE (baixa por pedido)
   ├── ADJUSTMENT (contagem física)
   ├── LOSS (perda/quebra)
   ├── RETURN (devolução)
   └── INITIAL_BALANCE (migração)

Order
   │
   │ validates via
   ▼
Inventory Application Service
   │
   ├── validate stock
   ├── atomic update + movement
   └── idempotency via reference
```

### Deprecation Plan

1. `Product.estoque` → deprecated, kept for backward compat
2. `Product.baixar_estoque()` → deprecated, replaced by Inventory
3. `Product.repor_estoque()` → deprecated, replaced by Inventory
4. Order flow → uses Inventory, not Product

---

## 18. RISKS REGISTER

| Level | Risk | Description |
|-------|------|-------------|
| **CRITICAL** | Dual source of truth | Product.estoque + Inventory.quantity |
| **CRITICAL** | No transaction atomicity | update_quantity + register_movement are separate commits |
| **HIGH** | No DB-level idempotency | reference_type + reference_id not UNIQUE |
| **HIGH** | No concurrency protection | No SELECT FOR UPDATE or atomic UPDATE |
| **HIGH** | Order integration not committed | Phase 7 Order changes reverted to HEAD |
| **MEDIUM** | No WAL mode | SQLite write serialization |
| **MEDIUM** | No busy_timeout | Concurrent writes may timeout |
| **MEDIUM** | Test quality | All unit tests with fakes, no DB tests |
| **MEDIUM** | No migration plan | Product.estoque → Inventory migration undefined |
| **LOW** | list_all() filters in Python | Performance at scale |
| **LOW** | signed_quantity inconsistent for ADJUSTMENT | Minor code quality |

---

## 19. GAPS SUMMARY

### Must Fix Before Production

1. **Resolve dual source of truth** — Inventory = sole authority
2. **Make operations atomic** — single transaction per stock change
3. **Add DB-level idempotency** — UNIQUE(reference_type, reference_id)
4. **Add concurrency protection** — atomic UPDATE with WHERE quantity >= N
5. **Commit Order integration** — connect Order flow to Inventory
6. **Configure SQLite** — WAL mode, busy_timeout
7. **Write integration tests** — real DB, not just fakes

### Should Fix

8. Create migration plan for Product.estoque → Inventory
9. Add integration test suite
10. Fix list_all() to use SQL filtering
11. Fix signed_quantity for ADJUSTMENT

### Nice to Have

12. Add DELETE /inventory/{product_codigo} (soft)
13. Add batch operations for multi-product stock changes
14. Add stock snapshot/reporting endpoint

---

## 20. RECOMMENDATION

### Phase 7.0 Audit = **AUDITED** ✅

### Next Steps (Phase 7.1)

1. **DO NOT** continue implementing on top of current code
2. **First** resolve the critical architectural issues:
   - Define Inventory as sole source of truth
   - Add transaction boundaries
   - Add DB-level constraints
3. **Then** implement incrementally:
   - Step 1: Inventory domain + DB (no Order integration)
   - Step 2: Inventory API (standalone)
   - Step 3: Integration tests with real DB
   - Step 4: Order integration (replace Product.estoque)
   - Step 5: Migration from Product.estoque
   - Step 6: Frontend
   - Step 7: Regression + adversarial review

### DO NOT

- Add more features before fixing architecture
- Ship Inventory without resolving dual source of truth
- Skip transaction boundaries
- Skip concurrency tests
