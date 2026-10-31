#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Smoke test pós-deploy — valida a stack docker-compose.prod
#
# Uso:
#   docker compose -f docker-compose.prod.yml --env-file .env.production up -d
#   ./scripts/smoke-test.sh [BASE_URL]
#
# BASE_URL default: http://localhost (porta do frontend)
# ═══════════════════════════════════════════════════════════════
set -uo pipefail

BASE_URL="${1:-http://localhost}"
TIMEOUT_TOTAL="${SMOKE_TIMEOUT:-120}"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
PASS=0; FAIL=0

check() {
  local desc="$1" url="$2" expect="$3"
  for _ in $(seq 1 "$TIMEOUT_TOTAL"); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null || true)
    if [ "$code" = "$expect" ]; then
      echo -e "${GREEN}OK${NC}  $desc ($code)"
      PASS=$((PASS + 1)); return 0
    fi
    sleep 2
  done
  echo -e "${RED}FAIL${NC} $desc (último código: ${code:-sem resposta})"
  FAIL=$((FAIL + 1)); return 1
}

echo "== Smoke test — $BASE_URL =="

# Frontend (nginx) responde
check "frontend (SPA)"                "$BASE_URL/"                         200
# Health via nginx -> backend
check "backend /health via nginx"     "$BASE_URL/api/health"               200
# Readiness (database/redis/whatsapp) via nginx - rota /ready e nova no nginx
check "backend /ready via nginx"      "$BASE_URL/ready"                    200
# /api/v1/* e' servido COM o prefixo pelo FastAPI (nginx NAO faz strip)
check "api v1 (sem strip)"            "$BASE_URL/api/v1/health"            200
# Regressao M1: rotas raiz do backend (antes caiam no fallback da SPA)
check "auth raiz (401 esperado)"      "$BASE_URL/auth/me"                  401
check "driver raiz (401 esperado)"    "$BASE_URL/driver/me"                401
# Regressao O2: /metrics nunca sai pela borda
check "metrics bloqueado na borda"    "$BASE_URL/metrics"                  404
# WhatsApp health exige Bearer (MARCOS_GAS_API_KEY) - 401 sem a chave
check "whatsapp via backend proxy"    "$BASE_URL/api/whatsapp/health"      401

# Autenticação real: login -> token -> /dashboard
LOGIN_BODY=$(curl -s --max-time 5 -X POST "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"${ADMIN_PASSWORD:-admin123}\"}" 2>/dev/null || true)
TOKEN=$(printf '%s' "$LOGIN_BODY" | python -c "import sys,json;
try: print(json.load(sys.stdin).get('token',''))
except Exception: print('')" 2>/dev/null || true)

if [ -n "$TOKEN" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/dashboard" || true)
  if [ "$code" = "200" ]; then
    echo -e "${GREEN}OK${NC}  auth + GET /dashboard (200)"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAIL${NC} auth + /dashboard ($code)"
    FAIL=$((FAIL + 1))
  fi
else
  echo -e "${RED}FAIL${NC} login retornou sem token (verifique ADMIN_PASSWORD)"
  FAIL=$((FAIL + 1))
fi

echo "========================================="
echo -e "Resultado: ${GREEN}$PASS ok${NC} / ${RED}$FAIL falhas${NC}"
[ "$FAIL" -eq 0 ] || exit 1
