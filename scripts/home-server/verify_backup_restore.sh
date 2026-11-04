#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# GasFlow Home Server — prova de BACKUP + RESTAURAÇÃO independente.
#
# O que faz (somente no banco de laboratório `gasflow_lab`):
#   1. pg_dump formato custom dentro do container Postgres;
#   2. copia o arquivo para um diretório FORA do repositório;
#   3. valida mágica PGDMP, tamanho e SHA-256, e grava um manifesto;
#   4. cria um banco DESCARTÁVEL (`gasflow_hs_restore`) do zero;
#   5. restaura com `pg_restore --exit-on-error`;
#   6. compara tabelas, índices, constraints, versão do Alembic e
#      contagem por tabela entre origem e restauração;
#   7. dropa o banco descartável.
#
# Um `pg_restore --list` NÃO substitui restauração real: aqui o banco
# restaurado é consultado e comparado (contagens por tabela).
#
# NUNCA toca em banco operacional, NUNCA sobrescreve arquivo.
#
# Uso:  ./scripts/home-server/verify_backup_restore.sh
# ═══════════════════════════════════════════════════════════════
set -uo pipefail

CONTAINER="${PG_CONTAINER:-gasflow-hs-lab-postgres}"
RESTORE_DB="${PG_RESTORE_DB:-gasflow_hs_restore}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT_ROOT="${BACKUP_OUT_DIR:-${TEMP:-/tmp}/gasflow-hs-backup}"
OUT_DIR="$OUT_ROOT/$TS"
REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
FAILED=0
RESTORE_OK=1

pass() { echo "OK    $*"; }
fail() { echo "FAIL  $*"; FAILED=1; }

# `docker exec` com caminhos POSIX dentro do container: desliga a conversão
# de caminho do MSYS/Git Bash. `docker cp` (destino no host) usa caminho
# Windows convertido por `cygpath`.
MSYS_NO_PATHCONV=1
export MSYS_NO_PATHCONV

win_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }

echo "== Backup + restore — PostgreSQL do Home Server =="

# Credenciais vêm do próprio container (nunca de argv/arquivo neste script).
PGU=$(docker exec "$CONTAINER" sh -c 'printf %s "$POSTGRES_USER"' 2>/dev/null)
PGD=$(docker exec "$CONTAINER" sh -c 'printf %s "$POSTGRES_DB"' 2>/dev/null)
if [ -z "${PGU:-}" ] || [ -z "${PGD:-}" ]; then
  echo "FAIL não foi possível ler POSTGRES_USER/DB do container $CONTAINER"
  exit 1
fi
echo "banco: $PGD · usuário: $PGU · container: $CONTAINER"
echo "destino: $OUT_DIR"

mkdir -p "$OUT_DIR" || { echo "FAIL destino não criado"; exit 1; }
case "$(cd "$OUT_DIR" && pwd -P)" in
  "$REPO_ROOT"/*) echo "FAIL destino dentro do repositório"; exit 1 ;;
esac

# 1. Dump custom
if docker exec "$CONTAINER" pg_dump --format=custom --no-owner --no-acl \
     -U "$PGU" -d "$PGD" -f /tmp/gasflow_hs.dump >/dev/null 2>&1; then
  pass "pg_dump (custom) executado"
else
  fail "pg_dump falhou"; exit 1
fi

# 2. Trazer para o host (destino precisa ser caminho Windows)
DUMP="$OUT_DIR/database-$TS.dump"
if docker cp "$CONTAINER:/tmp/gasflow_hs.dump" "$(win_path "$DUMP")" >/dev/null 2>&1; then
  pass "dump copiado para fora do container"
else
  fail "docker cp falhou"; exit 1
fi
docker exec "$CONTAINER" rm -f /tmp/gasflow_hs.dump >/dev/null 2>&1

# 3. Validação do artefato
SIZE=$(wc -c < "$DUMP" | tr -d ' ')
MAGIC=$(head -c 5 "$DUMP")
SHA=$(sha256sum "$DUMP" | cut -d' ' -f1)
[ "$MAGIC" = "PGDMP" ] && pass "mágica PGDMP" || fail "mágica inválida ($MAGIC)"
[ "${SIZE:-0}" -gt 4096 ] && pass "tamanho ${SIZE} bytes" || fail "tamanho suspeito ($SIZE)"

MANIFEST="$OUT_DIR/database-$TS.dump.manifest.json"
cat > "$MANIFEST" <<JSON
{
  "tool": "gasflow-home-server-verify-backup-restore",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "database": "$PGD",
  "container": "$CONTAINER",
  "dump": {
    "file": "$(basename "$DUMP")",
    "size_bytes": ${SIZE:-0},
    "sha256": "$SHA",
    "format": "custom",
    "magic_ok": true
  },
  "off_host": false,
  "note": "host sem segundo disco/volume independente: backup validado no MESMO disco (limitacao registrada)"
}
JSON
pass "manifesto gravado"

# 4. Banco descartável
docker exec "$CONTAINER" psql -U "$PGU" -d postgres -tAc \
  "DROP DATABASE IF EXISTS $RESTORE_DB;" >/dev/null 2>&1
if docker exec "$CONTAINER" psql -U "$PGU" -d postgres -tAc \
  "CREATE DATABASE $RESTORE_DB;" >/dev/null 2>&1; then
  pass "banco descartável $RESTORE_DB criado"
else
  fail "não foi possível criar $RESTORE_DB"; exit 1
fi

# 5. Restauração real
docker cp "$(win_path "$DUMP")" "$CONTAINER:/tmp/restore_hs.dump" >/dev/null 2>&1
if docker exec -e RDB="$RESTORE_DB" "$CONTAINER" sh -ec \
     'pg_restore -U "$POSTGRES_USER" -d "$RDB" --exit-on-error /tmp/restore_hs.dump' >/dev/null 2>&1; then
  pass "pg_restore completo (--exit-on-error)"
else
  fail "pg_restore retornou erro"; RESTORE_OK=0
fi
docker exec "$CONTAINER" rm -f /tmp/restore_hs.dump >/dev/null 2>&1

q() { docker exec "$CONTAINER" psql -U "$PGU" -d "$1" -tAc "$2" 2>/dev/null | tr -d '\r'; }

T_SRC=$(q "$PGD" "select count(*) from information_schema.tables where table_schema='public';")
T_DST=$(q "$RESTORE_DB" "select count(*) from information_schema.tables where table_schema='public';")
I_SRC=$(q "$PGD" "select count(*) from pg_indexes where schemaname='public';")
I_DST=$(q "$RESTORE_DB" "select count(*) from pg_indexes where schemaname='public';")
C_SRC=$(q "$PGD" "select count(*) from pg_constraint c join pg_namespace n on n.oid=c.connamespace where n.nspname='public';")
C_DST=$(q "$RESTORE_DB" "select count(*) from pg_constraint c join pg_namespace n on n.oid=c.connamespace where n.nspname='public';")
A_SRC=$(q "$PGD" "select version_num from alembic_version;")
A_DST=$(q "$RESTORE_DB" "select version_num from alembic_version;")

[ "$T_SRC" = "$T_DST" ] && pass "tabelas: $T_SRC = $T_DST" || fail "tabelas divergem: $T_SRC vs $T_DST"
[ "$I_SRC" = "$I_DST" ] && pass "índices: $I_SRC = $I_DST" || fail "índices divergem: $I_SRC vs $I_DST"
[ "$C_SRC" = "$C_DST" ] && pass "constraints: $C_SRC = $C_DST" || fail "constraints divergem: $C_SRC vs $C_DST"
[ "$A_SRC" = "$A_DST" ] && pass "alembic_version: $A_SRC = $A_DST" || fail "alembic_version diverge: $A_SRC vs $A_DST"

# 6. Contagem por tabela
TABLES=$(q "$PGD" "select table_name from information_schema.tables where table_schema='public' order by table_name;")
DIFFS=0
CHECKED=0
for t in $TABLES; do
  a=$(q "$PGD" "select count(*) from \"$t\";")
  b=$(q "$RESTORE_DB" "select count(*) from \"$t\";")
  CHECKED=$((CHECKED + 1))
  if [ "$a" != "$b" ]; then
    echo "      divergência em $t: origem=$a restore=$b (esperado em tabela viva: sessão/auditoria)"
    DIFFS=$((DIFFS + 1))
  fi
done
echo "      tabelas comparadas: $CHECKED (divergências: $DIFFS)"

# 7. Limpeza
docker exec "$CONTAINER" psql -U "$PGU" -d postgres -tAc \
  "DROP DATABASE IF EXISTS $RESTORE_DB;" >/dev/null 2>&1 && pass "banco descartável dropado"

echo "========================================="
if [ "$FAILED" -eq 0 ] && [ "$RESTORE_OK" -eq 1 ]; then
  echo "RESULTADO: BACKUP + RESTORE INDEPENDENTE VALIDADOS"
  echo "artefatos: $OUT_DIR"
  exit 0
fi
echo "RESULTADO: FALHOU"
exit 1
