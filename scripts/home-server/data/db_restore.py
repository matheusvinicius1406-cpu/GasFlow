#!/usr/bin/env python3
"""Restauração de backup SQLite em ambiente isolado (OPS-01D, Etapa 2).

Dry-run por padrão: sem ``--execute`` só planeja e valida. Guardas:

- recusa destino existente (nunca sobrescreve);
- recusa destino igual ao caminho de origem registrado no manifesto
  (impede "restaurar por cima" do banco operacional);
- exige manifesto ``status=verified`` com checksum conferido;
- após a cópia, revalida header/integridade/contagens no destino; falha
  remove apenas o arquivo que esta execução criou.

Uso:
    python scripts/home-server/data/db_restore.py --backup b.db --dest /tmp/x.db
    python ... --backup b.db --dest /tmp/x.db --execute

Códigos: 0 ok | 1 restauração/verificação falhou | 2 segurança.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402
import db_verify  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, help="arquivo .db do backup")
    parser.add_argument("--dest", required=True, help="arquivo de destino (novo)")
    parser.add_argument("--manifest", help="manifesto JSON (padrão: ao do backup)")
    parser.add_argument("--execute", action="store_true", help="realiza a cópia")
    parser.add_argument("--report", help="gravar o relatório JSON em arquivo")
    return parser.parse_args(argv)


def load_verified_manifest(
    backup: Path, manifest_path: Path | None
) -> tuple[dict, Path]:
    path = manifest_path or db_verify.default_manifest(backup)
    if not path.exists():
        raise FileNotFoundError(f"manifesto ausente: {path}")
    manifest = c.loads_json(path)
    if manifest.get("status") != "verified":
        raise ValueError("manifesto não está em status=verified")
    expected = (manifest.get("backup") or {}).get("sha256")
    actual = c.sha256_file(backup)
    if not expected or expected != actual:
        raise ValueError("checksum do backup diverge do manifesto")
    return manifest, path


def guard_destination(dest: Path, manifest: dict, backup: Path) -> str | None:
    if dest.exists():
        return f"destino já existe (sobrescrita proibida): {dest}"
    if dest == backup:
        return "destino coincide com o próprio arquivo de backup"
    source_path = Path((manifest.get("source") or {}).get("path", ""))
    try:
        if source_path.is_absolute() and dest.resolve() == source_path.resolve():
            return f"destino coincide com o banco de origem: {source_path}"
    except OSError:
        pass
    if dest.parent.exists() and not dest.parent.is_dir():
        return f"parente do destino não é diretório: {dest.parent}"
    return None


def _copy_and_verify(backup: Path, dest: Path, manifest: dict) -> dict:
    """Cópia + revalidação no destino; levanta exceção se reprovado."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, dest)
    check = db_verify.verify_file(dest)
    counters_match = check["counts"] == (manifest.get("tables") or {})
    verification = {
        "header_ok": check["header_ok"],
        "integrity_check": check["integrity_check"],
        "counters_match": counters_match,
    }
    if not (check["header_ok"] and not check["integrity_check"] and counters_match):
        raise RuntimeError(f"destino reprovado na verificação: {verification}")
    return verification


def _discard_dest(dest: Path) -> None:
    try:
        if dest.exists():
            dest.unlink()
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    backup = Path(args.backup).expanduser()
    if not backup.exists():
        return c.die(c.EXIT_SAFETY, f"backup inexistente: {backup}")
    backup = backup.resolve()
    dest = Path(args.dest).expanduser()

    try:
        manifest, manifest_path = load_verified_manifest(
            backup,
            Path(args.manifest).expanduser() if args.manifest else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        return c.die(c.EXIT_SAFETY, str(exc))

    refusal = guard_destination(dest, manifest, backup)
    if refusal:
        return c.die(c.EXIT_SAFETY, refusal)

    report = {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "restore",
        "generated_at": c.utc_now(),
        "mode": "execute" if args.execute else "dry-run",
        "backup": str(backup),
        "manifest": str(manifest_path),
        "dest": str(dest),
        "source_isolated_from": manifest.get("source", {}).get("path"),
        "expected_tables": len(manifest.get("tables") or {}),
    }

    if not args.execute:
        report["status"] = "dry-run"
        if args.report:
            c.write_json(args.report, report, overwrite=True)
        c.emit(report)
        c.note("dry-run: nada copiado (use --execute)")
        return c.EXIT_OK

    try:
        report["verification"] = _copy_and_verify(backup, dest, manifest)
    except (OSError, RuntimeError) as exc:
        _discard_dest(dest)
        report["status"] = "failed"
        report["error"] = str(exc)
        if args.report:
            c.write_json(args.report, report, overwrite=True)
        c.emit(report)
        return c.die(c.EXIT_FAIL, str(exc))

    report["status"] = "restored"
    report["restored_size_bytes"] = dest.stat().st_size
    if args.report:
        c.write_json(args.report, report, overwrite=True)
    c.emit(report)
    c.note(f"backup restaurado em ambiente isolado: {dest}")
    return c.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
