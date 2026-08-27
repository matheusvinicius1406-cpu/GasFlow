# FASE 10.X — HARDENING REPORT

## STATUS: **APPROVED**

## CHANGES

### Bug Fix: Draft Deserialization
- `ConversationDraft.to_dict()` included computed properties (`subtotal`, `total`) that aren't valid constructor args
- Fixed `_to_domain` to filter to only valid keys before constructing
- This prevented order drafts from being restored from DB

### Rate Limiting
- 30 messages per minute per phone number
- Thread-safe with `_rate_buckets` dict + lock
- Tracked in metrics

### Stock/Price Recheck
- Before order confirmation, rechecks Inventory.quantity for each item
- If stock dropped below requested quantity → rejects with clear message
- Rechecks Product.price and updates draft if price changed
- Prevents stale draft orders

### Draft Expiration
- 30-minute TTL for pending drafts
- Auto-expires stale AWAITING_CONFIRMATION → BROWSING
- Tracked in metrics

### Confirmation Hardening
- Added ambiguous confirmation patterns (talvez, depois, etc.)
- Returns "preciso de confirmação clara" instead of silent failure
- Existing positive/negative patterns verified

### Error Recovery
- AI engine failures return safe fallback message
- Never crashes the gateway
- `ai_failures` metric tracked

### Observability Metrics
- messages_received, messages_processed, duplicate_messages
- ai_calls, ai_failures
- orders_created, human_handoffs
- rate_limited, drafts_expired, stock_rechecks_failed
- Thread-safe via `_metrics_lock`

### Order Ownership
- Customer resolved by phone → CRM identity
- Conversation linked to customer_codigo
- Different customers get different conversations

### Human Handoff
- CLOSED conversation cannot be taken over
- Already HUMAN_ACTIVE returns error
- Release returns system notification message

### Input Validation
- Invalid account_id defaults to "primary"
- Oversized messages truncated to 4096 chars
- Phone normalized to digits, min 8 chars

## TESTS

| Suite | Tests | Status |
|-------|-------|--------|
| test_whatsapp_hardening.py | 46 | ✅ |
| test_whatsapp_gateway.py | 32 | ✅ |
| Backend (all) | 384 | ✅ All pass |
| WhatsApp | 38 | ✅ |
| TypeScript | PASS | ✅ |
| Build | PASS | ✅ |
| Security | PASS | ✅ |
