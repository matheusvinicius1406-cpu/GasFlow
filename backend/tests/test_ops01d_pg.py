"""Testes OPS-01D: ferramentas PostgreSQL com mocks (pg_backup/pg_restore).

Nenhum servidor é contatado: o modo --mock cobre o fluxo completo de dump e
restauração, e os testes negativos provam as guardas (relatório preservado,
DSN com senha embutida recusada, dump corrompido recusado, binário ausente).
"""

import json
import sys
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "home-server" / "data"
if str(_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(_DATA_DIR))

import common as c  # noqa: E402
import pg_backup  # noqa: E402
import pg_restore  # noqa: E402


def _mock_dump(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "out"
    rc = pg_backup.main(
        [
            "--mock",
            "--execute",
            "--out",
            str(out),
            "--report",
            str(tmp_path / "backup.json"),
        ]
    )
    assert rc == c.EXIT_OK
    dumps = sorted(out.glob("*.dump"))
    assert len(dumps) == 1
    manifest = Path(str(dumps[0]) + ".manifest.json")
    assert manifest.exists()
    return dumps[0], manifest


def test_pg_backup_mock_dry_run_writes_nothing(tmp_path):
    rc = pg_backup.main(["--mock", "--out", str(tmp_path / "out")])
    assert rc == c.EXIT_OK
    assert not (tmp_path / "out").exists()


def test_pg_backup_mock_execute_builds_dump_and_manifest(tmp_path):
    dump, manifest = _mock_dump(tmp_path)
    assert dump.read_bytes().startswith(pg_backup.PG_MAGIC)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["status"] == "verified"
    assert data["mode"] == "mock"
    assert data["dump"]["sha256"] == c.sha256_file(dump)
    report = c.loads_json(tmp_path / "backup.json")
    assert report["status"] == "verified"
    assert report["dsn_target"] == {"host": "mock", "database": "mock"}


def test_pg_backup_report_is_never_overwritten(tmp_path):
    report = tmp_path / "rel.json"
    report.write_text("{}", encoding="utf-8")
    rc = pg_backup.main(["--mock", "--execute", "--out", str(tmp_path / "out"), "--report", str(report)])
    assert rc == c.EXIT_SAFETY
    assert report.read_text(encoding="utf-8") == "{}"


def test_pg_backup_rejects_embedded_password_and_bad_label(tmp_path):
    rc = pg_backup.main(
        [
            "--out",
            str(tmp_path / "out"),
            "--dsn",
            "postgresql://user:segredo@host/db",
            "--execute",
        ]
    )
    assert rc == c.EXIT_SAFETY
    rc = pg_backup.main(["--out", str(tmp_path / "out"), "--label", "../fuga", "--execute"])
    assert rc == c.EXIT_SAFETY


def test_pg_backup_real_mode_requires_dsn_and_binary(tmp_path):
    rc = pg_backup.main(["--out", str(tmp_path / "out"), "--execute"])
    assert rc == c.EXIT_SAFETY  # sem --dsn
    rc = pg_backup.main(
        [
            "--out",
            str(tmp_path / "out"),
            "--dsn",
            "postgresql://host/db",
            "--execute",
            "--pg-bin",
            str(tmp_path / "pg_dump_falso"),
        ]
    )
    assert rc == c.EXIT_FAIL  # binário ausente


def test_pg_restore_verifies_and_refuses_corruption(tmp_path):
    dump, manifest = _mock_dump(tmp_path)
    rc = pg_restore.main(
        [
            "--dump",
            str(dump),
            "--manifest",
            str(manifest),
            "--report",
            str(tmp_path / "restore.json"),
        ]
    )
    assert rc == c.EXIT_OK
    report = c.loads_json(tmp_path / "restore.json")
    assert report["status"] == "verified"
    assert report["verification"]["manifest_checked"] is True
    data = bytearray(dump.read_bytes())
    data[-1] ^= 0xFF
    dump.write_bytes(bytes(data))
    rc = pg_restore.main(
        ["--dump", str(dump), "--manifest", str(manifest), "--report", str(tmp_path / "restore2.json")]
    )
    assert rc == c.EXIT_SAFETY
    assert "diverge" in c.loads_json(tmp_path / "restore2.json")["error"]


def test_pg_restore_mock_execute_and_missing_dump(tmp_path):
    dump, manifest = _mock_dump(tmp_path)
    rc = pg_restore.main(
        [
            "--dump",
            str(dump),
            "--manifest",
            str(manifest),
            "--mock",
            "--execute",
            "--report",
            str(tmp_path / "restore.json"),
        ]
    )
    assert rc == c.EXIT_OK
    assert c.loads_json(tmp_path / "restore.json")["status"] == "restored-mock"
    rc = pg_restore.main(["--dump", str(tmp_path / "nao_existe.dump"), "--mock", "--execute"])
    assert rc == c.EXIT_SAFETY


def test_pg_restore_rejects_non_pg_dump_file(tmp_path):
    estranho = tmp_path / "estranho.dump"
    estranho.write_bytes(b"isto nao e um dump postgres")
    rc = pg_restore.main(["--dump", str(estranho), "--mock", "--execute"])
    assert rc == c.EXIT_SAFETY
