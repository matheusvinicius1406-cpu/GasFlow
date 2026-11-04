"""
OPS-01B — perfil Home Server e laboratório isolado (validação ESTÁTICA).

Não sobe container, não usa o daemon e não toca em banco: o único processo
externo é `docker compose config`, que apenas interpola/mergeia os arquivos.

Invariantes cobertas:

- Perfil aditivo: o overlay `docker-compose.homeserver.yml` não cria serviço,
  não troca imagem e não publica porta nova (só o frontend, herdado do prod);
- Orçamento: core ≤ 3 GB e stack com observabilidade ≤ 3,5 GB (12 GB de host,
  dividido com Windows 11 + GasFlow Desktop), com teto de CPU por serviço;
- Rotação de logs (`json-file` 10 MB × 3), healthcheck com `start_period` e
  `no-new-privileges` em todos os serviços; nenhum `privileged`/docker socket;
- Persistência: volumes com os MESMOS nomes do prod (sem renomear) e todas as
  montagens graváveis (`postgres_data`, sessões Baileys, uploads, export,
  backups) preservadas;
- Observabilidade estritamente opcional (`--profile observability`) e métricas
  nunca públicas;
- Laboratório: projeto `gasflow-hs-lab`, containers `-lab`, volumes/rede/segredos
  prefixados, única porta `127.0.0.1:8088` e `restart: "no"` — sem conflito com
  `:80`, `127.0.0.1:8000` (GasFlow Desktop) ou sessões WhatsApp reais;
- Segredos: template do laboratório só com placeholders fictícios e `.env.lab`
  fora do git.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD = REPO_ROOT / "docker-compose.prod.yml"
HOMESERVER = REPO_ROOT / "docker-compose.homeserver.yml"
LAB = REPO_ROOT / "docker-compose.homeserver.lab.yml"
ENV_PROD = REPO_ROOT / ".env.production.example"
ENV_LAB = REPO_ROOT / "deploy" / "home-server" / ".env.lab.example"
ENV_LAB_REAL = REPO_ROOT / "deploy" / "home-server" / ".env.lab"
README = REPO_ROOT / "deploy" / "home-server" / "README.md"
VERIFY = REPO_ROOT / "deploy" / "home-server" / "verify-static.sh"

CORE_SERVICES = ("postgres", "redis", "backend", "frontend", "whatsapp")
OBS_SERVICES = ("prometheus", "alertmanager", "grafana")
ALL_SERVICES = CORE_SERVICES + OBS_SERVICES

# Host: 12 GB RAM. Windows 11 (~4 GB) + core do compose precisa deixar folga.
CORE_LIMIT_BUDGET_MB = 3072
TOTAL_LIMIT_BUDGET_MB = 3584

LAB_PROJECT = "gasflow-hs-lab"
LAB_FRONTEND_PORT = 8088
# Portas internas que NUNCA podem aparecer publicadas no host por este perfil.
FORBIDDEN_PUBLISHED_PORTS = {3000, 3001, 5432, 6379, 8000, 8080, 9090, 9093}

_CACHE: dict[tuple[str, ...], dict[str, Any]] = {}


def _read(path: Path) -> str:
    assert path.exists(), f"{path.name} ausente"
    return path.read_text(encoding="utf-8")


def _compose_config(files: tuple[Path, ...], env_file: Path, profiles: tuple[str, ...] = ()) -> dict[str, Any]:
    """`docker compose config --format json` (sem daemon) para os arquivos dados."""
    cache_key = (*(str(f) for f in files), str(env_file), *profiles)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker CLI indisponível no host")
    command = [docker, "compose"]
    if LAB in files:
        command += ["-p", LAB_PROJECT]
    for file in files:
        command += ["-f", str(file)]
    for profile in profiles:
        command += ["--profile", profile]
    command += ["--env-file", str(env_file), "config", "--format", "json"]

    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f"docker compose config falhou:\n{proc.stdout}\n{proc.stderr}"
    document = json.loads(proc.stdout)
    _CACHE[cache_key] = document
    return document


def _prod() -> dict[str, Any]:
    return _compose_config((PROD,), ENV_PROD, ("observability",))


def _homeserver() -> dict[str, Any]:
    return _compose_config((PROD, HOMESERVER), ENV_PROD, ("observability",))


def _lab() -> dict[str, Any]:
    return _compose_config((PROD, HOMESERVER, LAB), ENV_LAB, ("observability",))


def _limits(service: dict[str, Any]) -> dict[str, Any]:
    return ((service.get("deploy") or {}).get("resources") or {}).get("limits") or {}


def _memory_mb(service: dict[str, Any]) -> int:
    return int(_limits(service).get("memory", 0)) // (1024 * 1024)


def _published_ports(service: dict[str, Any]) -> list[dict[str, Any]]:
    return service.get("ports") or []


def _env_vars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in _read(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


# ── Validade e composição dos arquivos ───────────────────────────


def test_profile_files_exist() -> None:
    for path in (HOMESERVER, LAB, ENV_LAB, README, VERIFY):
        assert path.exists(), f"{path} ausente"


@pytest.mark.parametrize(
    ("files", "env_file"),
    [
        ((PROD, HOMESERVER), ENV_PROD),
        ((PROD, HOMESERVER, LAB), ENV_LAB),
    ],
)
def test_compose_config_quiet_is_valid(files: tuple[Path, ...], env_file: Path) -> None:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker CLI indisponível no host")
    command = [docker, "compose"]
    for file in files:
        command += ["-f", str(file)]
    command += ["--env-file", str(env_file), "config", "--quiet"]
    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f"docker compose config falhou:\n{proc.stdout}\n{proc.stderr}"


def test_homeserver_overlay_is_additive() -> None:
    """Só mexe no que já existe: nenhum serviço/imagem/porta nova."""
    prod = _prod()
    homeserver = _homeserver()
    assert set(homeserver["services"]) == set(prod["services"]), "overlay não pode criar serviço"
    text = _read(HOMESERVER)
    for name in ALL_SERVICES:
        block = re.search(rf"^  {name}:\n(.*?)(?=^  [A-Za-z0-9_.-]+:|\Z)", text, re.M | re.S)
        assert block, f"serviço {name} ausente do overlay"
        assert not re.search(r"^\s+image:", block.group(0), re.M), f"{name}: overlay não troca imagem"
        assert not re.search(r"^\s+ports:", block.group(0), re.M), f"{name}: overlay não abre porta"


def test_profile_has_no_local_ai_dependency() -> None:
    """IA local (Ollama) não é serviço obrigatório deste perfil."""
    for document in (_prod(), _homeserver()):
        for name, service in document["services"].items():
            assert "ollama" not in name.lower()
            assert "ollama" not in str(service.get("image", "")).lower()
    overlay = _read(HOMESERVER)
    assert not re.search(r"^\s+ollama:", overlay, re.M), "overlay não pode declarar serviço de IA local"
    assert "AI_PROVIDER=mock" in _read(ENV_LAB)


def test_observability_stays_optional() -> None:
    homeserver = _homeserver()
    for name in OBS_SERVICES:
        assert homeserver["services"][name].get("profiles") == ["observability"], f"{name} saiu do profile"
    for name in CORE_SERVICES:
        assert not homeserver["services"][name].get("profiles"), f"{name} virou opcional"


# ── Orçamento de RAM/CPU ────────────────────────────────────────


def test_memory_limits_fit_the_home_server() -> None:
    homeserver = _homeserver()
    for name in ALL_SERVICES:
        assert _memory_mb(homeserver["services"][name]) > 0, f"{name} sem limite de memória"
    core = sum(_memory_mb(homeserver["services"][name]) for name in CORE_SERVICES)
    total = sum(_memory_mb(homeserver["services"][name]) for name in ALL_SERVICES)
    assert core <= CORE_LIMIT_BUDGET_MB, f"core soma {core} MB (orçamento {CORE_LIMIT_BUDGET_MB} MB)"
    assert total <= TOTAL_LIMIT_BUDGET_MB, f"stack soma {total} MB (orçamento {TOTAL_LIMIT_BUDGET_MB} MB)"


def test_every_service_has_cpu_cap() -> None:
    homeserver = _homeserver()
    for name in ALL_SERVICES:
        cpus = float(_limits(homeserver["services"][name]).get("cpus") or 0)
        assert 0 < cpus <= 2, f"{name}: teto de CPU ausente ou absurdo ({cpus})"


def test_postgres_keeps_shm_for_slow_disk() -> None:
    postgres = _homeserver()["services"]["postgres"]
    assert int(postgres.get("shm_size") or 0) >= 128 * 1024 * 1024, "Postgres no HDD precisa de /dev/shm explícito"
    assert str(postgres.get("stop_grace_period")) == "1m0s", "checkpoint precisa de grace period"


# ── Logs, saúde e privilégios ───────────────────────────────────


def test_every_service_rotates_logs() -> None:
    homeserver = _homeserver()
    for name in ALL_SERVICES:
        logging_config = homeserver["services"][name].get("logging") or {}
        options = logging_config.get("options") or {}
        assert logging_config.get("driver") == "json-file", f"{name}: driver de log inesperado"
        assert options.get("max-size") == "10m", f"{name}: max-size ausente"
        assert str(options.get("max-file")) == "3", f"{name}: max-file ausente"


def test_every_service_has_healthcheck_with_start_period() -> None:
    homeserver = _homeserver()
    for name in ALL_SERVICES:
        healthcheck = homeserver["services"][name].get("healthcheck") or {}
        assert healthcheck.get("test"), f"{name}: healthcheck ausente"
        assert healthcheck.get("start_period"), f"{name}: healthcheck sem start_period"


def test_containers_never_gain_privileges_or_docker_socket() -> None:
    homeserver = _homeserver()
    for name in ALL_SERVICES:
        service = homeserver["services"][name]
        assert not service.get("privileged"), f"{name}: privileged não é permitido"
        assert "no-new-privileges:true" in (service.get("security_opt") or []), f"{name}: sem no-new-privileges"
        assert service.get("user") != "0", f"{name}: não deve forçar root"
        for volume in service.get("volumes") or []:
            assert "docker.sock" not in str(volume.get("source", "")), f"{name}: socket do Docker montado"


def test_restart_policy_is_server_grade() -> None:
    homeserver = _homeserver()
    for name in ALL_SERVICES:
        assert homeserver["services"][name].get("restart") == "unless-stopped", f"{name}: restart inesperado"


# ── Exposição de portas ─────────────────────────────────────────


def test_only_frontend_is_published_on_the_server() -> None:
    homeserver = _homeserver()
    publishing = {name: _published_ports(service) for name, service in homeserver["services"].items()}
    publishing = {name: ports for name, ports in publishing.items() if ports}
    assert set(publishing) == {"frontend"}, f"portas publicadas em {sorted(publishing)}"
    for port in publishing["frontend"]:
        assert port.get("host_ip") in (None, "", "0.0.0.0"), "frontend deve escutar na LAN"
        assert str(port.get("published")) == "80", "única porta pública do perfil é a 80"


def test_internal_ports_are_never_published() -> None:
    documents = (_prod(), _homeserver(), _lab())
    for document in documents:
        for name, service in document["services"].items():
            for port in _published_ports(service):
                published = int(str(port.get("published", 0)))
                assert published not in FORBIDDEN_PUBLISHED_PORTS or name == "frontend", (
                    f"{name}: porta interna {published} não pode ser publicada"
                )


def test_metrics_never_public() -> None:
    homeserver = _homeserver()
    backend_env = homeserver["services"]["backend"].get("environment") or {}
    whatsapp_env = homeserver["services"]["whatsapp"].get("environment") or {}
    assert str(backend_env.get("METRICS_PUBLIC")).lower() == "false"
    assert str(whatsapp_env.get("METRICS_PUBLIC")).lower() == "false"
    assert not _published_ports(homeserver["services"]["prometheus"])


# ── Persistência ────────────────────────────────────────────────


def test_volume_names_are_unchanged_from_production() -> None:
    """Renomear volume = perder dados; o perfil precisa manter os nomes."""
    prod_volumes = _prod().get("volumes") or {}
    homeserver_volumes = _homeserver().get("volumes") or {}
    assert set(homeserver_volumes) == set(prod_volumes)
    for name, config in homeserver_volumes.items():
        assert config.get("name") == prod_volumes[name].get("name"), f"volume {name} renomeado"


def test_persistent_mounts_are_preserved() -> None:
    expected = {
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
    homeserver = _homeserver()
    for service_name, required in expected.items():
        mounted = homeserver["services"][service_name].get("volumes") or []
        actual = {volume.get("source"): volume.get("target") for volume in mounted}
        for volume, target in required.items():
            assert actual.get(volume) == target, f"{service_name}: {volume} → {target} perdido"


def test_redis_stays_ephemeral_by_design() -> None:
    redis = _homeserver()["services"]["redis"]
    assert not redis.get("volumes"), "Redis não persiste rate limit (decisão documentada)"
    assert "redis" in _read(README).lower()
    assert "efêmer" in _read(README).lower()


def test_secrets_are_environment_backed_and_project_scoped() -> None:
    homeserver = _homeserver()
    secrets = homeserver.get("secrets") or {}
    assert set(secrets) == {"metrics_key", "alerts_secret"}
    assert secrets["metrics_key"].get("environment") == "MARCOS_GAS_API_KEY"
    assert secrets["alerts_secret"].get("environment") == "ALERTS_WEBHOOK_SECRET"
    assert [item.get("source") for item in homeserver["services"]["prometheus"].get("secrets") or []] == ["metrics_key"]
    assert [item.get("source") for item in homeserver["services"]["alertmanager"].get("secrets") or []] == [
        "alerts_secret"
    ]
    for name, config in secrets.items():
        assert config.get("file") is None, f"{name}: segredo em arquivo versionado"


# ── Laboratório isolado ─────────────────────────────────────────


def test_lab_uses_its_own_compose_project() -> None:
    lab = _lab()
    assert lab.get("name") == LAB_PROJECT
    prefix = f"{LAB_PROJECT}_"
    for name, service in lab["services"].items():
        assert (service.get("container_name") or "").startswith(f"{LAB_PROJECT}-"), f"{name}: container fora do projeto"
    for volume_name, volume in (lab.get("volumes") or {}).items():
        assert str(volume.get("name", "")).startswith(prefix), f"volume {volume_name} fora do projeto"
    for secret_name, secret in (lab.get("secrets") or {}).items():
        assert str(secret.get("name", "")).startswith(prefix), f"secret {secret_name} fora do projeto"
    for network in (lab.get("networks") or {}).values():
        assert str(network.get("name", "")).startswith(prefix), "rede fora do projeto"


def test_lab_publishes_only_loopback_high_port() -> None:
    lab = _lab()
    publishing = {name: _published_ports(service) for name, service in lab["services"].items()}
    publishing = {name: ports for name, ports in publishing.items() if ports}
    assert set(publishing) == {"frontend"}
    ports = publishing["frontend"]
    assert len(ports) == 1, "laboratório deve publicar uma única porta"
    assert ports[0].get("host_ip") == "127.0.0.1", "laboratório não pode escutar na LAN"
    assert int(str(ports[0].get("published"))) == LAB_FRONTEND_PORT
    # Não pode colidir com o GasFlow Desktop (127.0.0.1:8000) nem com :80.
    assert int(str(ports[0].get("published"))) not in (80, 8000)


def test_lab_does_not_auto_restart() -> None:
    lab = _lab()
    for name, service in lab["services"].items():
        assert str(service.get("restart")).lower() in {"no", "false"}, f"{name}: laboratório não deve reiniciar sozinho"


def test_lab_disables_whatsapp_broadcast_and_critical_webhook() -> None:
    """Laboratório nunca dispara campanha nem chama webhook do ambiente real."""
    whatsapp_env = _lab()["services"]["whatsapp"].get("environment") or {}
    assert str(whatsapp_env.get("WA_SEND_MODE")).lower() == "dry-run"
    assert str(whatsapp_env.get("WA_BROADCAST_ENABLED")).lower() == "false"
    assert not whatsapp_env.get("WA_CRITICAL_WEBHOOK_URL")
    assert str(whatsapp_env.get("ALLOW_INSECURE_AUTH")).lower() == "false"


def test_lab_reuses_paths_but_not_volumes() -> None:
    """Mesmos caminhos de sessão/upload, mas em volumes do projeto do lab."""
    lab = _lab()
    homeserver = _homeserver()
    lab_mounts = {volume.get("source"): volume.get("target") for volume in lab["services"]["whatsapp"]["volumes"]}
    hs_mounts = {volume.get("source"): volume.get("target") for volume in homeserver["services"]["whatsapp"]["volumes"]}
    assert lab_mounts == hs_mounts, "o laboratório deve montar os mesmos caminhos"
    assert lab.get("name") == LAB_PROJECT != homeserver.get("name"), "projeto do lab precisa ser distinto"
    for volume in (lab.get("volumes") or {}).values():
        assert str(volume.get("name", "")).startswith(f"{LAB_PROJECT}_")


def test_lab_backend_runs_single_worker() -> None:
    command = " ".join(_lab()["services"]["backend"].get("command") or [])
    assert "--workers 1" in command, f"laboratório deve rodar 1 worker (comando: {command!r})"


# ── Template de variáveis do laboratório ────────────────────────


def test_lab_env_template_is_fictional_and_sized_for_two_cores() -> None:
    env = _env_vars(ENV_LAB)
    for key in (
        "POSTGRES_PASSWORD",
        "ADMIN_PASSWORD",
        "MARCOS_GAS_API_KEY",
        "GRAFANA_ADMIN_PASSWORD",
        "ALERTS_WEBHOOK_SECRET",
    ):
        assert env.get(key, "").startswith("CHANGE_ME_lab"), f"{key} precisa de placeholder fictício"
    assert env["POSTGRES_DB"] == "gasflow_lab"
    assert "gasflow_lab" in env["DATABASE_URL"]
    assert env["BACKEND_WORKERS"] == "1", "i3-10110U (2C/4T) → 1 worker"
    assert str(LAB_FRONTEND_PORT) in env["CORS_ORIGINS"]
    assert "FRONTEND_PORT" not in env, "a porta do laboratório é fixa no overlay, não configurável pelo env"
    frontend_ports = _published_ports(_lab()["services"]["frontend"])
    assert len(frontend_ports) == 1
    assert frontend_ports[0].get("host_ip") == "127.0.0.1"
    assert int(str(frontend_ports[0].get("published"))) == LAB_FRONTEND_PORT
    assert env["METRICS_PUBLIC"] == "false"
    assert env["ENVIRONMENT"] == "production", "laboratório valida a semântica de produção"


def test_local_lab_env_uses_strong_credentials_with_shared_service_key_when_present() -> None:
    """O arquivo local deve usar segredos fortes; valores fictícios ficam só no template."""
    if not ENV_LAB_REAL.exists():
        return

    env = _env_vars(ENV_LAB_REAL)
    credential_keys = (
        "POSTGRES_PASSWORD",
        "ADMIN_PASSWORD",
        "MARCOS_GAS_API_KEY",
        "GASFLOW_SERVICE_KEY",
        "ALERTS_WEBHOOK_SECRET",
        "GRAFANA_ADMIN_PASSWORD",
    )
    credentials = [env.get(key, "") for key in credential_keys]
    for key, credential in zip(credential_keys, credentials, strict=True):
        cryptographic_hex = re.fullmatch(r"[0-9a-f]{64}", credential) is not None
        diverse_value = len(credential) >= 32 and len(set(credential)) >= 16
        assert cryptographic_hex or diverse_value, f"{key} precisa ser uma credencial forte"
        assert not credential.startswith("CHANGE_ME_lab_"), f"{key} ainda é placeholder"
    assert env["GASFLOW_SERVICE_KEY"] == env["MARCOS_GAS_API_KEY"], (
        "a chave compartilhada backend/WhatsApp precisa ser igual nos dois serviços"
    )
    independent_credentials = [
        env[key] for key in credential_keys if key not in {"MARCOS_GAS_API_KEY", "GASFLOW_SERVICE_KEY"}
    ]
    assert len(set(independent_credentials)) == len(independent_credentials), (
        "credenciais independentes do laboratório precisam ser exclusivas"
    )


def test_lab_env_file_is_gitignored() -> None:
    gitignore = _read(REPO_ROOT / ".gitignore")
    assert "deploy/home-server/.env.lab" in gitignore.splitlines()


def test_prod_env_template_documents_home_server_profile() -> None:
    text = _read(ENV_PROD)
    assert "Home Server (OPS-01B)" in text
    assert "# BACKEND_WORKERS=1" in text
    assert "docker-compose.homeserver.yml" in text


# ── Segredos e higiene dos arquivos novos ───────────────────────

NEW_FILES = (HOMESERVER, LAB, ENV_LAB, README, VERIFY)
SECRET_PATTERNS = (
    r"BEGIN [A-Z ]*PRIVATE KEY",
    r"ghp_[A-Za-z0-9]{20,}",
    r"sk-[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.",
)


def test_new_files_carry_no_credential_material() -> None:
    for path in NEW_FILES:
        text = _read(path)
        for pattern in SECRET_PATTERNS:
            assert not re.search(pattern, text), f"{path.name}: possível credencial ({pattern})"


def test_new_files_have_no_trailing_whitespace() -> None:
    for path in NEW_FILES:
        for number, line in enumerate(_read(path).splitlines(), start=1):
            assert line == line.rstrip(), f"{path.name}:{number} tem espaço no fim da linha"


def test_verify_script_is_read_only() -> None:
    text = _read(VERIFY)
    assert "config -q" in text
    for forbidden in (" up -d", " up ", " down", "prune", "compose exec", "compose run", "migrate"):
        assert forbidden not in text, f"script de verificação não pode executar {forbidden!r}"


def test_readme_documents_required_operations() -> None:
    text = _read(README)
    for required in (
        "gasflow-hs-lab",
        "127.0.0.1:8088",
        "2688 MB",
        "3360 MB",
        "down -v",
        "Riscos restantes",
        "Nada disto foi executado nesta entrega",
        "GasFlow Desktop",
    ):
        assert required.lower() in text.lower(), f"README sem {required!r}"
