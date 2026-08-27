# FASE 13.1 — SECURITY HARDENING

## STATUS: APPROVED ✅

## CHANGES

### 13.1.1 — Password Security
| Before | After |
|--------|-------|
| SHA-256 + salt | bcrypt |
| Hash: `salt:sha256` | Hash: `bcrypt:$2b$...` |
| Legacy support | ✅ Transparent migration |

- `hash_password()`: Uses `bcrypt.hashpw` with `bcrypt.gensalt()`
- `verify_password()`: Supports both bcrypt and legacy SHA-256
- `needs_rehash()`: Detects legacy hashes for transparent migration
- On successful login, legacy hashes are automatically rehashed to bcrypt

### 13.1.5 — Token Entropy
- `secrets.token_hex(32)` = 256 bits of cryptographic randomness
- Combined with user_id + salt via SHA-256

### 13.1.6 — Auth Enumeration Prevention
- All login failures return **same generic message**: "Invalid credentials."
- Disabled user: same message (no "Account is disabled")
- Nonexistent user: same message + bcrypt dummy hash (timing-safe)
- Rate limit: separate message

### 13.1.12 — Password Change
- `change_password(user_id, old, new)` method added
- Verifies old password before accepting new
- Automatically rehashes to bcrypt
- Audit logged

## TESTS

| Item | Status |
|------|--------|
| bcrypt hash/verify | ✅ |
| Legacy migration | ✅ |
| Generic error messages | ✅ |
| Timing-safe (bcrypt on miss) | ✅ |
| Token entropy (secrets module) | ✅ |
| Password change + rehash | ✅ |
