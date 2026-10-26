"""Utilitários comuns dos scripts de dados do Home Server (OPS-01D).

Invariante central de todo script deste pacote: a origem nunca é modificada.
Conexões de leitura são ESTRITAMENTE ``mode=ro`` (sem fallback de escrita e
sem criar sidecars na origem — ver ``open_readonly``); todo artefato de saída
é criado em caminho explícito, com nome único, e recusa sobrescrever arquivo
existente (inclusive relatórios — ver ``guard_report_path``).

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


class ReadOnlyOpenError(RuntimeError):
    """Origem não pôde ser aberta estritamente somente-leitura.

    Levantada em vez de cair para uma conexão com capacidade de escrita.
    Nenhum arquivo da origem é criado, modificado ou teve permissão alterada.
    """


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


def journal_write_version(path: str | Path) -> int | None:
    """Byte 18 do header SQLite sem abrir o banco: 1=rollback, 2=WAL."""
    try:
        with open(path, "rb") as fh:
            fh.seek(18)
            byte = fh.read(1)
    except OSError:
        return None
    return byte[0] if byte else None


def _sidecar_state(base: Path) -> dict[str, tuple[int, int] | None]:
    """(tamanho, mtime_ns) dos sidecars -wal/-shm — para detectar mudanças."""
    state: dict[str, tuple[int, int] | None] = {}
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(base) + suffix)
        try:
            st = sidecar.stat()
            state[suffix] = (st.st_size, st.st_mtime_ns)
        except OSError:
            state[suffix] = None
    return state


def open_readonly(path: str | Path) -> tuple[sqlite3.Connection, str]:
    """Abre a origem ESTRITAMENTE somente-leitura (nunca com capacidade de escrita).

    Política por tipo de journal (byte 18 do header, lido sem abrir o banco):

    * rollback (1): ``mode=ro``;
    * WAL (2) com ``-shm`` presente: ``mode=ro`` (leitura não altera sidecars);
    * WAL (2) sem ``-shm`` e sem ``-wal`` (fecho limpo): ``mode=ro&immutable=1``
      — o ``mode=ro`` puro faria o SQLite criar ``-shm``/``-wal`` na origem;
    * WAL (2) sem ``-shm`` com ``-wal`` pendente: ``ReadOnlyOpenError`` — a
      recuperação de transações pendentes exigiria escrita na origem.

    Se a abertura falhar, ou se qualquer sidecar aparecer/mudar durante ela,
    ``ReadOnlyOpenError`` é levantado: sem fallback silencioso, sem alteração
    de permissões, sem criar ou modificar banco/sidecars na origem.
    """
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise ReadOnlyOpenError(f"arquivo inexistente: {resolved}")
    params = "mode=ro"
    if journal_write_version(resolved) == 2:
        has_shm = Path(str(resolved) + "-shm").exists()
        wal_path = Path(str(resolved) + "-wal")
        if not has_shm:
            if wal_path.exists() and wal_path.stat().st_size > 0:
                raise ReadOnlyOpenError(
                    "WAL com transações pendentes e sem -shm: recuperação "
                    f"exigiria escrita na origem ({resolved.name})"
                )
            params = "mode=ro&immutable=1"
    before = _sidecar_state(resolved)
    uri = f"file:{resolved.as_posix()}?{params}"
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        raise ReadOnlyOpenError(
            f"abertura somente-leitura recusada: {resolved.name} ({exc})"
        ) from exc
    if before != _sidecar_state(resolved):
        conn.close()
        raise ReadOnlyOpenError(
            "sidecars da origem mudaram durante a abertura "
            f"({resolved.name}) — escritor externo ativo?"
        )
    return conn, ("ro-immutable" if "immutable=1" in params else "ro")


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


def guard_report_path(path: str | Path | None) -> str | None:
    """Relatório existente é preservado: sobrescrita de ``--report`` proibida."""
    if path and Path(path).exists():
        return f"relatório existente (sobrescrita proibida): {path}"
    return None


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
