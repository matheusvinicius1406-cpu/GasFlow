#!/usr/bin/env python3
"""Restauração de dump PostgreSQL (OPS-01D, fase de integração — MOCK).

Envolvória de ``pg_restore``: dry-run por padrão (só VERIFICA o dump contra
o manifesto), ``--execute`` para restaurar de verdade. Garantias:

* dump precisa ter o mágico ``PGDMP`` e bater com o sha256 do manifesto
  (quando presente) — divergência = recusa (código 2);
* relatório e artefatos nunca sobrescritos; DSN com senha embutida recusado
  (a ferramenta nunca define ``PGPASSWORD``);
* ``--mock --execute`` simula a restauração sem servidor algum — caminho
  exercitado pelos testes;
* sem ``--clean``: a restauração não apaga objetos pré-existentes do alvo
  (o banco de destino deve virgar vazio na fase de integração).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

PG_MAGIC = b"PGDMP"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, help="arquivo .dump do backup")
    parser.add_argument("--dsn", help="postgresql://... do banco de destino")
    parser.add_argument("--manifest", help="manifesto JSON (padrão: ao do dump)")
    parser.add_argument(
        "--mock", action="store_true", help="sem servidor: simula a restauração"
    )
    parser.add_argument(
        "--execute", action="store_true", help="restaura (mock ou pg_restore)"
    )
    parser.add_argument("--pg-bin", default="pg_restore", help="caminho do pg_restore")
    parser.add_argument("--report", help="relatório JSON (nunca sobrescreve)")
    return parser.parse_args(argv)


def default_manifest(dump: Path) -> Path:
    return Path(str(dump) + ".manifest.json")


def _dsn_gate(args: argparse.Namespace) -> str | None:
    if args.dsn and urlparse(args.dsn).password:
        return (
            "DSN com senha embutida: recusado "
            "(use PGPASSWORD/pgpassfile; a senha nunca vai em argv)"
        )
    if args.execute and not args.mock and not args.dsn:
        return "--dsn obrigatório fora do modo --mock"
    return None


def _dsn_target(dsn: str | None) -> dict[str, str]:
    if not dsn:
        return {"host": "mock", "database": "mock"}
    parsed = urlparse(dsn)
    return {
        "host": parsed.hostname or "",
        "database": (parsed.path or "/").lstrip("/"),
    }


def _verify_dump(dump: Path, manifest_path: Path) -> dict:
    """Confere mágico + sha256 do manifesto. Levanta RuntimeError em recusa."""
    if dump.read_bytes()[: len(PG_MAGIC)] != PG_MAGIC:
        raise RuntimeError("dump sem mágico PGDMP (arquivo corrompido/alheio)")
    verification: dict = {"magic_ok": True, "manifest_checked": False}
    if manifest_path.exists():
        manifest = c.loads_json(manifest_path)
        esperado = manifest.get("dump", {}).get("sha256")
        if not esperado:
            raise RuntimeError("manifesto sem dump.sha256")
        atual = c.sha256_file(dump)
        if atual != esperado:
            raise RuntimeError("sha256 do dump diverge do manifesto")
        verification = {"magic_ok": True, "manifest_checked": True}
    return verification


def _run_pg_restore(args: argparse.Namespace, dump: Path) -> str:
    if not shutil.which(args.pg_bin) and not Path(args.pg_bin).exists():
        raise RuntimeError(f"pg_restore não encontrado: {args.pg_bin}")
    cmd = [args.pg_bin, "--dbname", args.dsn or "", str(dump)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pg_restore falhou (rc={proc.returncode}): {proc.stderr[:300]}"
        )
    return _pg_version(args)


def _pg_version(args: argparse.Namespace) -> str:
    proc = subprocess.run(
        [args.pg_bin, "--version"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip()[:120] or "desconhecida"


def _finish(report: dict, args: argparse.Namespace) -> None:
    if args.report:
        c.write_json(args.report, report)
    c.emit(report)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dump = Path(args.dump).expanduser()
    manifest = (
        Path(args.manifest).expanduser() if args.manifest else default_manifest(dump)
    )
    refusal = c.guard_report_path(args.report)
    if refusal:
        return c.die(c.EXIT_SAFETY, refusal)
    if args.report and Path(args.report).expanduser().resolve() in {
        dump.resolve(),
        manifest.resolve(),
    }:
        return c.die(c.EXIT_SAFETY, "--report coincide com artefato do dump")
    if not dump.exists() or not dump.is_file():
        return c.die(c.EXIT_SAFETY, f"dump inexistente: {dump}")
    dsn_refusal = _dsn_gate(args)
    if dsn_refusal:
        return c.die(c.EXIT_SAFETY, dsn_refusal)
    report = {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "pg-restore",
        "generated_at": c.utc_now(),
        "mode": "mock" if args.mock else "real",
        "dsn_target": _dsn_target(args.dsn),
        "dump": str(dump),
        "manifest": str(manifest) if manifest.exists() else None,
        "status": "pending",
    }
    try:
        verification = _verify_dump(dump, manifest)
    except (RuntimeError, ValueError, OSError) as exc:
        report["status"] = "refused"
        report["error"] = str(exc)[:300]
        _finish(report, args)
        return c.die(c.EXIT_SAFETY, f"dump recusado: {exc}")
    report["verification"] = verification
    if not args.execute:
        report["status"] = "verified"
        _finish(report, args)
        c.note("dry-run: dump verificado, nada restaurado")
        return c.EXIT_OK
    try:
        if args.mock:
            version = "mock"
        else:
            version = _run_pg_restore(args, dump)
    except (OSError, RuntimeError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)[:300]
        _finish(report, args)
        return c.die(c.EXIT_FAIL, f"restauração falhou: {exc}")
    report["status"] = "restored-mock" if args.mock else "restored"
    report["pg_restore_version"] = version
    _finish(report, args)
    c.note("restauração concluída" + (" (mock)" if args.mock else ""))
    return c.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
