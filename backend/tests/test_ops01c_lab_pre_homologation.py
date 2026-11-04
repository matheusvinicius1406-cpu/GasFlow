"""
OPS-01C-A — pré-homologação ESTÁTICA do laboratório (gate da fase 0).

Complementa `test_ops01b_homeserver_profile.py` cobrindo o que o plano
`docs/integration/OPS_01C_LAB_PLAN.md` exige ANTES de qualquer `up`:

- isolamento: overrides herdados de `FRONTEND_PORT`, `DATABASE_URL` e
  `COMPOSE_PROJECT_NAME` não podem abrir porta, trocar o banco nem reutilizar
  volumes/rede de outro projeto;
- falha SEGURA: variável indispensável ausente → `config` aborta, nunca
  gera um stack parcial/publicando errado;
- alembic/`DATABASE_URL` confinados ao banco novo `gasflow_lab`, dentro do
  container (nunca no host, nunca em SQLite do cwd);
- nenhum bind mount de dado operacional (`C:\\gf`, `gasflow.db`, sessão);
- `data/prototype-contacts/app.db`: só metadados de esquema são lidos aqui,
  nunca registros (PII) — e o arquivo precisa continuar rastreado para o
  dono decidir a limpeza (P1-1);
- documentação das fases LAB-01..LAB-06 com pré-requisitos, comandos,
  critérios, abort e limpeza.

Validação ESTÁTICA: o único processo externo é `docker compose config`
(interpolação/merge, sem daemon, sem `up`). Ausência de Docker CLI ou de
Compose >= 2.24.4 (necessário para `!override`) pula com mensagem explícita.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD = REPO_ROOT / "docker-compose.prod.yml"
HOMESERVER = REPO_ROOT / "docker-compose.homeserver.yml"
LAB = REPO_ROOT / "docker-compose.homeserver.lab.yml"
ENV_LAB = REPO_ROOT / "deploy" / "home-server" / ".env.lab.example"
ENV_LAB_REAL = REPO_ROOT / "deploy" / "home-server" / ".env.lab"
PLAN = REPO_ROOT / "docs" / "integration" / "OPS_01C_LAB_PLAN.md"
REPORT = REPO_ROOT / "docs" / "integration" / "INT_01_FINAL_REPORT.md"
README = REPO_ROOT / "deploy" / "home-server" / "README.md"
APP_DB = REPO_ROOT / "data" / "prototype-contacts" / "app.db"

LAB_PROJECT = "gasflow-hs-lab"
LAB_FRONTEND_PORT = 8088
# `!override` entra no Compose v2.24.4 (docs.docker.com/reference/compose-file/merge).
MIN_COMPOSE = (2, 24, 4)
# Portas internas que o lab NUNCA pode publicar.
FORBIDDEN_PUBLISHED_PORTS = {80, 3000, 5432, 6379, 8000, 8080, 9090, 9093}

_CACHE: dict[tuple[str, ...], dict[str, Any]] = {}


def _read(path: Path) -> str:
    assert path.exists(), f"{path.name} ausente"
    return path.read_text(encoding="utf-8")


def _compose_cli() -> str:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker CLI indisponível no host")
    proc = subprocess.run([docker, "compose", "version", "--short"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"docker compose indisponível:\n{proc.stderr}"
    numbers = [int(part) for part in re.findall(r"\d+", proc.stdout.strip())[:3]]
    if tuple((numbers + [0, 0, 0])[:3]) < MIN_COMPOSE:
        pytest.skip(f"Compose {'.'.join(map(str, numbers))} < 2.24.4: tag !override indisponível")
    return docker


def _compose_config(
    env_file: Path,
    *,
    drop_env: tuple[str, ...] = (),
    profiles: tuple[str, ...] = ("observability",),
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """`docker compose config --format json` do stack do laboratório."""
    overrides = overrides or {}
    cache_key = (str(env_file), *drop_env, *profiles, *(f"{key}={value}" for key, value in sorted(overrides.items())))
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    docker = _compose_cli()
    command = [docker, "compose", "-p", LAB_PROJECT, "-f", str(PROD), "-f", str(HOMESERVER), "-f", str(LAB)]
    for profile in profiles:
        command += ["--profile", profile]
    command += ["--env-file", str(env_file), "config", "--format", "json"]

    environment = {key: value for key, value in os.environ.items() if key not in drop_env}
    environment.update(overrides)
    proc = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        env=environment,
    )
    assert proc.returncode == 0, f"docker compose config falhou:\n{proc.stdout}\n{proc.stderr}"
    document = json.loads(proc.stdout)
    _CACHE[cache_key] = document
    return document


def _lab() -> dict[str, Any]:
    return _compose_config(ENV_LAB)


def _published_ports(service: dict[str, Any]) -> list[dict[str, Any]]:
    return service.get("ports") or []


def _env_without(*keys: str) -> Path:
    """Copia do template SEM as chaves dadas (arquivo temporário, fora do git)."""
    kept = [line for line in _read(ENV_LAB).splitlines() if not any(line.startswith(f"{key}=") for key in keys)]
    target = ENV_LAB.with_name(f".env.lab.missing-{'-'.join(keys)}.tmp")
    target.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return target


# ── Isolamento: overrides herdados não podem mudar recursos do lab ──


def test_lab_ignores_inherited_database_port_and_project_overrides() -> None:
    """Overrides do processo não podem abrir porta nem trocar o banco/projeto."""
    document = _compose_config(
        ENV_LAB,
        overrides={
            "COMPOSE_PROJECT_NAME": "outside-lab",
            "DATABASE_URL": "postgresql+psycopg2://fake:fake@outside.invalid:5432/notlab",
            "FRONTEND_PORT": "0.0.0.0:80",
            "POSTGRES_DB": "outside_db",
            "POSTGRES_USER": "outside_user",
        },
    )
    assert document["name"] == LAB_PROJECT, "projeto Compose alterado por variável herdada"

    ports = _published_ports(document["services"]["frontend"])
    assert len(ports) == 1, f"esperava 1 porta, veio {ports}"
    assert ports[0].get("host_ip") == "127.0.0.1", f"lab publicou fora do loopback: {ports[0]}"
    assert str(ports[0].get("published")) == str(LAB_FRONTEND_PORT), f"porta errada: {ports[0]}"

    database_url = str(document["services"]["backend"]["environment"].get("DATABASE_URL", ""))
    assert database_url.startswith("postgresql"), "lab não aponta para PostgreSQL"
    assert "gasflow_lab" in database_url and "@postgres:5432" in database_url, (
        "DATABASE_URL herdada conseguiu alterar o destino do laboratório"
    )
    assert "outside.invalid" not in database_url and "notlab" not in database_url
    postgres_env = document["services"]["postgres"]["environment"]
    assert postgres_env.get("POSTGRES_DB") == "gasflow_lab", "banco do Postgres alterado por variável herdada"
    assert postgres_env.get("POSTGRES_USER") == "gasflow_lab", "usuário do Postgres alterado por variável herdada"


def test_lab_overlay_uses_literal_loopback_port_override() -> None:
    """O overlay precisa fixar o bind de loopback sem interpolação do host."""
    text = _read(LAB)
    assert "ports: !override" in text, "overlay do lab sem !override: merge soma a :80 do prod"
    # Só o código conta: o comentário cita o fallback do prod para explicar
    # por que ele foi substituído.
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert '"127.0.0.1:8088:80"' in code, "bind do lab precisa ser loopback:8088 literal"
    assert "${FRONTEND_PORT:-80}" not in code, "fallback :80 proibido no laboratório"


def test_compose_override_tag_minimum_version_is_documented() -> None:
    """`!override` exige Compose >= 2.24.4 — documentado onde se instala."""
    for path in (README, PLAN):
        text = _read(path)
        assert re.search(r"2\.24\.4", text), f"{path.name} sem a versão mínima 2.24.4 do !override"


def test_lab_fails_safe_when_required_variable_is_missing() -> None:
    """Segredo obrigatório ausente → aborta; nunca gera stack parcial."""
    docker = _compose_cli()
    env_file = _env_without("MARCOS_GAS_API_KEY")
    try:
        command = [
            docker,
            "compose",
            "-p",
            LAB_PROJECT,
            "-f",
            str(PROD),
            "-f",
            str(HOMESERVER),
            "-f",
            str(LAB),
            "--env-file",
            str(env_file),
            "config",
            "--quiet",
        ]
        proc = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            env={key: value for key, value in os.environ.items() if key != "MARCOS_GAS_API_KEY"},
        )
        assert proc.returncode != 0, "config deveria abortar sem MARCOS_GAS_API_KEY"
        assert "MARCOS_GAS_API_KEY" in (proc.stderr + proc.stdout), "erro não apontou a variável faltante"
    finally:
        env_file.unlink(missing_ok=True)


# ── LAB-01: PostgreSQL e Redis isolados ─────────────────────────


def test_lab_postgres_targets_new_database_and_is_unpublished() -> None:
    lab = _lab()
    postgres = lab["services"]["postgres"]
    assert not _published_ports(postgres), "PostgreSQL do lab não pode ser publicado"
    assert postgres.get("image", "").startswith("postgres:"), "imagem inesperada do Postgres"
    postgres_env = postgres.get("environment") or {}
    assert postgres_env.get("POSTGRES_DB") == "gasflow_lab", "banco do lab não está fixado"
    assert postgres_env.get("POSTGRES_USER") == "gasflow_lab", "usuário do lab não está fixado"
    healthcheck = postgres.get("healthcheck") or {}
    assert healthcheck.get("test"), "Postgres sem healthcheck (LAB-01 exige healthy)"
    assert healthcheck.get("start_period"), "healthcheck sem start_period (HDD lento)"

    backend_env = lab["services"]["backend"].get("environment") or {}
    database_url = str(backend_env.get("DATABASE_URL", ""))
    assert database_url.startswith("postgresql"), f"lab não aponta para PostgreSQL: {database_url!r}"
    assert "gasflow_lab" in database_url, "DATABASE_URL fora do banco fictício"
    assert "sqlite" not in database_url.lower(), "lab não pode cair em SQLite"
    assert "@postgres:5432" in database_url, "DSN precisa usar o serviço interno postgres"
    assert str(lab["services"]["postgres"].get("container_name", "")).startswith(f"{LAB_PROJECT}-")


def test_lab_redis_is_ephemeral_unpublished_and_healthy() -> None:
    lab = _lab()
    redis = lab["services"]["redis"]
    assert not _published_ports(redis), "Redis do lab não pode ser publicado"
    assert not redis.get("volumes"), "Redis do lab deve continuar efêmero"
    healthcheck = redis.get("healthcheck") or {}
    assert healthcheck.get("test"), "Redis sem healthcheck (LAB-01 exige healthy)"

    backend_env = lab["services"]["backend"].get("environment") or {}
    assert str(backend_env.get("RATE_LIMIT_REDIS_URL", "")).startswith("redis://redis:"), (
        "rate limit não aponta para o Redis interno do lab"
    )


def test_lab_migrations_run_only_inside_the_container() -> None:
    """`alembic upgrade head` só no boot do container, contra o PG do lab."""
    lab = _lab()
    command = " ".join(lab["services"]["backend"].get("command") or [])
    assert "alembic upgrade head" in command, f"boot sem migração: {command!r}"
    assert command.index("alembic upgrade head") < command.index("uvicorn"), "migração precisa anteceder o boot"
    assert "--workers 1" in command, "i3-10110U (2C/4T) → 1 worker"

    env_text = _read(REPO_ROOT / "backend" / "migrations" / "env.py")
    assert 'os.getenv("DATABASE_URL"' in env_text, "env.py não lê DATABASE_URL do ambiente"
    assert 'configuration["sqlalchemy.url"]' in env_text, "env.py não sobrescreve o sqlalchemy.url do alembic.ini"


def test_lab_has_no_bind_mount_of_operational_data() -> None:
    """Nenhum bind mount de dado/sessão operacional no laboratório."""
    lab = _lab()
    forbidden = ("c:\\gf", "gasflow.db", "prototype-contacts", "export-broadcast", "docker.sock")
    for name, service in lab["services"].items():
        for volume in service.get("volumes") or []:
            if volume.get("type") != "bind":
                continue
            source = str(volume.get("source", "")).lower().replace("/", "\\")
            assert not any(token in source for token in forbidden), f"{name}: bind mount operacional {source!r}"
            assert volume.get("read_only"), f"{name}: bind mount gravável {source!r} no lab"
            assert "monitoring" in source, f"{name}: bind mount fora de monitoring/ ({source!r})"
        for mount in service.get("volumes") or []:
            assert "docker.sock" not in str(mount.get("source", "")), f"{name}: socket do Docker montado"


def test_lab_publishes_no_internal_port() -> None:
    lab = _lab()
    publishing = {name: _published_ports(svc) for name, svc in lab["services"].items()}
    publishing = {name: ports for name, ports in publishing.items() if ports}
    assert set(publishing) == {"frontend"}, f"lab publica portas em {sorted(publishing)}"
    for port in publishing["frontend"]:
        assert str(port.get("published")) not in {str(item) for item in FORBIDDEN_PUBLISHED_PORTS}, port
        assert port.get("host_ip") == "127.0.0.1", f"lab escutando fora do loopback: {port}"


def test_lab_env_file_stays_out_of_git_and_real_file_is_optional() -> None:
    gitignore = _read(REPO_ROOT / ".gitignore")
    assert "deploy/home-server/.env.lab" in gitignore.splitlines(), ".env.lab versionável"
    if not ENV_LAB_REAL.exists():
        return  # o env local é opcional; o template fictício é versionado
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "deploy/home-server/.env.lab"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert tracked.returncode != 0, ".env.lab real está versionado (vazaria segredos)"


# ── P1-1: metadados do banco de protótipo (sem registros) ───────


def test_prototype_contacts_db_is_tracked_and_pii_columns_are_known() -> None:
    """Só esquema/contagens: nenhum registro (PII) é lido ou impresso."""
    assert APP_DB.exists(), "data/prototype-contacts/app.db ausente"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "data/prototype-contacts/app.db"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert tracked.returncode == 0, "app.db deixou de ser rastreado sem decisão do dono (P1-1)"

    uri = APP_DB.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "contacts" in tables, "tabela contacts ausente (metadado esperado)"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(contacts)")}
        assert {"phone", "jid", "name"} <= columns, "colunas de PII esperadas ausentes"
        count = connection.execute("SELECT count(*) FROM contacts").fetchone()[0]
        assert count > 0, "contagem inesperada: arquivo vazio não é o caso documentado"
    finally:
        connection.close()


# ── Documentação das fases do laboratório ───────────────────────


def test_plan_defines_the_six_lab_gates() -> None:
    text = _read(PLAN)
    for gate in ("LAB-01", "LAB-02", "LAB-03", "LAB-04", "LAB-05", "LAB-06"):
        assert re.search(rf"#+\s*{gate}\b", text), f"plano sem o gate {gate}"
    for section in ("pré-requisitos", "comandos", "critérios de aprovação", "abort", "limpeza"):
        assert section in text.lower(), f"plano sem a seção {section!r}"


def test_plan_records_the_lab_preparation_deliverables() -> None:
    text = _read(PLAN)
    for item in ("PostgreSQL", "Redis", "parada", "limpeza", "recursos"):
        assert item.lower() in text.lower(), f"preparação LAB-01 sem {item!r}"
    assert REPORT.exists(), "INT_01_FINAL_REPORT.md ausente"


def test_plan_keeps_the_no_real_execution_statement() -> None:
    text = _read(PLAN)
    assert "Nada foi iniciado" in text or "nada foi iniciado" in text.lower(), (
        "plano deve declarar que nada foi executado"
    )
    assert "down -v" in text, "plano sem procedimento de limpeza"
