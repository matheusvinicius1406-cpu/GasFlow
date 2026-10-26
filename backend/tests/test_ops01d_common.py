"""Testes OPS-01D: utilitários comuns — leitura fail-closed e guardas.

A origem NUNCA pode ser alterada: estes testes provam que open_readonly não
cria sidecars, não faz fallback de escrita e recusa recuperação de WAL
pendente. Dados sempre sintéticos em diretório temporário.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "home-server" / "data"
if str(_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(_DATA_DIR))

import common as c  # noqa: E402


def _plain_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('x')")
        conn.commit()
    finally:
        conn.close()


def _clean_wal_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('x')")
        conn.commit()
    finally:
        conn.close()


def _pending_wal_copy(src: Path, dst: Path) -> None:
    """Simula crash: main + -wal commitados, sem -shm."""
    conn = sqlite3.connect(str(src))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('pending')")
        conn.commit()
        wal = Path(str(src) + "-wal")
        assert wal.exists() and wal.stat().st_size > 0
        dst.write_bytes(src.read_bytes())
        Path(str(dst) + "-wal").write_bytes(wal.read_bytes())
    finally:
        conn.close()


def _sidecars(path: Path) -> list[Path]:
    return [Path(str(path) + s) for s in ("-wal", "-shm")]


def test_open_readonly_rollback_journal_is_pure_read(tmp_path):
    db = tmp_path / "legacy.db"
    _plain_db(db)
    before = {p.name: p.stat().st_mtime_ns for p in _sidecars(db) if p.exists()}
    conn, mode = c.open_readonly(db)
    try:
        assert mode == "ro"
        assert c.journal_write_version(db) == 1
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    finally:
        conn.close()
    after = {p.name: p.stat().st_mtime_ns for p in _sidecars(db) if p.exists()}
    assert before == after == {}


def test_open_readonly_clean_wal_uses_immutable(tmp_path):
    db = tmp_path / "wal_clean.db"
    _clean_wal_db(db)
    assert c.journal_write_version(db) == 2
    assert not any(p.exists() for p in _sidecars(db))
    conn, mode = c.open_readonly(db)
    try:
        assert mode == "ro-immutable"
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    finally:
        conn.close()
    assert not any(p.exists() for p in _sidecars(db))


def test_open_readonly_pending_wal_without_shm_is_refused(tmp_path):
    db = tmp_path / "wal_pending.db"
    _pending_wal_copy(tmp_path / "seed.db", db)
    with pytest.raises(c.ReadOnlyOpenError):
        c.open_readonly(db)
    assert not Path(str(db) + "-shm").exists()


def test_open_readonly_wal_with_shm_does_not_touch_sidecars(tmp_path):
    db = tmp_path / "wal_live.db"
    writer = sqlite3.connect(str(db))
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        writer.execute("INSERT INTO t (v) VALUES ('live')")
        writer.commit()
        before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in _sidecars(db) if p.exists()}
        assert before, "cenario precisa de -wal/-shm vivos"
        conn, mode = c.open_readonly(db)
        try:
            assert mode == "ro"
            assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
        finally:
            conn.close()
        after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in _sidecars(db) if p.exists()}
        assert before == after
    finally:
        writer.close()


def test_open_readonly_missing_file_is_refused(tmp_path):
    with pytest.raises(c.ReadOnlyOpenError):
        c.open_readonly(tmp_path / "nao_existe.db")


def test_has_sqlite_magic_and_sha256(tmp_path):
    db = tmp_path / "magic.db"
    _plain_db(db)
    texto = tmp_path / "not.db"
    texto.write_text("nada de sqlite aqui", encoding="utf-8")
    assert c.has_sqlite_magic(db) is True
    assert c.has_sqlite_magic(texto) is False
    assert c.has_sqlite_magic(tmp_path / "missing.db") is False
    digest = c.sha256_file(db)
    assert digest == c.sha256_file(db)
    db.write_bytes(db.read_bytes() + b"\x00")
    assert c.sha256_file(db) != digest


def test_guard_report_path_rules(tmp_path):
    assert c.guard_report_path(None) is None
    novo = tmp_path / "rel.json"
    assert c.guard_report_path(novo) is None
    novo.write_text("{}", encoding="utf-8")
    assert "sobrescrita proibida" in (c.guard_report_path(novo) or "")
    assert c.guard_report_path(tmp_path / "ausente" / "rel.json") is None


def test_write_json_preserves_existing_and_has_no_bom(tmp_path):
    destino = tmp_path / "rel.json"
    c.write_json(destino, {"a": 1})
    assert not destino.read_bytes().startswith(b"\xef\xbb\xbf")
    assert json.loads(destino.read_text(encoding="utf-8")) == {"a": 1}
    with pytest.raises(FileExistsError):
        c.write_json(destino, {"a": 2})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"a": 1}
