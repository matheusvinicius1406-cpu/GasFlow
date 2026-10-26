#!/usr/bin/env python3
"""Preparação de backup PostgreSQL (OPS-01D, fase de integração — MOCK).

Envolvória de ``pg_dump`` com as mesmas garantias dos scripts SQLite:
dry-run por padrão, artefatos e relatório nunca sobrescritos, senha NUNCA
como argumento e NUNCA com default — a ferramenta não define ``PGPASSWORD``
(herda o ambiente do chamador apenas se ele próprio configurou).

``--mock`` gera um dump sintético (arquivo + manifesto) SEM contatar qualquer
servidor — é o caminho exercitado pelos testes. O caminho real exige
``--execute`` + ``--dsn`` + binário ``pg_dump``; DSN com senha embutida é
recusado (credenciais devem vir de ``PGPASSWORD``/``pgpassfile``).
A conversão SQLite→PostgreSQL segue pendente (docs/data-migration/README.md).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

PG_MAGIC = b"PGDMP"
MOCK_DUMP_BYTES = PG_MAGIC + (
    b"\n-- ops01d mock dump: artefato de laboratorio, nenhum dado real\n"
)
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="postgresql://... do banco de origem")
    parser.add_argument("--out", required=True, help="diretório do dump")
    parser.add_argument("--label", default="gasflow", help="prefixo do arquivo")
    parser.add_argument(
        "--mock", action="store_true", help="sem servidor: dump sintético"
    )
    parser.add_argument(
        "--execute", action="store_true", help="produz o dump (mock ou pg_dump)"
    )
    parser.add_argument("--pg-bin", default="pg_dump", help="caminho do pg_dump")
    parser.add_argument("--report", help="relatório JSON (nunca sobrescreve)")
    return parser.parse_args(argv)


def _targets(out_dir: Path, label: str, stamp: str) -> dict[str, Path]:
    dump = out_dir / f"{label}-{stamp}.dump"
    return {"dump": dump, "manifest": out_dir / f"{label}-{stamp}.dump.manifest.json"}


def _refusal(args: argparse.Namespace, targets: dict[str, Path]) -> str | None:
    if not _LABEL_RE.match(args.label):
        return f"rótulo inválido (use [A-Za-z0-9._-]): {args.label!r}"
    for path in targets.values():
        if path.exists():
            return f"artefato existente (sobrescrita proibida): {path.name}"
    refusal = c.guard_report_path(args.report)
    if refusal:
        return refusal
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        if report_path in {p.resolve() for p in targets.values()}:
            return f"--report coincide com artefato do dump: {report_path}"
    return None


def _dsn_gate(args: argparse.Namespace) -> str | None:
    if args.mock:
        return None
    if not args.dsn:
        return "--dsn obrigatório fora do modo --mock"
    if urlparse(args.dsn).password:
        return (
            "DSN com senha embutida: recusado "
            "(use PGPASSWORD/pgpassfile; a senha nunca vai em argv)"
        )
    return None


def _dsn_target(dsn: str | None) -> dict[str, str]:
    if not dsn:
        return {"host": "mock", "database": "mock"}
    parsed = urlparse(dsn)
    return {
        "host": parsed.hostname or "",
        "database": (parsed.path or "/").lstrip("/"),
    }


def _run_pg_dump(args: argparse.Namespace, targets: dict[str, Path]) -> str:
    if not shutil.which(args.pg_bin) and not Path(args.pg_bin).exists():
        raise RuntimeError(f"pg_dump não encontrado: {args.pg_bin}")
    cmd = [
        args.pg_bin,
        "--file",
        str(targets["dump"]),
        "--format",
        "custom",
        args.dsn or "",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pg_dump falhou (rc={proc.returncode}): {proc.stderr[:300]}"
        )
    return _pg_version(args)


def _pg_version(args: argparse.Namespace) -> str:
    proc = subprocess.run(
        [args.pg_bin, "--version"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip()[:120] or "desconhecida"


def _mock_dump(targets: dict[str, Path]) -> None:
    targets["dump"].write_bytes(MOCK_DUMP_BYTES)


def _build_manifest(args: argparse.Namespace, targets: dict, version: str) -> dict:
    dump = targets["dump"]
    return {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "pg-backup",
        "created_at": c.utc_now(),
        "mode": "mock" if args.mock else "real",
        "dsn_target": _dsn_target(args.dsn),
        "pg_dump_version": version,
        "dump": {
            "path": str(dump),
            "size_bytes": dump.stat().st_size,
            "sha256": c.sha256_file(dump),
            "magic_ok": dump.read_bytes()[: len(PG_MAGIC)] == PG_MAGIC,
        },
        "status": "verified",
    }


def _cleanup(targets: dict[str, Path]) -> None:
    for path in targets.values():
        path.unlink(missing_ok=True)


def _finish(report: dict, args: argparse.Namespace) -> None:
    if args.report:
        c.write_json(args.report, report)
    c.emit(report)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stamp = c.slug_ts()
    targets = _targets(Path(args.out).expanduser(), args.label, stamp)
    refusal = _refusal(args, targets)
    if refusal:
        return c.die(c.EXIT_SAFETY, refusal)
    dsn_refusal = _dsn_gate(args)
    if dsn_refusal:
        return c.die(c.EXIT_SAFETY, dsn_refusal)
    report = {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "pg-backup",
        "generated_at": c.utc_now(),
        "mode": "mock" if args.mock else "real",
        "dsn_target": _dsn_target(args.dsn),
        "plan": {
            "dump_path": str(targets["dump"]),
            "manifest_path": str(targets["manifest"]),
        },
        "status": "pending",
    }
    if not args.execute:
        report["status"] = "dry-run"
        _finish(report, args)
        c.note("dry-run: nenhum dump gravado")
        return c.EXIT_OK
    out_dir = targets["dump"].parent
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.mock:
            _mock_dump(targets)
            version = "mock"
        else:
            version = _run_pg_dump(args, targets)
        manifest = _build_manifest(args, targets, version)
        c.write_json(targets["manifest"], manifest)
    except (OSError, RuntimeError) as exc:
        _cleanup(targets)
        report["status"] = "failed"
        report["error"] = str(exc)[:300]
        _finish(report, args)
        return c.die(c.EXIT_FAIL, f"dump falhou (artefatos removidos): {exc}")
    report["status"] = "verified"
    report["dump"] = manifest["dump"]
    report["manifest_path"] = str(targets["manifest"])
    _finish(report, args)
    c.note(f"dump pronto: {targets['dump'].name}")
    return c.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
