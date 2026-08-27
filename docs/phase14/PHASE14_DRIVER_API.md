# Driver API — FASE 14.5

## Architecture

```
DRIVER APP → HTTPS → FastAPI → DRIVER API → AUTH → TENANT → DRIVER OWNERSHIP
→ DELIVERY USE CASE → DOMAIN → DATABASE
```

**Never:** Driver App → Database, Finance, Inventory, Admin, Tools, Workflows

## Authentication

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/driver/v1/auth/login | POST | None | Driver login |
| /api/driver/v1/auth/logout | POST | Bearer | Driver logout |
| /api/driver/v1/me | GET | Bearer | Current driver info |

## Deliveries (Driver-scoped)

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/driver/v1/deliveries | GET | Bearer | List own deliveries |
| /api/driver/v1/deliveries/{id} | GET | Bearer | Delivery detail |
| /api/driver/v1/deliveries/{id}/accept | POST | Bearer | Accept delivery |
| /api/driver/v1/deliveries/{id}/start | POST | Bearer | Start route |
| /api/driver/v1/deliveries/{id}/arrive | POST | Bearer | Arrive at location |
| /api/driver/v1/deliveries/{id}/complete | POST | Bearer | Complete delivery |
| /api/driver/v1/deliveries/{id}/fail | POST | Bearer | Report failure |

## Routes (Driver-scoped)

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/driver/v1/routes | GET | Bearer | List own routes |
| /api/driver/v1/routes/current | GET | Bearer | Current active route |

## Location

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/driver/v1/location | POST | Bearer | GPS update (10s rate limit) |

## Proofs

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/driver/v1/proofs | POST | Bearer | Upload delivery proof |

## Sync (Offline support)

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/driver/v1/sync | POST | Bearer | Batch action sync |

## DTOs

### DriverDeliverySummary (compact)
```json
{
  "delivery_id": "uuid",
  "order_reference": "ORD-001",
  "customer_name": "Maria",
  "masked_phone": "1199****8888",
  "address": "Rua A, 100 - Centro",
  "status": "ASSIGNED",
  "scheduled_at": "2024-01-01T10:00:00",
  "eta_minutes": 30,
  "version": 1
}
```

### DriverDeliveryDetail (full)
```json
{
  "delivery_id": "uuid",
  "order_reference": "ORD-001",
  "customer_name": "Maria",
  "address": "Rua A, 100 - Centro, SP",
  "status": "ASSIGNED",
  "can_accept": false,
  "can_start": true,
  "can_arrive": false,
  "can_complete": false,
  "can_fail": true,
  "proof_required": false,
  "version": 1
}
```

## State Machine

```
PENDING → ASSIGNED → DISPATCHED → EN_ROUTE → ARRIVED → DELIVERED
                                  → FAILED
```

### Allowed Actions per State

| State | can_accept | can_start | can_arrive | can_complete | can_fail |
|-------|-----------|-----------|-----------|-------------|---------|
| PENDING | ✅ | ❌ | ❌ | ❌ | ❌ |
| ASSIGNED | ❌ | ✅ | ❌ | ❌ | ❌ |
| DISPATCHED | ❌ | ✅ | ❌ | ❌ | ❌ |
| EN_ROUTE | ❌ | ❌ | ✅ | ❌ | ✅ |
| ARRIVED | ❌ | ❌ | ❌ | ✅ | ✅ |
| DELIVERED | ❌ | ❌ | ❌ | ❌ | ❌ |
| FAILED | ❌ | ❌ | ❌ | ❌ | ❌ |

## Idempotency

Every action accepts `idempotency_key`. If sent twice:
- First: action executed
- Second: `{"idempotent_replay": true}` returned

## Versioning (Optimistic Concurrency)

Every response includes `version`. To update:
1. Read delivery → get `version`
2. Send action with `client_version`
3. If version mismatch → `409 STATE_CONFLICT` with current state

## Error Codes

| Code | Meaning |
|------|---------|
| AUTH_REQUIRED | No token |
| FORBIDDEN | Not authorized |
| DELIVERY_NOT_FOUND | Delivery doesn't exist |
| DELIVERY_NOT_ASSIGNED | Not this driver's delivery |
| INVALID_STATE | Cannot perform action in current state |
| STATE_CONFLICT | Version mismatch |
| IDEMPOTENT_REPLAY | Already processed |
| PROOF_REQUIRED | Proof needed for completion |
| PROOF_INVALID | Invalid proof type |
| ROUTE_NOT_FOUND | No active route |
| LOCATION_INVALID | Invalid GPS coordinates |
| RATE_LIMITED | Too many requests |

## Driver Permissions

| Permission | Purpose |
|------------|---------|
| delivery.read.assigned | Read own deliveries |
| delivery.accept | Accept delivery |
| delivery.start | Start route |
| delivery.arrive | Arrive at location |
| delivery.complete | Complete delivery |
| delivery.fail | Report failure |
| route.read.assigned | Read own routes |
| location.write.self | Update own GPS |
| proof.write.assigned | Upload proof for own delivery |
| customer.read | Read customer name/address |
| order.read | Read order reference |

**Driver CANNOT:** finance.*, inventory.*, admin.*, workflow.*, agent.*, user.*
