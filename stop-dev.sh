#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# GasFlow — Para os serviços iniciados pelo start-dev.sh
#
#   ./stop-dev.sh
#
# Só encerra processos com PID salvo em logs/*.pid — ou seja,
# serviços que ESTE script iniciou. O que estava rodando antes
# (sem pidfile) não é tocado.
# ═══════════════════════════════════════════════════════════════

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

stopped=0
for pidfile in "$LOGS"/*.pid; do
  [ -f "$pidfile" ] || continue
  name="$(basename "$pidfile" .pid)"
  pid="$(cat "$pidfile" 2>/dev/null)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    # taskkill derruba a árvore inteira (npm → node/uvicorn) no Windows
    if command -v taskkill >/dev/null 2>&1; then
      taskkill //F //T //PID "$pid" >/dev/null 2>&1 || kill -9 "$pid" 2>/dev/null
    else
      kill -9 "$pid" 2>/dev/null
    fi
    echo -e "${GREEN}[ok]${NC} $name parado (pid $pid)"
  else
    echo -e "${YELLOW}[skip]${NC} $name não está mais rodando (pid $pid)"
  fi
  rm -f "$pidfile"
  stopped=$((stopped + 1))
done

if [ "$stopped" -eq 0 ]; then
  echo "Nenhum serviço iniciado pelo start-dev.sh está rodando."
else
  echo "Pronto — $stopped serviço(s) parado(s). Logs mantidos em GasFlow/logs/."
fi
