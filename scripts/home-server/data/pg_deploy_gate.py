#!/usr/bin/env python3
"""Backup verificável antes de migrations PostgreSQL do Home Server.

O script é somente plano por padrão. Para executar, requer --execute,
--confirm-off-host e uma pasta de backup pré-existente em filesystem diferente
do checkout. O operador continua responsável por confirmar que esse filesystem
está realmente fora do host/volume do banco (por exemplo, disco externo ou share).
Nenhum comando de migration é chamado antes de pg_dump, SHA-256, manifesto e
`pg_restore --list` passarem. O script nunca inicia WhatsApp nem a API.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_DATA_DIR = Path(__file__).resolve().parent
if str(_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(_DATA_DIR))

import common as c  # noqa: E402

PG_MAGIC = b"PGDMP"


class GateRefusal(RuntimeError):
    """Pré-condição de segurança não atendida; nenhum upgrade deve iniciar."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="nome do projeto Compose")
    parser.add_argument(
        "--env-file", required=True, help="arquivo de ambiente do deploy"
    )
    parser.add_argument(
        "--compose-file",
        action="append",
        dest="compose_files",
        help="arquivo Compose (repita para overlays, na ordem de aplicação)",
    )
    parser.add_argument(
        "--backup-dir",
        required=True,
        help="diretório externo já montado em filesystem diferente",
    )
    parser.add_argument(
        "--database-name", required=True, help="nome não secreto do banco a migrar"
    )
    parser.add_argument(
        "--confirm-off-host",
        action="store_true",
        help="confirmação humana de que o destino está fora do host do banco",
    )
    parser.add_argument(
        "--execute", action="store_true", help="executa backup, valida e migra"
    )
    return parser.parse_args(argv)


def _compose_prefix(args: argparse.Namespace) -> list[str]:
    files = args.compose_files or [
        "docker-compose.prod.yml",
        "docker-compose.homeserver.yml",
    ]
    command = ["docker", "compose", "-p", args.project]
    for compose_file in files:
        command.extend(["-f", compose_file])
    command.extend(["--env-file", args.env_file])
    return command


def _validate_backup_destination(backup_dir: Path, repository_root: Path) -> Path:
    destination = backup_dir.expanduser().resolve()
    root = repository_root.resolve()
    if not destination.is_dir():
        raise GateRefusal(
            "destino de backup deve existir e estar montado antes do gate"
        )
    try:
        destination.relative_to(root)
    except ValueError:
        pass
    else:
        raise GateRefusal("backup dentro do repositório recusado")
    if destination.stat().st_dev == root.stat().st_dev:
        raise GateRefusal("destino está no mesmo filesystem; backup off-host recusado")
    return destination


def _run_checked(
    runner: Callable[..., Any],
    command: list[str],
    *,
    stdin: Any = subprocess.DEVNULL,
    stdout: Any = subprocess.PIPE,
) -> Any:
    result = runner(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise GateRefusal("etapa externa falhou; Alembic não foi executado")
    return result


def _execute_gate(
    args: argparse.Namespace,
    *,
    repository_root: Path,
    runner: Callable[..., Any] = subprocess.run,
    destination_validator: Callable[[Path, Path], Path] = _validate_backup_destination,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if not args.execute:
        return {
            "status": "dry-run",
            "steps": [
                "backup custom",
                "SHA-256 + manifesto",
                "pg_restore --list",
                "Alembic upgrade head",
            ],
            "migration_executed": False,
        }
    if not args.confirm_off_host:
        raise GateRefusal("confirmação humana --confirm-off-host obrigatória")

    destination = destination_validator(Path(args.backup_dir), repository_root)
    run_id = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = destination / f"gasflow-pre-migration-{run_id}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(exist_ok=False)
    dump_path = run_dir / "database.dump"
    manifest_path = run_dir / "database.dump.manifest.json"
    prefix = _compose_prefix(args)

    try:
        dump_command = prefix + [
            "exec",
            "-T",
            "postgres",
            "sh",
            "-ec",
            'exec pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        ]
        with dump_path.open("xb") as dump_file:
            _run_checked(runner, dump_command, stdout=dump_file)
        if (
            dump_path.stat().st_size <= len(PG_MAGIC)
            or dump_path.read_bytes()[: len(PG_MAGIC)] != PG_MAGIC
        ):
            dump_path.unlink(missing_ok=True)
            raise GateRefusal("pg_dump não produziu um arquivo custom válido")

        restore_check = prefix + ["exec", "-T", "postgres", "pg_restore", "--list", "-"]
        with dump_path.open("rb") as dump_file:
            _run_checked(runner, restore_check, stdin=dump_file)

        manifest = {
            "tool": "gasflow-pg-deploy-gate",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": args.database_name,
            "destination": str(run_dir),
            "dump": {
                "file": dump_path.name,
                "size_bytes": dump_path.stat().st_size,
                "sha256": c.sha256_file(dump_path),
                "format": "custom",
                "magic_ok": True,
                "pg_restore_list_verified": True,
            },
            "off_host_confirmed_by_operator": True,
            "status": "backup-verified",
        }
        c.write_json(manifest_path, manifest)
    except (OSError, GateRefusal) as exc:
        if dump_path.exists() and not manifest_path.exists():
            dump_path.unlink(missing_ok=True)
        try:
            run_dir.rmdir()
        except OSError:
            pass
        if isinstance(exc, GateRefusal):
            raise
        raise GateRefusal(
            "backup não pôde ser criado/verificado; migration bloqueada"
        ) from exc

    migration_command = prefix + [
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "alembic",
        "backend",
        "upgrade",
        "head",
    ]
    verification_command = prefix + [
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "backend",
        "-c",
        "from app.infrastructure.database.init_db import _assert_postgres_schema_current; _assert_postgres_schema_current()",
    ]
    manifest["status"] = "migration-started"
    c.write_json(manifest_path, manifest, overwrite=True)
    try:
        _run_checked(runner, migration_command)
    except (GateRefusal, OSError) as exc:
        manifest["status"] = "migration-failed-or-partial"
        c.write_json(manifest_path, manifest, overwrite=True)
        raise GateRefusal(
            "Alembic falhou; migration pode estar parcial e o backup foi preservado"
        ) from exc
    try:
        _run_checked(runner, verification_command)
    except (GateRefusal, OSError) as exc:
        manifest["status"] = "migration-unverified"
        c.write_json(manifest_path, manifest, overwrite=True)
        raise GateRefusal(
            "Alembic terminou, mas o schema head não foi verificado; backup preservado"
        ) from exc
    manifest["status"] = "migration-completed"
    c.write_json(manifest_path, manifest, overwrite=True)
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = _execute_gate(
            args, repository_root=Path(__file__).resolve().parents[3]
        )
    except (GateRefusal, OSError) as exc:
        return c.die(c.EXIT_SAFETY, str(exc))
    c.emit(result)
    return c.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
