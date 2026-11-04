#!/usr/bin/env sh
# ═══════════════════════════════════════════════════════════════
# OPS-01B — verificação ESTÁTICA do perfil Home Server + laboratório.
#
# NÃO sobe, NÃO derruba e NÃO migra nada: só roda `docker compose config`
# (interpolação/merge, sem daemon) e confere invariantes do arquivo
# resolvido. Seguro para rodar na máquina que hospeda o GasFlow Desktop.
#
# Uso:
#   ./deploy/home-server/verify-static.sh
#
# Saída: uma linha PASS/FAIL por invariante; exit 1 no primeiro FAIL.
# ═══════════════════════════════════════════════════════════════
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"

PROD=docker-compose.prod.yml
HS=docker-compose.homeserver.yml
LAB=docker-compose.homeserver.lab.yml
ENV_PROD=.env.production.example
ENV_LAB=deploy/home-server/.env.lab.example

for f in "$PROD" "$HS" "$LAB" "$ENV_PROD" "$ENV_LAB"; do
  [ -f "$f" ] || { echo "FAIL arquivo ausente: $f"; exit 1; }
done

command -v docker >/dev/null 2>&1 || { echo "FAIL docker CLI ausente"; exit 1; }

PY=$(command -v python || command -v python3 || true)
[ -n "$PY" ] || { echo "FAIL python ausente (necessário para ler o config JSON)"; exit 1; }

# 1. Os dois modos precisam resolver (com e sem o profile de observabilidade).
docker compose -f "$PROD" -f "$HS" --env-file "$ENV_PROD" config -q
docker compose -f "$PROD" -f "$HS" --profile observability --env-file "$ENV_PROD" config -q
docker compose -p gasflow-hs-lab -f "$PROD" -f "$HS" -f "$LAB" --env-file "$ENV_LAB" config -q
docker compose -p gasflow-hs-lab -f "$PROD" -f "$HS" -f "$LAB" --profile observability --env-file "$ENV_LAB" config -q
echo "PASS compose config -q (perfil real e laboratório, com e sem observabilidade)"

CHECKS=$(cat <<'PY'
import json
import sys

MODE = sys.argv[1]
CORE = ("postgres", "redis", "backend", "frontend", "whatsapp")
OBS = ("prometheus", "alertmanager", "grafana")
CORE_BUDGET_MB = 3072
TOTAL_BUDGET_MB = 3584

doc = json.load(sys.stdin)
services = doc["services"]
errors = []


def fail(msg):
    errors.append(msg)


def mb(value):
    return int(value) // (1024 * 1024)


# ── invariantes comuns aos dois modos ──────────────────────────
for name, svc in services.items():
    log = svc.get("logging") or {}
    opts = log.get("options") or {}
    if log.get("driver") != "json-file" or not opts.get("max-size") or not opts.get("max-file"):
        fail(f"{name}: logging json-file com max-size/max-file ausente")
    if "no-new-privileges:true" not in (svc.get("security_opt") or []):
        fail(f"{name}: security_opt no-new-privileges:true ausente")
    if svc.get("privileged"):
        fail(f"{name}: privileged=true proibido")
    for vol in svc.get("volumes") or []:
        if str(vol.get("source", "")).find("docker.sock") >= 0:
            fail(f"{name}: socket do Docker montado")
    if not (svc.get("healthcheck") or {}).get("test"):
        fail(f"{name}: healthcheck ausente")
    if not (svc.get("deploy") or {}).get("resources", {}).get("limits", {}).get("memory"):
        fail(f"{name}: deploy.resources.limits.memory ausente")

missing = [n for n in (*CORE, *OBS) if n not in services]
if missing:
    fail(f"serviços ausentes no arquivo resolvido: {missing}")

if any("ollama" in n.lower() for n in services):
    fail("perfil não pode depender de IA local (ollama)")

limits = {
    n: mb((services[n].get("deploy") or {}).get("resources", {}).get("limits", {}).get("memory", 0))
    for n in services
}
core = sum(limits[n] for n in CORE if n in limits)
total = sum(limits.values())
if core > CORE_BUDGET_MB:
    fail(f"core soma {core} MB (orçamento {CORE_BUDGET_MB} MB)")
if total > TOTAL_BUDGET_MB:
    fail(f"stack soma {total} MB (orçamento {TOTAL_BUDGET_MB} MB)")

# Todo volume precisa ser resolvido como `<projeto>_<volume>`; um `name:`
# explícito no compose romperia o isolamento entre real e laboratorio.
prefix = f'{doc["name"]}_'
for vol, cfg in (doc.get("volumes") or {}).items():
    resolved = str((cfg or {}).get("name", ""))
    if not resolved.startswith(prefix):
        fail(f"volume {vol}: nome resolvido {resolved!r} fora do prefixo {prefix!r}")

# Nenhuma porta publicada pode ser o backend (:8000 do GasFlow Desktop).
for name, svc in services.items():
    for port in svc.get("ports") or []:
        if int(port.get("published", 0)) in (8000, 3000, 5432, 6379, 9090):
            fail(f"{name}: porta interna publicada no host ({port.get('published')})")

# ── perfil real: só o frontend publica porta ───────────────────
if MODE == "real":
    publishing = {n: s.get("ports") or [] for n, s in services.items() if s.get("ports")}
    if list(publishing) != ["frontend"]:
        fail(f"perfil real publica portas em {sorted(publishing)} (só frontend pode)")
    for port in publishing.get("frontend", []):
        if port.get("host_ip") not in (None, "", "0.0.0.0") or str(port.get("published")) != "80":
            fail(f"frontend: esperado 0.0.0.0:80, veio {port.get('host_ip')}:{port.get('published')}")
    print(f"PASS perfil real: somente 0.0.0.0:80 (frontend); core {core} MB / total {total} MB")

# ── laboratório: projeto, containers, porta loopback e restart ─
if MODE == "lab":
    if doc.get("name") != "gasflow-hs-lab":
        fail(f"projeto do laboratório deveria ser gasflow-hs-lab (veio {doc.get('name')})")
    db_url = str((services.get("backend", {}).get("environment") or {}).get("DATABASE_URL", ""))
    if not db_url.startswith("postgresql") or "@postgres:5432/gasflow_lab" not in db_url:
        fail("backend do laboratório deve apontar para postgres:5432/gasflow_lab")
    if "sqlite" in db_url.lower() or "outside.invalid" in db_url:
        fail("backend do laboratório não pode apontar para SQLite ou outro host")
    for name, svc in services.items():
        cname = svc.get("container_name") or ""
        if not cname.startswith("gasflow-hs-lab-"):
            fail(f"{name}: container_name fora do prefixo do laboratorio ({cname!r})")
        if svc.get("restart") != "no":
            fail(f"{name}: laboratorio deve usar restart \"no\" (veio {svc.get('restart')!r})")
    publishing = {n: s.get("ports") or [] for n, s in services.items() if s.get("ports")}
    if list(publishing) != ["frontend"]:
        fail(f"laboratorio publica portas em {sorted(publishing)} (somente frontend pode)")
    for port in publishing.get("frontend", []):
        if port.get("host_ip") != "127.0.0.1" or str(port.get("published")) != "8088":
            fail(f"laboratorio: esperado 127.0.0.1:8088, veio {port.get('host_ip')}:{port.get('published')}")
    wa_env = services["whatsapp"].get("environment") or {}
    if str(wa_env.get("WA_BROADCAST_ENABLED")).lower() != "false":
        fail("laboratorio: WA_BROADCAST_ENABLED precisa ser false")
    for secret, cfg in (doc.get("secrets") or {}).items():
        if not str((cfg or {}).get("name", "")).startswith("gasflow-hs-lab_"):
            fail(f"secret {secret}: nome fora do projeto do laboratorio")
    print("PASS laboratorio: projeto gasflow-hs-lab, containers -lab, 127.0.0.1:8088, restart no")

for message in errors:
    print(f"FAIL {message}")
sys.exit(1 if errors else 0)
PY
)

# 2. Perfil real (observabilidade ligada para validar também os 3 serviços dela).
docker compose -f "$PROD" -f "$HS" --profile observability --env-file "$ENV_PROD" \
  config --format json | "$PY" -c "$CHECKS" real

# 3. Laboratório isolado.
docker compose -p gasflow-hs-lab -f "$PROD" -f "$HS" -f "$LAB" --profile observability --env-file "$ENV_LAB" \
  config --format json | "$PY" -c "$CHECKS" lab

# 4. O env real do laboratório não pode estar versionado.
if git ls-files --error-unmatch deploy/home-server/.env.lab >/dev/null 2>&1; then
  echo "FAIL deploy/home-server/.env.lab está versionado (vazaria segredos)"
  exit 1
fi
echo "PASS segredos: .env.lab fora do git; placeholders fictícios no template"

if [ -f deploy/home-server/.env.lab ]; then
  "$PY" - deploy/home-server/.env.lab <<'PY'
import sys
import re
from pathlib import Path

values = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, _, value = stripped.partition("=")
    values[key.strip()] = value.strip()

keys = (
    "POSTGRES_PASSWORD",
    "ADMIN_PASSWORD",
    "MARCOS_GAS_API_KEY",
    "GASFLOW_SERVICE_KEY",
    "ALERTS_WEBHOOK_SECRET",
    "GRAFANA_ADMIN_PASSWORD",
)
credentials = [values.get(key, "") for key in keys]
for key, value in zip(keys, credentials):
    cryptographic_hex = re.fullmatch(r"[0-9a-f]{64}", value) is not None
    diverse_value = len(value) >= 32 and len(set(value)) >= 16
    if not (cryptographic_hex or diverse_value) or value.startswith("CHANGE_ME_lab_"):
        print(f"FAIL .env.lab: {key} precisa de credencial forte e exclusiva")
        sys.exit(1)
if values.get("GASFLOW_SERVICE_KEY") != values.get("MARCOS_GAS_API_KEY"):
    print("FAIL .env.lab: a chave compartilhada backend/WhatsApp precisa ser igual")
    sys.exit(1)
independent = [
    values[key]
    for key in keys
    if key not in {"MARCOS_GAS_API_KEY", "GASFLOW_SERVICE_KEY"}
]
if len(set(independent)) != len(independent):
    print("FAIL .env.lab: credenciais independentes precisam ser distintas")
    sys.exit(1)
PY
  echo "PASS segredos: credenciais locais fortes; chave backend/WhatsApp compartilhada corretamente"
else
  echo "SKIP credenciais locais: deploy/home-server/.env.lab ausente"
fi

echo "OK — perfil Home Server e laboratório válidos (nada foi iniciado)"
