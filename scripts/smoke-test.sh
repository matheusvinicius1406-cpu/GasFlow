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
# Docs/root-level via nginx
check "backend docs via nginx"        "$BASE_URL/docs"                     200
# WhatsApp health via backend proxy
check "whatsapp via backend proxy"    "$BASE_URL/api/whatsapp/health"      200

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
