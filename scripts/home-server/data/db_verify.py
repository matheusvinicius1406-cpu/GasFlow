#!/usr/bin/env python3
"""Verificação de backup SQLite + ensaio de restauração (OPS-01D, Etapa 2).

Confere que um backup existente continua recuperável: header, integridade,
checksum SHA-256 contra o manifesto, contagens por tabela e (opcionalmente)
schema/contagens contra a origem atual. ``--restore-drill`` copia o backup
para um diretório temporário, revalida e apaga a cópia — prova de
recuperabilidade sem tocar em nenhum banco real.

Uso:
    python scripts/home-server/data/db_verify.py --backup backups/x.db
    python ... --backup backups/x.db --source app.db --restore-drill

Códigos: 0 ok | 1 verificação reprovada | 2 segurança (arquivo ausente).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, help="arquivo .db do backup")
    parser.add_argument("--manifest", help="manifesto JSON (padrão: ao do backup)")
    parser.add_argument("--source", help="origem atual para comparação opcional")
    parser.add_argument(
        "--restore-drill",
        action="store_true",
        help="restaura em diretório temporário, valida e apaga",
    )
    parser.add_argument("--report", help="gravar o relatório JSON em arquivo")
    return parser.parse_args(argv)


def default_manifest(backup: Path) -> Path:
    return backup.with_name(backup.name + ".manifest.json")


def verify_file(backup: Path) -> dict:
    result = {
        "header_ok": False,
        "integrity_check": [],
        "sha256": None,
        "counts": {},
    }
    if not backup.exists() or not backup.is_file():
        return result
    result["header_ok"] = c.has_sqlite_magic(backup)
    if not result["header_ok"]:
        return result
    result["sha256"] = c.sha256_file(backup)
    try:
        conn, _mode = c.open_readonly(backup)
    except c.ReadOnlyOpenError as exc:
        # Abertura estritamente read-only falhou: sem fallback de escrita.
        result["open_error"] = str(exc)
        return result
    try:
        result["integrity_check"] = c.integrity_problems(conn)
        result["counts"] = c.row_counts(conn)
    finally:
        conn.close()
    return result


def compare_source(backup: Path, source: Path) -> dict:
    mismatch = {
        "counts_match": False,
        "schema_match": False,
        "count_differences": [],
    }
    try:
        src_conn, _mode = c.open_readonly(source)
        try:
            src_counts = c.row_counts(src_conn)
            src_schema = c.schema_snapshot(src_conn)
        finally:
            src_conn.close()
        bk_conn, _mode2 = c.open_readonly(backup)
        try:
            bk_counts = c.row_counts(bk_conn)
            bk_schema = c.schema_snapshot(bk_conn)
        finally:
            bk_conn.close()
    except c.ReadOnlyOpenError as exc:
        return {**mismatch, "open_error": str(exc)}
    return {
        "counts_match": bk_counts == src_counts,
        "schema_match": bk_schema == src_schema,
        "count_differences": sorted(
            name
            for name in set(bk_counts) | set(src_counts)
            if bk_counts.get(name) != src_counts.get(name)
        ),
    }


def restore_drill(backup: Path, expected_counts: dict) -> dict:
    drill = {"performed": True, "ok": False, "error": None}
    with tempfile.TemporaryDirectory(prefix="ops01d-drill-") as tmp:
        restored = Path(tmp) / "restore.db"
        try:
            shutil.copy2(backup, restored)
            check = verify_file(restored)
            drill["integrity_check"] = check["integrity_check"]
            drill["counts_match"] = check["counts"] == expected_counts
            drill["ok"] = (
                check["header_ok"]
                and not check["integrity_check"]
                and drill["counts_match"]
            )
        except OSError as exc:
            drill["error"] = str(exc)
    return drill


def _load_manifest(manifest_path: Path, report: dict) -> dict:
    """Lê o manifesto (se houver) e registra falhas estruturais no relatório."""
    if not manifest_path.exists():
        report["failures"].append("manifesto_ausente")
        return {}
    try:
        manifest = c.loads_json(manifest_path)
    except ValueError:  # JSON inválido
        report["failures"].append("manifesto_corrompido")
        return {}
    report["manifest_data"] = {
        "created_at": manifest.get("created_at"),
        "status": manifest.get("status"),
    }
    if manifest.get("status") != "verified":
        report["failures"].append("manifesto_nao_verificado")
    report["checks"]["manifest_present"] = True
    return manifest


def _record_file_checks(file_check: dict, report: dict) -> str | None:
    """Registra checks do arquivo; devolve motivo quando a abertura foi negada."""
    if file_check.get("open_error"):
        report["failures"].append("abertura_somente_leitura")
        return file_check["open_error"]
    checks = report["checks"]
    checks["header_ok"] = file_check["header_ok"]
    checks["integrity_check"] = file_check["integrity_check"]
    if not file_check["header_ok"]:
        report["failures"].append("header_invalido")
    if file_check["integrity_check"]:
        report["failures"].append("integridade")
    return None


def _record_manifest_match(manifest: dict, file_check: dict, report: dict) -> None:
    checks = report["checks"]
    expected_hash = (manifest.get("backup") or {}).get("sha256")
    expected_counts = manifest.get("tables") or {}
    if expected_hash:
        checks["sha256_match"] = file_check["sha256"] == expected_hash
        if not checks["sha256_match"]:
            report["failures"].append("checksum_divergente")
    if expected_counts:
        checks["counters_match"] = file_check["counts"] == expected_counts
        if not checks["counters_match"]:
            report["failures"].append("contagens_divergentes")


def _record_source_compare(args, backup: Path, report: dict) -> int | None:
    """Compara backup x origem atual; devolve código de saída quando aborta."""
    if not args.source:
        return None
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        return c.die(c.EXIT_SAFETY, f"origem inexistente: {source}")
    cmp_result = compare_source(backup, source)
    report["checks"]["source_comparison"] = cmp_result
    if cmp_result.get("open_error"):
        report["failures"].append("abertura_somente_leitura")
        return c.die(c.EXIT_SAFETY, cmp_result["open_error"])
    if not (cmp_result["counts_match"] and cmp_result["schema_match"]):
        report["failures"].append("divergente_da_origem_atual")
    return None


def _record_drill(args, backup: Path, expected_counts: dict, report: dict) -> None:
    if not args.restore_drill:
        return
    report["checks"]["restore_drill"] = restore_drill(backup, expected_counts)
    if not report["checks"]["restore_drill"]["ok"]:
        report["failures"].append("restore_drill_falhou")


def run(args: argparse.Namespace) -> int:
    report_refusal = c.guard_report_path(args.report)
    if report_refusal:
        return c.die(c.EXIT_SAFETY, report_refusal)
    backup = Path(args.backup).expanduser()
    if not backup.exists():
        return c.die(c.EXIT_SAFETY, f"backup inexistente: {backup}")
    backup = backup.resolve()
    manifest_path = (
        Path(args.manifest).expanduser().resolve()
        if args.manifest
        else default_manifest(backup)
    )

    report: dict = {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "verify",
        "generated_at": c.utc_now(),
        "backup": str(backup),
        "manifest": str(manifest_path),
        "checks": {},
        "failures": [],
    }

    manifest = _load_manifest(manifest_path, report)
    file_check = verify_file(backup)
    open_error = _record_file_checks(file_check, report)
    if open_error:
        report["status"] = "failed"
        report["error"] = open_error
        c.emit(report)
        return c.die(c.EXIT_SAFETY, open_error)
    _record_manifest_match(manifest, file_check, report)

    expected_counts = manifest.get("tables") or {}
    code = _record_source_compare(args, backup, report)
    if code is not None:
        return code
    _record_drill(args, backup, expected_counts, report)

    report["status"] = "ok" if not report["failures"] else "failed"
    if args.report:
        c.write_json(args.report, report)
    c.emit(report)
    if report["failures"]:
        return c.die(c.EXIT_FAIL, f"falhas: {', '.join(report['failures'])}")
    c.note("backup verificado" + (" + restore drill" if args.restore_drill else ""))
    return c.EXIT_OK


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
