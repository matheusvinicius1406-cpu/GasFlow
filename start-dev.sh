#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# GasFlow — Inicia TUDO com um comando (dev local, sem Docker)
#
#   ./start-dev.sh
#
# O que ele faz:
#   1. Cria o .env de dev se não existir (senhas/ports padrão)
#   2. Instala dependências se faltarem (npm / pip)
#   3. Sobe os 3 serviços em background (logs em logs/):
#        • WhatsApp  → http://localhost:3001  (npm run dev)
#        • Backend   → http://localhost:8000  (uvicorn + SQLite)
#        • Frontend  → http://localhost:5173  (Vite)
#   4. Espera os health checks ficarem verdes
#   5. Abre o navegador (Brave se instalado, senão o padrão)
#
# Serviços que já estão saudáveis são apenas reaproveitados —
# é seguro rodar o script de novo a qualquer momento.
# Para parar tudo: ./stop-dev.sh
# ═══════════════════════════════════════════════════════════════

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[gasflow]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[aviso]${NC} $*"; }
fail()  { echo -e "${RED}[erro]${NC} $*"; }

BACKEND_PORT="${BACKEND_PORT:-8000}"
WHATSAPP_PORT="${WHATSAPP_PORT:-3001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_URL="http://localhost:${BACKEND_PORT}"
WHATSAPP_URL="http://localhost:${WHATSAPP_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

# ── 0. Pré-requisitos ──────────────────────────────────────────
for tool in node npm python curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    fail "Ferramenta obrigatória não encontrada: $tool"
    exit 1
  fi
done

# ── 1. .env de dev (cria se não existir) ───────────────────────
if [ ! -f "$ROOT/.env" ]; then
  info "Criando .env de desenvolvimento (não versionado)…"
  cat > "$ROOT/.env" <<'EOF'
# GasFlow — dev local (gerado por start-dev.sh)
ENVIRONMENT=development
DEBUG=true

# Login do painel (troque se quiser)
ADMIN_PASSWORD=gasflow-dev

# SQLite no dev; Postgres apenas em produção (docker-compose.prod)
DATABASE_URL=sqlite:///./gasflow.db

# WhatsApp service (dev roda na 3001 — a 3000 pode estar ocupada)
WHATSAPP_PORT=3001
WHATSAPP_SERVICE_URL=http://localhost:3001
MARCOS_GAS_API_KEY=

# Frontend usa o proxy do Vite (/api → :8000)
VITE_API_BASE_URL=/api
FRONTEND_PORT=5173

# IA/Áudio em modo mock até configurar Ollama/OpenAI
AI_PROVIDER=mock
STT_PROVIDER=mock
TTS_PROVIDER=mock
EOF
  ok ".env criado (ADMIN_PASSWORD=gasflow-dev)"
fi
# Carrega o .env (comentários e linhas simples KEY=VALUE)
set -a
. "$ROOT/.env" 2>/dev/null
set +a
export ADMIN_PASSWORD WHATSAPP_SERVICE_URL DATABASE_URL WHATSAPP_PORT

# ── Helpers ────────────────────────────────────────────────────
healthy() { # healthy <url>
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null)" = "200" ]
}

wait_for() { # wait_for <nome> <url> <tentativas>
  local name="$1" url="$2" tries="$3" i code
  for ((i = 1; i <= tries; i++)); do
    if healthy "$url"; then return 0; fi
    sleep 3
  done
  return 1
}

deps_ok() { # dependências Python essenciais (rápido o suficiente p/ 1 chamada)
  python -c "import fastapi, uvicorn, sqlalchemy, pydantic" >/dev/null 2>&1
}

# ── 2. Dependências Node ───────────────────────────────────────
if [ ! -d "$ROOT/whatsapp/node_modules" ]; then
  info "Instalando dependências do serviço WhatsApp (npm install)…"
  (cd "$ROOT/whatsapp" && npm install --no-audit --no-fund >>"$LOGS/npm-install.log" 2>&1) \
    && ok "whatsapp: deps instaladas" || fail "npm install do whatsapp falhou (veja logs/npm-install.log)"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  info "Instalando dependências do frontend (npm install)…"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund >>"$LOGS/npm-install.log" 2>&1) \
    && ok "frontend: deps instaladas" || fail "npm install do frontend falhou (veja logs/npm-install.log)"
fi

# ── 3. Sobe os serviços ────────────────────────────────────────
# WhatsApp (:3001)
if healthy "$WHATSAPP_URL/api/health"; then
  ok "WhatsApp já está rodando em $WHATSAPP_URL — reaproveitando"
else
  info "Iniciando serviço WhatsApp na porta $WHATSAPP_PORT…"
  (cd "$ROOT/whatsapp" \
    && PORT="$WHATSAPP_PORT" MARCOS_GAS_API_KEY="${MARCOS_GAS_API_KEY:-}" \
       nohup npm run dev >"$LOGS/whatsapp.log" 2>&1 </dev/null & echo $! >"$LOGS/whatsapp.pid")
fi

# Backend (:8000)
if healthy "$BACKEND_URL/"; then
  ok "Backend já está rodando em $BACKEND_URL — reaproveitando"
else
  if ! deps_ok; then
    info "Dependências Python ausentes — instalando requirements.txt…"
    python -m pip install -r "$ROOT/backend/requirements.txt" >>"$LOGS/pip-install.log" 2>&1 \
      && ok "backend: deps instaladas" || fail "pip install falhou (veja logs/pip-install.log)"
  fi
  info "Iniciando backend (FastAPI) na porta $BACKEND_PORT…"
  (cd "$ROOT/backend" \
    && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
        >"$LOGS/backend.log" 2>&1 </dev/null & echo $! >"$LOGS/backend.pid")
fi

# Frontend (:5173)
if healthy "$FRONTEND_URL/"; then
  ok "Frontend já está rodando em $FRONTEND_URL — reaproveitando"
else
  info "Iniciando frontend (Vite) na porta $FRONTEND_PORT…"
  (cd "$ROOT/frontend" \
    && nohup npm run dev >"$LOGS/frontend.log" 2>&1 </dev/null & echo $! >"$LOGS/frontend.pid")
fi

# ── 4. Health checks ───────────────────────────────────────────
info "Aguardando serviços ficarem prontos (pode levar ~1 min no primeiro start)…"

if wait_for "whatsapp" "$WHATSAPP_URL/api/health" 40; then
  ok "WhatsApp pronto → $WHATSAPP_URL  (QR/conexão: $WHATSAPP_URL/connect)"
else
  fail "WhatsApp não respondeu — veja logs/whatsapp.log"
fi

if wait_for "backend" "$BACKEND_URL/" 60; then
  ok "Backend pronto → $BACKEND_URL  (docs: $BACKEND_URL/docs)"
else
  fail "Backend não respondeu — veja logs/backend.log"
fi

if wait_for "frontend" "$FRONTEND_URL/" 90; then
  ok "Frontend pronto → $FRONTEND_URL"
else
  fail "Frontend não respondeu — veja logs/frontend.log"
fi

# ── 5. Abrir navegador ─────────────────────────────────────────
BRAVE="/c/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"
if healthy "$FRONTEND_URL/"; then
  if [ -x "$BRAVE" ]; then
    "$BRAVE" "$FRONTEND_URL" >/dev/null 2>&1 &
    ok "Abrindo no Brave → $FRONTEND_URL"
  else
    cmd //c start "" "$FRONTEND_URL" >/dev/null 2>&1
    ok "Abrindo no navegador padrão → $FRONTEND_URL"
  fi
else
  warn "Frontend fora do ar — navegador não aberto. Corrija e rode de novo."
fi

# ── Resumo ─────────────────────────────────────────────────────
echo
echo -e "${CYAN}══════════════════════════════════════════════${NC}"
echo -e " GasFlow no ar"
echo -e "   Painel      ${GREEN}$FRONTEND_URL${NC}   (login: admin / ${ADMIN_PASSWORD:-gasflow-dev})"
echo -e "   API + docs  ${GREEN}$BACKEND_URL/docs${NC}"
echo -e "   WhatsApp    ${GREEN}$WHATSAPP_URL/connect${NC} (QR Code)"
echo -e " Logs: ${CYAN}GasFlow/logs/*.log${NC}   Parar: ${CYAN}./stop-dev.sh${NC}"
echo -e "${CYAN}══════════════════════════════════════════════${NC}"
