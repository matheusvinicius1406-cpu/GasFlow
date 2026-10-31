#!/usr/bin/env python3
"""Diagnóstico somente-leitura de um SQLite de origem (OPS-01D, Etapa 2).

Coleta: header, integridade, journal, páginas, tabelas + contagens, snapshot
de schema, versão do app (``_schema_version``), versão Alembic
(``alembic_version``), sidecars WAL/SHM, tamanho e checksum SHA-256 do
arquivo principal. Nunca escreve na origem (conexão ``mode=ro``) e não emite
o conteúdo de nenhuma linha (sem PII).

Uso:
    python scripts/home-server/data/db_diagnose.py --source caminho/gasflow.db
    python ... --source x.db --report out/diagnostico.json

Códigos de saída: 0 ok | 1 origem inválida/corrompida | 2 segurança.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="caminho do SQLite de origem")
    parser.add_argument("--report", help="gravar o relatório JSON em arquivo")
    parser.add_argument(
        "--no-hash",
        action="store_true",
        help="não calcular SHA-256 do arquivo principal",
    )
    return parser.parse_args(argv)


def diagnose(source: Path, *, with_hash: bool) -> dict:
    info: dict = {
        "path": str(source),
        "exists": source.exists(),
        "size_bytes": None,
        "mtime_utc": None,
        "header_ok": False,
        "header_write_version": None,
        "open_mode": None,
        "journal_mode": None,
        "page_size": None,
        "page_count": None,
        "integrity_check": [],
        "sha256": None,
        "hash_scope": "bytes do arquivo principal (WAL não incluso)",
        "schema_version": None,
        "alembic_version": None,
        "sidecars": {},
        "tables": {},
        "table_count": 0,
        "row_total": 0,
    }
    if not source.exists():
        info["status"] = "missing"
        return info
    if not source.is_file():
        info["status"] = "not_a_file"
        return info

    stat = source.stat()
    info["size_bytes"] = stat.st_size
    info["mtime_utc"] = c.iso_from_mtime(stat.st_mtime)
    info["header_ok"] = c.has_sqlite_magic(source)
    if info["header_ok"]:
        info["header_write_version"] = c.journal_write_version(source)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source) + suffix)
        info["sidecars"][suffix.lstrip("-")] = (
            sidecar.stat().st_size if sidecar.exists() else None
        )
    if with_hash:
        info["sha256"] = c.sha256_file(source)
    if not info["header_ok"]:
        info["status"] = "invalid_header"
        return info

    try:
        conn, mode = c.open_readonly(source)
    except c.ReadOnlyOpenError as exc:
        # Abertura estritamente read-only falhou: erro explícito, sem fallback
        # de escrita e sem criar sidecars na origem.
        info["open_mode"] = "denied"
        info["read_only_error"] = str(exc)
        info["status"] = "read_only_error"
        return info
    try:
        info["open_mode"] = mode
        info["journal_mode"] = c.pragma_str(conn, "journal_mode")
        info["page_size"] = c.pragma_str(conn, "page_size")
        info["page_count"] = c.pragma_str(conn, "page_count")
        info["integrity_check"] = c.integrity_problems(conn)
        info["schema_version"] = c.scalar_setting(conn, "_schema_version", "version")
        info["alembic_version"] = c.scalar_setting(
            conn, "alembic_version", "version_num"
        )
        counts = c.row_counts(conn)
        snapshot = c.schema_snapshot(conn)
        info["tables"] = {
            name: {"rows": count, "columns": len(snapshot.get(name, {}))}
            for name, count in counts.items()
        }
        info["table_count"] = len(counts)
        info["row_total"] = sum(counts.values())
    finally:
        conn.close()

    info["status"] = "corrupt" if info["integrity_check"] else "ok"
    return info


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    refusal = c.guard_report_path(args.report)
    if refusal:
        return c.die(c.EXIT_SAFETY, refusal)
    source = Path(args.source).expanduser()
    if source.exists():
        source = source.resolve()
    report = {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "diagnose",
        "generated_at": c.utc_now(),
        "source": diagnose(source, with_hash=not args.no_hash),
    }
    status = report["source"]["status"]
    if args.report:
        c.write_json(args.report, report)
    c.emit(report)
    if status == "ok":
        c.note(f"diagnóstico ok: {report['source']['table_count']} tabelas")
        return c.EXIT_OK
    if status == "missing":
        return c.die(c.EXIT_SAFETY, f"origem inexistente: {source}")
    if status == "read_only_error":
        return c.die(
            c.EXIT_SAFETY,
            f"abertura somente-leitura da origem recusada: "
            f"{report['source'].get('read_only_error')}",
        )
    if status in {"invalid_header", "not_a_file"}:
        return c.die(c.EXIT_FAIL, f"origem não é SQLite válido ({status})")
    return c.die(
        c.EXIT_FAIL, f"integridade reprovada: {report['source']['integrity_check']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
