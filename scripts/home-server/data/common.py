"""Utilitários comuns dos scripts de dados do Home Server (OPS-01D).

Invariante central de todo script deste pacote: a origem nunca é modificada.
Conexões de leitura usam a URI ``mode=ro``; todo artefato de saída é criado
em caminho explícito, com nome único, e recusa sobrescrever arquivo existente.

Nada aqui lê conteúdo de linhas (sem PII em relatórios): relatórios contêm
apenas caminhos, contagens, nomes de tabela/coluna, chaves primárias e motivos.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_SAFETY = 2
EXIT_PARTIAL = 3

TOOL = "ops01d"
TOOL_VERSION = "1.0.0"

SQLITE_MAGIC = b"SQLite format 3\x00"
_CHUNK = 1 << 20


def utc_now() -> str:
    """Timestamp ISO-8601 em UTC, formato canônico dos manifestos."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug_ts() -> str:
    """Timestamp compacto e ordenável para nomes de arquivo (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_from_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def has_sqlite_magic(path: str | Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        return False


def open_readonly(path: str | Path) -> tuple[sqlite3.Connection, str]:
    """Abre a origem somente-leitura; registra o modo efetivamente usado.

    Modo ``ro`` é o padrão. O fallback (leitura normal) existe porque um
    SQLite em WAL com ``-shm`` ausente recusa conexão ro — o fallback não
    altera o conteúdo, apenas pode criar sidecar de WAL.
    """
    resolved = Path(path).resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("SELECT 1").fetchone()
        return conn, "ro"
    except sqlite3.Error:
        conn = sqlite3.connect(str(resolved))
        return conn, "rw-fallback"


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in table_names(conn):
        counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    return counts


def schema_snapshot(conn: sqlite3.Connection) -> dict[str, dict[str, dict[str, Any]]]:
    """Estrutura liga: {tabela: {coluna: {type, notnull, pk, dflt}}}. Sem dados."""
    snapshot: dict[str, dict[str, dict[str, Any]]] = {}
    for name in table_names(conn):
        cols: dict[str, dict[str, Any]] = {}
        for col in conn.execute(f'PRAGMA table_info("{name}")').fetchall():
            _cid, col_name, col_type, notnull, _dflt, pk = col
            cols[col_name] = {
                "type": (col_type or "").upper(),
                "notnull": bool(notnull),
                "pk": bool(pk),
            }
        snapshot[name] = cols
    return snapshot


def integrity_problems(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    return [r[0] for r in rows if r[0] != "ok"]


def data_version(conn: sqlite3.Connection) -> int | None:
    """Versão lógica do arquivo (muda quando OUTRA conexão altera o banco)."""
    try:
        return int(conn.execute("PRAGMA data_version").fetchone()[0])
    except sqlite3.Error:
        return None


def pragma_str(conn: sqlite3.Connection, name: str) -> str | None:
    try:
        row = conn.execute(f"PRAGMA {name}").fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else str(row[0])


def scalar_setting(conn: sqlite3.Connection, table: str, column: str) -> Any:
    """Lê um valor escalar de tabela de metadados (ex.: alembic_version)."""
    try:
        row = conn.execute(f'SELECT "{column}" FROM "{table}" LIMIT 1').fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else row[0]


def write_json(path: str | Path, data: Any, *, overwrite: bool = False) -> None:
    dest = Path(path)
    if dest.exists() and not overwrite:
        raise FileExistsError(f"recusando sobrescrever: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    tmp.replace(dest)


def loads_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def emit(data: Any) -> None:
    """Relatório JSON canônico na stdout (humano/progresso vai para stderr)."""
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")


def note(message: str) -> None:
    sys.stderr.write(f"[{TOOL}] {message}\n")


def die(code: int, message: str) -> int:
    note(f"ERRO: {message}")
    return code
