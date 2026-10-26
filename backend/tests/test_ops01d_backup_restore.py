"""Testes OPS-01D: backup, verificação e restauração de SQLite.

Fluxo completo em diretório temporário com dados sintéticos: a origem nunca
muda (bytes e sidecars), relatórios nunca são sobrescritos, restauração
exige --execute e recusa destino já existente.
"""

import sys
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "home-server" / "data"
if str(_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(_DATA_DIR))

import common as c  # noqa: E402
import db_backup  # noqa: E402
import db_diagnose  # noqa: E402
import db_restore  # noqa: E402
import db_verify  # noqa: E402
import synthetic  # noqa: E402


def _source(tmp_path: Path) -> Path:
    src = tmp_path / "legacy.db"
    synthetic.create_source_db(src)
    return src


def _backup(tmp_path: Path, src: Path, report: Path) -> tuple[Path, Path]:
    out = tmp_path / "out"
    rc = db_backup.main(["--source", str(src), "--out", str(out), "--report", str(report)])
    assert rc == c.EXIT_OK, f"backup rc={rc}"
    backups = sorted(out.glob("*.db"))
    assert len(backups) == 1
    manifest = Path(str(backups[0]) + ".manifest.json")
    assert manifest.exists()
    return backups[0], manifest


def test_backup_creates_verified_artifacts_and_keeps_source(tmp_path):
    src = _source(tmp_path)
    src_bytes = src.read_bytes()
    src_mtime = src.stat().st_mtime_ns
    backup, manifest = _backup(tmp_path, src, tmp_path / "backup.json")
    assert backup.exists() and manifest.exists()
    report = c.loads_json(tmp_path / "backup.json")
    assert report["status"] == "verified"
    assert c.sha256_file(src) == c.sha256_file(src)  # arquivo segue legível
    assert src.read_bytes() == src_bytes
    assert src.stat().st_mtime_ns == src_mtime
    assert not Path(str(src) + "-wal").exists()
    assert not Path(str(src) + "-shm").exists()
    assert Path(report["backup"]["path"]) == backup
    assert report["backup"]["sha256"] == c.sha256_file(backup)
    assert Path(report["manifest_path"]) == manifest


def test_backup_missing_source_is_refused(tmp_path):
    rc = db_backup.main(
        [
            "--source",
            str(tmp_path / "nao_existe.db"),
            "--out",
            str(tmp_path / "out"),
            "--report",
            str(tmp_path / "r.json"),
        ]
    )
    assert rc == c.EXIT_SAFETY


def test_backup_report_is_never_overwritten(tmp_path):
    src = _source(tmp_path)
    report = tmp_path / "report.json"
    _backup(tmp_path, src, report)
    first = report.read_bytes()
    out2 = tmp_path / "out2"
    rc = db_backup.main(
        [
            "--source",
            str(src),
            "--out",
            str(out2),
            "--dry-run",
            "--report",
            str(report),
        ]
    )
    assert rc == c.EXIT_SAFETY
    assert report.read_bytes() == first


def test_diagnose_is_read_only_and_refuses_report_overwrite(tmp_path):
    src = _source(tmp_path)
    src_bytes = src.read_bytes()
    report = tmp_path / "diag.json"
    rc = db_diagnose.main(["--source", str(src), "--report", str(report)])
    assert rc == c.EXIT_OK
    assert src.read_bytes() == src_bytes
    assert not Path(str(src) + "-wal").exists()
    first = report.read_bytes()
    rc = db_diagnose.main(["--source", str(src), "--report", str(report)])
    assert rc == c.EXIT_SAFETY
    assert report.read_bytes() == first


def test_restore_dry_run_creates_nothing(tmp_path):
    src = _source(tmp_path)
    backup, _manifest = _backup(tmp_path, src, tmp_path / "backup.json")
    dest = tmp_path / "restored.db"
    rc = db_restore.main(
        [
            "--backup",
            str(backup),
            "--dest",
            str(dest),
            "--report",
            str(tmp_path / "restore.json"),
        ]
    )
    assert rc == c.EXIT_OK
    assert not dest.exists()


def test_restore_execute_then_second_run_blocked(tmp_path):
    src = _source(tmp_path)
    backup, _manifest = _backup(tmp_path, src, tmp_path / "backup.json")
    dest = tmp_path / "restored.db"
    rc = db_restore.main(
        [
            "--backup",
            str(backup),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(tmp_path / "restore.json"),
        ]
    )
    assert rc == c.EXIT_OK
    assert dest.exists()
    src_conn, _src_mode = c.open_readonly(src)
    try:
        src_counts = c.row_counts(src_conn)
    finally:
        src_conn.close()
    conn, _mode = c.open_readonly(dest)
    try:
        counts = c.row_counts(conn)
    finally:
        conn.close()
    # restauração é cópia fiel: até linhas que o ensaio bloquearia
    assert counts == src_counts
    assert counts["clients"] == 7  # 5 válidas + tenant nulo + duplicata
    restored_sha = c.sha256_file(dest)
    rc = db_restore.main(
        [
            "--backup",
            str(backup),
            "--dest",
            str(dest),
            "--execute",
            "--report",
            str(tmp_path / "restore2.json"),
        ]
    )
    assert rc == c.EXIT_SAFETY
    assert c.sha256_file(dest) == restored_sha


def test_verify_detects_corrupted_backup(tmp_path):
    src = _source(tmp_path)
    backup, manifest = _backup(tmp_path, src, tmp_path / "backup.json")
    data = bytearray(backup.read_bytes())
    data[len(data) // 2] ^= 0xFF
    backup.write_bytes(bytes(data))
    rc = db_verify.main(
        [
            "--backup",
            str(backup),
            "--manifest",
            str(manifest),
            "--report",
            str(tmp_path / "verify.json"),
        ]
    )
    assert rc != c.EXIT_OK


def test_verify_with_restore_drill_passes(tmp_path):
    src = _source(tmp_path)
    backup, _manifest = _backup(tmp_path, src, tmp_path / "backup.json")
    rc = db_verify.main(
        [
            "--backup",
            str(backup),
            "--source",
            str(src),
            "--restore-drill",
            "--report",
            str(tmp_path / "verify.json"),
        ]
    )
    assert rc == c.EXIT_OK
    report = c.loads_json(tmp_path / "verify.json")
    assert report["status"] == "ok"
