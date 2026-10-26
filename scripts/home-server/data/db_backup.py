#!/usr/bin/env python3
"""Backup consistente de SQLite com verificação (OPS-01D, Etapa 2).

Cópia pela API de backup online do SQLite (``Connection.backup``): leitura
concorrente do app é segura e a origem não é alterada. O backup só é
considerado válido — e só fica em disco — depois de passar por:

1. header SQLite + ``PRAGMA integrity_check`` no backup;
2. snapshot de schema idêntico ao da origem;
3. contagens por tabela idênticas às da origem;
4. origem sem alteração durante a cópia (``PRAGMA data_version`` + SHA-256);
5. manifesto JSON com checksum SHA-256, timestamp e contagens.

Falha em qualquer etapa remove o arquivo parcial e devolve código != 0 —
não deixamos backup não comprovado no diretório.

Uso:
    python scripts/home-server/data/db_backup.py --source app.db --out backups/
    python ... --source app.db --out backups/ --dry-run

Códigos: 0 ok | 1 verificação falhou | 2 segurança (origem/alvo inválidos).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, help="SQLite de origem (nunca alterado)"
    )
    parser.add_argument("--out", required=True, help="diretório de destino do backup")
    parser.add_argument("--label", default="gasflow", help="prefixo do nome do arquivo")
    parser.add_argument("--report", help="gravar o relatório JSON em arquivo")
    parser.add_argument("--dry-run", action="store_true", help="planejar sem gravar")
    parser.add_argument(
        "--allow-concurrent-writes",
        action="store_true",
        help="aceita origem alterada durante a cópia (relatório marca a alteração)",
    )
    return parser.parse_args(argv)


def preflight_source(source: Path) -> tuple[sqlite3.Connection, str] | int:
    if not source.exists() or not source.is_file():
        return c.die(c.EXIT_SAFETY, f"origem inexistente: {source}")
    if not c.has_sqlite_magic(source):
        return c.die(c.EXIT_FAIL, f"origem sem header SQLite: {source}")
    conn, mode = c.open_readonly(source)
    problems = c.integrity_problems(conn)
    if problems:
        conn.close()
        return c.die(c.EXIT_FAIL, f"integridade da origem reprovada: {problems[:3]}")
    return conn, mode


def plan_targets(out_dir: Path, label: str, source: Path) -> dict:
    stamp = c.slug_ts()
    backup = out_dir / f"{label}-{stamp}.db"
    manifest = out_dir / f"{label}-{stamp}.db.manifest.json"
    for path in (backup, manifest):
        if path.exists():
            raise FileExistsError(f"recusando sobrescrever artefato existente: {path}")
    if backup.resolve() == source:
        raise ValueError("alvo do backup coincide com a origem")
    return {"backup": backup, "manifest": manifest}


def snapshot(conn: sqlite3.Connection, source: Path, *, with_hash: bool) -> dict:
    return {
        "counts": c.row_counts(conn),
        "schema": c.schema_snapshot(conn),
        "data_version": c.data_version(conn),
        "sha256": c.sha256_file(source) if with_hash else None,
    }


def copy_database(source: Path, dest: Path) -> None:
    src_conn, _mode = c.open_readonly(source)
    try:
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def verify_backup(dest: Path, expected_counts: dict, expected_schema: dict) -> dict:
    result = {
        "header_ok": c.has_sqlite_magic(dest),
        "integrity_check": [],
        "schema_match": False,
        "counters_match": False,
        "counts": {},
        "passed": False,
    }
    if not result["header_ok"]:
        return result
    conn = sqlite3.connect(str(dest))
    try:
        result["integrity_check"] = c.integrity_problems(conn)
        result["counts"] = c.row_counts(conn)
        result["schema_match"] = c.schema_snapshot(conn) == expected_schema
        result["counters_match"] = result["counts"] == expected_counts
    finally:
        conn.close()
    result["passed"] = (
        not result["integrity_check"]
        and result["schema_match"]
        and result["counters_match"]
    )
    return result


def source_delta(before: dict, after: dict) -> list[str]:
    delta: list[str] = []
    if before["data_version"] != after["data_version"]:
        delta.append("data_version")
    if before.get("sha256") and before["sha256"] != after.get("sha256"):
        delta.append("sha256")
    if before["counts"] != after["counts"]:
        delta.append("row_counts")
    return delta


def build_manifest(
    args: argparse.Namespace, conn: sqlite3.Connection, info: dict
) -> dict:
    return {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "backup",
        "created_at": c.utc_now(),
        "source": {
            "path": info["source_path"],
            "size_bytes": info["source_size"],
            "sha256_before": info["before"]["sha256"],
            "sha256_after": info["after"]["sha256"],
            "journal_mode": c.pragma_str(conn, "journal_mode"),
            "integrity_check": "ok",
            "open_mode": info["open_mode"],
        },
        "backup": {
            "path": str(info["backup"]),
            "size_bytes": info["backup"].stat().st_size,
            "sha256": info["backup_sha256"],
            "integrity_check": "ok",
        },
        "tables": info["verification"]["counts"],
        "schema_tables": len(info["before"]["schema"]),
        "source_changed_during_backup": info["delta"],
        "concurrent_writes_accepted": bool(args.allow_concurrent_writes),
        "status": "verified",
    }


def _finish(report: dict, args: argparse.Namespace, *, overwrite: bool = False) -> None:
    if args.report:
        c.write_json(args.report, report, overwrite=overwrite)
    c.emit(report)


def _execute_backup(args, conn, source, targets, before, open_mode) -> dict:
    """Cópia + verificação + manifesto. Levanta exceção em qualquer falha."""
    out_dir = targets["backup"].parent
    out_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "source_path": str(source),
        "source_size": source.stat().st_size,
        "open_mode": open_mode,
        "before": before,
        "backup": targets["backup"],
    }
    copy_database(source, targets["backup"])
    info["verification"] = verify_backup(
        targets["backup"], before["counts"], before["schema"]
    )
    if not info["verification"]["passed"]:
        raise RuntimeError(f"verificação do backup reprovada: {info['verification']}")
    info["after"] = snapshot(conn, source, with_hash=True)
    info["delta"] = source_delta(before, info["after"])
    if info["delta"] and not args.allow_concurrent_writes:
        raise RuntimeError(
            f"origem alterada durante a cópia ({','.join(info['delta'])}) — "
            "reexecute com o app ocioso ou use --allow-concurrent-writes"
        )
    info["backup_sha256"] = c.sha256_file(targets["backup"])
    manifest = build_manifest(args, conn, info)
    c.write_json(targets["manifest"], manifest)
    return manifest


def run(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    if not _LABEL.match(args.label):
        return c.die(c.EXIT_SAFETY, f"--label inválido: {args.label!r}")
    opened = preflight_source(source)
    if isinstance(opened, int):
        return opened
    conn, open_mode = opened

    try:
        targets = plan_targets(Path(args.out).expanduser(), args.label, source)
    except (FileExistsError, ValueError) as exc:
        conn.close()
        return c.die(c.EXIT_SAFETY, str(exc))

    before = snapshot(conn, source, with_hash=True)
    report = {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "backup",
        "generated_at": c.utc_now(),
        "mode": "dry-run" if args.dry_run else "execute",
        "source": {
            "path": str(source),
            "size_bytes": source.stat().st_size,
            "tables": len(before["counts"]),
            "rows": sum(before["counts"].values()),
            "open_mode": open_mode,
            "journal_mode": c.pragma_str(conn, "journal_mode"),
        },
        "plan": {
            "backup_path": str(targets["backup"]),
            "manifest_path": str(targets["manifest"]),
        },
    }
    if args.dry_run:
        conn.close()
        report["status"] = "dry-run"
        _finish(report, args)
        c.note("dry-run: nenhum arquivo gravado")
        return c.EXIT_OK

    try:
        manifest = _execute_backup(args, conn, source, targets, before, open_mode)
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        conn.close()
        _cleanup(targets["backup"])
        _cleanup(targets["manifest"])
        report["status"] = "failed"
        report["error"] = str(exc)
        _finish(report, args, overwrite=True)
        return c.die(c.EXIT_FAIL, str(exc))

    conn.close()
    report["status"] = "verified"
    report["backup"] = manifest["backup"]
    report["tables"] = manifest["tables"]
    report["manifest_path"] = str(targets["manifest"])
    _finish(report, args)
    c.note(f"backup verificado: {targets['backup'].name}")
    return c.EXIT_OK


def _cleanup(path: Path) -> None:
    """Remove artefato parcial criado NESTA execução (nunca a origem)."""
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
