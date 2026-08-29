# GASFLOW — FINAL CROSS-PHASE STATUS
# FASES 5 + 6 + 7 + 8 + 15.1 + 15.2 + 15.3 + 16.0 (POST-16.0)

## STATUS: STABLE ✅

## BASELINE

- **Branch:** main
- **Date:** 2026-08-29

---

## PHASE 15.1 — Client Phone Multi-Tenancy
- `UniqueConstraint("telefone")` → `UniqueConstraint("tenant_id", "telefone")`
- Migration `b001` created

## PHASE 15.2 — Delivery Contract Normalization
- `delivery_ops.py` dict/entity mismatch resolved
- IDOR test strengthened

## PHASE 15.3 — Persistence Consolidation (CORRECTED)

### Sessions
- **Before:** `store["sessions"][token] = {...}` — in-memory, lost on restart
- **After:** `driver_sessions` table + `SQLAlchemyDriverSessionRepository`
- **No in-memory fallback** — DB is single source of truth

### Idempotency
- **Before:** `store["idempotency_keys"].add(key)` — in-memory, lost on restart
- **After:** `idempotency_keys` table + `SQLAlchemyIdempotencyRepository`
- **No in-memory fallback** — DB is single source of truth

### Proofs
- **Before:** `store["proofs"][proof_id] = {...}` — in-memory
- **After:** Stored in `DeliveryRecord.proof_type` + `DeliveryRecord.proof_data`
- **No in-memory fallback** — DB is single source of truth

### Sync
- **Before:** `store["deliveries"]` and `store["idempotency_keys"]` — in-memory
- **After:** Uses `SQLAlchemyDeliveryPersistenceRepository` + `SQLAlchemyIdempotencyRepository`

### Routes (Category A — Transient)
- `store["routes"]` remains in-memory (route plans for dispatch sessions)
- **Justified:** Routes are computed and consumed within the same operational cycle
- **TODO:** Persist in Fase 21 when multi-stop route planning requires restart survival

### What was NOT migrated (and why)
- `dispatch._in_memory_store` — calculation cache, recalculated each request
- `operations._in_memory_store` — read-only dashboard cache
- `shared_store["drivers"]` — already persisted via `DeliveryDriverModel`
- `shared_store["locations"]` — already persisted via `DriverLocationRecord`
- `shared_store["deliveries"]` — already persisted via `DeliveryRecord`

### Test Infrastructure
- `conftest.py` created: ensures all tables exist in test SQLite
- `test_persistence_validation.py` added: 17 tests for restart, isolation, idempotency

## PHASE 16.0 — Frontend Hardening
- 13 TypeScript errors resolved (DriverHomePage, DriversPage)
- `GET /delivery/locations` endpoint created

## PHASE PÓS-16.0 — Location Contract Alignment
- `/delivery/locations` endpoint verified against frontend contract
- driver_id = codigo confirmed consistent

---

## TEST RESULTS (Current)

| Suite | Tests | Status |
|-------|-------|--------|
| Backend (all) | **859** | **859 passed, 0 failed** |
| Frontend Tests | 37 | ✅ |
| Frontend Build | — | ✅ PASS (0 TS errors) |
| WhatsApp Tests | 38 | ✅ |

---

## REMAINING KNOWN ISSUES

| # | Issue | Severity | Phase |
|---|-------|----------|-------|
| 1 | Auth in-memory for main users | HIGH | 15.6 |
| 2 | `admin123` default | HIGH | 15.7 |
| 3 | WhatsApp typecheck error | MEDIUM | 15.9 |
| 4 | No CI/CD | MEDIUM | 15.13 |
| 5 | No docker-compose.prod | MEDIUM | 15.14 |
| 6 | ESLint not installed | LOW | — |
| 7 | Routes not persisted | LOW | 21 |

---

## MULTI-TENANT ISOLATION — VERIFIED

| Entity | tenant_id | Isolation |
|--------|-----------|-----------|
| clients | ✅ | ✅ PASS |
| orders | ✅ | ✅ PASS |
| products | ✅ | ✅ PASS |
| delivery_drivers | ✅ | ✅ PASS |
| delivery_records | ✅ | ✅ PASS |
| driver_sessions | ✅ | ✅ PASS |
| idempotency_keys | ✅ | ✅ PASS |
| driver_locations | ✅ | ✅ PASS |
| outbox_entries | ✅ | ✅ PASS |

---

## PERSISTENCE STATUS

| State | Source of Truth | Survives Restart |
|-------|----------------|------------------|
| Sessions | DB (`driver_sessions`) | ✅ YES |
| Idempotency | DB (`idempotency_keys`) | ✅ YES |
| Delivery lifecycle | DB (`delivery_records`) | ✅ YES |
| Driver status | DB (`delivery_drivers`) | ✅ YES |
| GPS location | DB (`driver_locations`) | ✅ YES |
| Proof of delivery | DB (`delivery_records.proof_*`) | ✅ YES |
| Outbox events | DB (`outbox_entries`) | ✅ YES |
| Route plans | In-memory (`store["routes"]`) | ❌ No (transient) |
| Dispatch candidates | In-memory | ❌ No (recalculated) |

---

## DECISION

**PHASES 5–8 + 15.1 + 15.2 + 15.3 + 16.0 = STABLE** ✅

- **859 backend tests, 0 failures**
- All critical operational state persists to database
- No in-memory fallback for sessions, idempotency, or delivery lifecycle
- Multi-tenancy verified across all persistent entities
- Frontend compiles, builds, and tests pass
