"""
OPS-01A — invariantes de configuração da stack de produção (compose/env/monitoring).

Validação ESTÁTICA (não sobe serviço, não usa Docker daemon):

- O1: todo valor exigido pelo `docker-compose.prod.yml` com `${VAR:?...}`
  existe no `.env.production.example` e é documentado;
- O2: `/metrics` sai autenticado (secret `metrics_key` + Bearer no Prometheus)
  e o nginx da borda responde 404; Alertmanager assina o webhook com secret;
- Perfis: serviços de observabilidade ficam atrás de `--profile observability`
  (perfil Home Server 12 GB — o `up` padrão só sobe o core);
- Limits: a soma dos `deploy.resources.limits` do core cabe em ~4 GB e da
  stack completa em ~5 GB (12 GB de RAM com folra para o SO/docker);
- Volumes: todo diretório gravável dos services tem volume declarado;
- Smoke: `scripts/smoke-test.sh` cobre as regressões M1/O2.

O `docker compose config` roda apenas se o binário `docker` existir no host
(senário de CI local/agent) — com skip explícito quando indisponível.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.production.example"
PROMETHEUS = REPO_ROOT / "monitoring" / "prometheus.yml"
ALERTMANAGER = REPO_ROOT / "monitoring" / "alertmanager.yml"
NGINX_CONF = REPO_ROOT / "frontend" / "nginx.conf"
SMOKE = REPO_ROOT / "scripts" / "smoke-test.sh"

CORE_SERVICES = ("postgres", "redis", "backend", "frontend", "whatsapp")
OBS_SERVICES = ("prometheus", "alertmanager", "grafana")

# 12 GB de RAM: core precisa caber em ~4 GB; a stack completa (core + obs)
# em ~5 GB, deixando ~7 GB para SO, Docker Desktop/Engine e headroom.
CORE_LIMIT_BUDGET_MB = 4096
TOTAL_LIMIT_BUDGET_MB = 5120


def _read(path: Path) -> str:
    assert path.exists(), f"{path.name} ausente"
    return path.read_text(encoding="utf-8")


def _env_vars(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z0-9_.-]+:|\Z)", compose, re.M | re.S)
    assert match, f"service {name!r} ausente no compose"
    return match.group(0)


def _memory_limits(compose: str) -> dict[str, int]:
    limits: dict[str, int] = {}
    current: str | None = None
    for line in compose.splitlines():
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if header:
            current = header.group(1)
            continue
        memory = re.match(r"^\s+memory:\s*(\d+)([MG])\s*$", line)
        if memory and current:
            limits[current] = int(memory.group(1)) * (1024 if memory.group(2) == "G" else 1)
    return limits


# ── O1: variáveis exigidas existem no example ───────────────────────


def test_env_example_declares_every_required_var() -> None:
    compose = _read(COMPOSE)
    required = set(re.findall(r"\$\{([A-Z0-9_]+):\?", compose))
    required.discard("VAR")
    env = _env_vars(_read(ENV_EXAMPLE))
    missing = sorted(var for var in required if var not in env)
    assert not missing, f"variáveis exigidas pelo compose ausentes no example: {missing}"


def test_env_example_metrics_and_passwords_defaults() -> None:
    env = _env_vars(_read(ENV_EXAMPLE))
    assert env["METRICS_PUBLIC"] == "false", "O2: METRICS_PUBLIC precisa ser false no example"
    assert env["ALERTS_WEBHOOK_SECRET"] == "", "segredo do Alertmanager vazio por padrão (fail-closed)"
    for var in ("POSTGRES_PASSWORD", "ADMIN_PASSWORD", "MARCOS_GAS_API_KEY", "GRAFANA_ADMIN_PASSWORD"):
        assert env.get(var, "").startswith("CHANGE_ME"), f"{var} precisa de placeholder CHANGE_ME_*"
    assert env["BACKEND_WORKERS"].isdigit(), "BACKEND_WORKERS documentado (2 workers no Home Server)"


# ── O2: métricas autenticadas na origem e bloqueadas na borda ───────


def test_compose_wires_metrics_secret() -> None:
    compose = _read(COMPOSE)
    secrets = compose[compose.index("\nsecrets:") :]
    assert "metrics_key:" in secrets
    assert "environment: MARCOS_GAS_API_KEY" in secrets
    prometheus = _service_block(compose, "prometheus")
    assert "- metrics_key" in prometheus, "prometheus precisa montar o secret de métricas"
    assert "METRICS_PUBLIC=${METRICS_PUBLIC:-false}" in compose, "default fail-closed no compose"


def test_prometheus_scrapes_with_bearer_credentials_file() -> None:
    text = _read(PROMETHEUS)
    jobs = re.findall(r"- job_name:\s*(\S+)", text)
    assert set(jobs) == {"gasflow-backend", "gasflow-whatsapp"}
    assert text.count("credentials_file: /run/secrets/metrics_key") == len(jobs)
    assert text.count("type: Bearer") == len(jobs)


def test_nginx_returns_404_for_metrics() -> None:
    from tests.test_nginx_routing import route

    conf = _read(NGINX_CONF)
    for url in ("/metrics", "/metrics/", "/api/metrics"):
        assert route(conf, url) == ("404", None), f"{url} precisa morrer na borda"


def test_alertmanager_webhook_secret_is_mounted() -> None:
    compose = _read(COMPOSE)
    alertmanager = _service_block(compose, "alertmanager")
    assert "- alerts_secret" in alertmanager
    secrets = compose[compose.index("\nsecrets:") :]
    assert "environment: ALERTS_WEBHOOK_SECRET" in secrets
    config = _read(ALERTMANAGER)
    assert "credentials_file: /run/secrets/alerts_secret" in config, "webhook assinado com Bearer (fail-closed)"
    assert "send_resolved: true" in config


# ── Perfil Home Server 12 GB ────────────────────────────────────────


def test_observability_behind_profile_observability() -> None:
    compose = _read(COMPOSE)
    for name in OBS_SERVICES:
        block = _service_block(compose, name)
        assert 'profiles: ["observability"]' in block, f"{name} precisa estar atrás do profile"


def test_core_services_have_no_profile() -> None:
    compose = _read(COMPOSE)
    for name in CORE_SERVICES:
        assert "profiles:" not in _service_block(compose, name), f"{name} deve subir no up padrão"


def test_memory_limits_fit_home_server() -> None:
    limits = _memory_limits(_read(COMPOSE))
    for name in (*CORE_SERVICES, *OBS_SERVICES):
        assert name in limits, f"{name} sem deploy.resources.limits"
    core = sum(limits[name] for name in CORE_SERVICES)
    total = sum(limits.values())
    assert core <= CORE_LIMIT_BUDGET_MB, f"core soma {core} MB (limite {CORE_LIMIT_BUDGET_MB} MB)"
    assert total <= TOTAL_LIMIT_BUDGET_MB, f"stack soma {total} MB (limite {TOTAL_LIMIT_BUDGET_MB} MB)"


# ── Persistência: todo diretório gravável tem volume ────────────────

STATEFUL_MOUNTS = {
    "postgres": {"postgres_data": "/var/lib/postgresql/data"},
    "backend": {"backups_data": "/app/backups"},
    "whatsapp": {
        "whatsapp_data": "/app/data",
        "whatsapp_auth": "/app/wwebjs_auth",
        "baileys_auth": "/app/baileys_auth",
        "whatsapp_uploads": "/app/uploads",
        "whatsapp_export": "/app/export",
    },
}


def test_stateful_dirs_have_declared_volumes() -> None:
    compose = _read(COMPOSE)
    declared = set(re.findall(r"^  ([a-z0-9_]+):\n    driver: local", compose, re.M))
    for service, mounts in STATEFUL_MOUNTS.items():
        block = _service_block(compose, service)
        for volume, container_path in mounts.items():
            assert f"- {volume}:{container_path}" in block, f"{service}: {container_path} sem volume"
            assert volume in declared, f"volume {volume} não declarado no topo do compose"


def test_uploads_and_session_dirs_excluded_from_image() -> None:
    """Nada de mídia/sessão do host dentro da imagem (whatsapp/.dockerignore)."""
    dockerignore = _read(REPO_ROOT / "whatsapp" / ".dockerignore")
    for entry in ("data/", "baileys_auth/", "wwebjs_auth/", "uploads/", "export/"):
        assert entry in dockerignore, f"{entry} fora do .dockerignore vai para a imagem"


# ── Smoke pós-deploy cobre M1/O2 ────────────────────────────────────


def test_smoke_script_covers_edge_regressions() -> None:
    text = _read(SMOKE)
    expected = (
        (r'"\$BASE_URL/auth/me"\s+401', "M1: /auth/me raiz responde 401 (não a SPA)"),
        (r'"\$BASE_URL/driver/me"\s+401', "M1: /driver/me raiz responde 401 (não a SPA)"),
        (r'"\$BASE_URL/metrics"\s+404', "O2: /metrics bloqueado na borda"),
        (r'"\$BASE_URL/ready"\s+200', "M1: /ready de readiness via nginx"),
        (r'"\$BASE_URL/api/v1/health"\s+200', "M1: /api/v1/* sem strip no nginx"),
        (r'"\$BASE_URL/api/whatsapp/health"\s+401', "whatsapp /health exige Bearer (antes esperava 200)"),
    )
    for pattern, why in expected:
        assert re.search(pattern, text), f"smoke sem o check: {why}"
    assert '"$BASE_URL/docs"' not in text, "/docs é 404 em produção (DOCS_ENABLED=0) — quebrava o smoke"


# ── Validação real do compose (docker CLI disponível) ───────────────


@pytest.mark.parametrize("args", [(), ("--profile", "observability")])
def test_docker_compose_config_valid(args: tuple[str, ...]) -> None:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker CLI indisponível no host")
    version = subprocess.run([docker, "compose", "version"], capture_output=True, text=True, timeout=60)
    if version.returncode != 0:
        pytest.skip("plugin docker compose indisponível")
    if not ENV_EXAMPLE.exists():
        pytest.skip(".env.production.example ausente")
    proc = subprocess.run(
        [docker, "compose", "-f", str(COMPOSE), "--env-file", str(ENV_EXAMPLE), *args, "config", "--quiet"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"docker compose config falhou:\n{proc.stdout}\n{proc.stderr}"
