"""Testes OPS-01D: ensaio de migração (migrate_rehearsal).

Cobre dry-run, execute com marcador, reconciliação idempotente, bloqueios de
segurança (origem alheia, mesmo nome, PostgreSQL, WhatsApp), política de
tenant, regras por linha (órfão, cast, unicidade, cross-tenant, ledger
imutável) e rollback com remoção do alvo em falha injetada.
"""

import sqlite3
import sys
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "home-server" / "data"
if str(_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(_DATA_DIR))

import common as c  # noqa: E402
import migrate_rehearsal as mr  # noqa: E402
import synthetic  # noqa: E402


def _source(tmp_path: Path, name: str = "legacy.db") -> Path:
    src = tmp_path / name
    synthetic.create_source_db(src)
    return src


def _run(source: Path, target: Path, report: Path, *extra: str) -> int:
    return mr.main(
        [
            "--source",
            str(source),
            "--target",
            str(target),
            "--report",
            str(report),
            *extra,
        ]
    )


def _plan_by_table(report: dict, table: str) -> dict:
    for plan in report["plans"]:
        if plan["table"] == table:
            return plan
    raise AssertionError(f"plano ausente para {table}")


def _issue_rules(report: dict) -> set[str]:
    return {issue["rule"] for issue in report["issues"]}


def test_dry_run_plans_but_writes_nothing(tmp_path):
    src = _source(tmp_path)
    target = tmp_path / "target.db"
    rc = _run(src, target, tmp_path / "dry.json")
    assert rc == c.EXIT_PARTIAL
    assert not target.exists()
    report = c.loads_json(tmp_path / "dry.json")
    assert report["status"] == "dry-run-partial"
    assert report["mode"] == "dry-run"
    assert report["target"]["plan"] == "fresh"
    assert _plan_by_table(report, "old_phones")["action"] == "block"
    assert _plan_by_table(report, "old_phones")["reason"] == ("tabela_legada_sem_equivalente")
    assert _plan_by_table(report, "clients")["action"] == "migrate"


def test_execute_creates_target_with_marker_and_expected_counts(tmp_path):
    src = _source(tmp_path)
    target = tmp_path / "target.db"
    rc = _run(src, target, tmp_path / "run.json", "--execute")
    assert rc == c.EXIT_PARTIAL  # bloqueios esperados (old_phones etc.)
    assert target.exists()
    report = c.loads_json(tmp_path / "run.json")
    assert report["status"] == "migrated-partial"
    assert report["target"]["created"] is True
    assert report["verification"]["marker"] == "escrito"
    for table, count in synthetic.EXPECTED_DEFAULT_COUNTS.items():
        assert report["summary"]["rows_planned"][table] == count, table
    conn, _mode = c.open_readonly(target)
    try:
        marker = conn.execute("SELECT source_kind FROM _ops01d_run").fetchone()
        assert marker is not None and marker[0] == "backend"
        for table, count in synthetic.EXPECTED_DEFAULT_COUNTS.items():
            got = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            assert got == count, table
    finally:
        conn.close()


def test_reexecution_reconciles_read_only(tmp_path):
    src = _source(tmp_path)
    target = tmp_path / "target.db"
    assert _run(src, target, tmp_path / "a.json", "--execute") == c.EXIT_PARTIAL
    target_sha = c.sha256_file(target)
    rc = _run(src, target, tmp_path / "b.json", "--execute")
    assert rc == c.EXIT_PARTIAL
    report = c.loads_json(tmp_path / "b.json")
    assert report["status"] == "reconciled-partial"
    assert report["reconcile"]["status"] == "ok"
    assert c.sha256_file(target) == target_sha  # nada foi reescrito


def test_different_source_is_blocked(tmp_path):
    src = _source(tmp_path)
    target = tmp_path / "target.db"
    assert _run(src, target, tmp_path / "a.json", "--execute") == c.EXIT_PARTIAL
    other = _source(tmp_path, "legacy2.db")
    with sqlite3.connect(str(other)) as conn:
        conn.execute("DELETE FROM orders WHERE id = 3")
        conn.commit()
    rc = _run(other, target, tmp_path / "b.json", "--execute")
    assert rc == c.EXIT_SAFETY
    report = c.loads_json(tmp_path / "b.json")
    assert report["status"] == "blocked"


def test_identical_copy_reconciles(tmp_path):
    src = _source(tmp_path)
    target = tmp_path / "target.db"
    assert _run(src, target, tmp_path / "a.json", "--execute") == c.EXIT_PARTIAL
    copia = tmp_path / "copia.db"
    copia.write_bytes(src.read_bytes())
    rc = _run(copia, target, tmp_path / "b.json", "--execute")
    assert rc == c.EXIT_PARTIAL
    assert c.loads_json(tmp_path / "b.json")["status"] == "reconciled-partial"


def test_strict_blocks_writes_when_issues_exist(tmp_path):
    src = _source(tmp_path)
    target = tmp_path / "target.db"
    rc = _run(src, target, tmp_path / "strict.json", "--execute", "--strict")
    assert rc == c.EXIT_PARTIAL
    assert not target.exists()
    assert c.loads_json(tmp_path / "strict.json")["status"] == "strict-blocked"


def test_injected_load_failure_rolls_back_and_removes_target(tmp_path, monkeypatch):
    src = _source(tmp_path)
    target = tmp_path / "target.db"

    def boom(conn, validation, metadata):
        raise RuntimeError("falha injetada de carga")

    monkeypatch.setattr(mr, "_load_rows", boom)
    rc = _run(src, target, tmp_path / "fail.json", "--execute")
    assert rc == c.EXIT_FAIL
    assert not target.exists()
    report = c.loads_json(tmp_path / "fail.json")
    assert report["status"] == "failed"
    assert "falha injetada" in report["error"]


def test_injected_financial_mismatch_rolls_back(tmp_path, monkeypatch):
    src = _source(tmp_path)
    target = tmp_path / "target.db"

    def diff_pegajoso(conn, validation, metadata):
        return [{"table": "orders", "column": "total", "expected": "1.00", "actual": "2.00"}]

    monkeypatch.setattr(mr, "_financial_diffs", diff_pegajoso)
    rc = _run(src, target, tmp_path / "fin.json", "--execute")
    assert rc == c.EXIT_FAIL
    assert not target.exists()
    assert "financeiro" in c.loads_json(tmp_path / "fin.json")["error"]


def test_report_overwrite_is_refused(tmp_path):
    src = _source(tmp_path)
    report = tmp_path / "rel.json"
    report.write_text("{}", encoding="utf-8")
    rc = _run(src, tmp_path / "t.db", report)
    assert rc == c.EXIT_SAFETY
    assert report.read_text(encoding="utf-8") == "{}"


def test_target_named_like_source_is_refused(tmp_path):
    src = _source(tmp_path)
    rc = mr.main(["--source", str(src), "--target", str(tmp_path / "legacy.db"), "--execute"])
    assert rc == c.EXIT_SAFETY


def test_postgresql_target_is_refused(tmp_path):
    src = _source(tmp_path)
    rc = mr.main(["--source", str(src), "--target", "postgresql://user@host/db", "--execute"])
    assert rc == c.EXIT_SAFETY


def test_whatsapp_service_source_is_always_refused(tmp_path):
    src = tmp_path / "zap.db"
    conn = sqlite3.connect(str(src))
    try:
        conn.execute("CREATE TABLE clients (id INTEGER)")
        conn.execute("CREATE TABLE _migration_tracking (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    rc = mr.main(
        [
            "--source",
            str(src),
            "--target",
            str(tmp_path / "t.db"),
            "--allow-unknown-source",
            "--execute",
        ]
    )
    assert rc == c.EXIT_SAFETY


def test_unknown_source_gate(tmp_path):
    src = tmp_path / "estranho.db"
    conn = sqlite3.connect(str(src))
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    rc = _run(src, tmp_path / "t.db", tmp_path / "a.json")
    assert rc == c.EXIT_SAFETY  # sem --allow-unknown-source
    rc = _run(src, tmp_path / "t.db", tmp_path / "b.json", "--allow-unknown-source")
    assert rc == c.EXIT_PARTIAL  # foo vira tabela legada bloqueada
    assert _plan_by_table(c.loads_json(tmp_path / "b.json"), "foo")["action"] == ("block")
    vazio = tmp_path / "vazio.db"
    conn = sqlite3.connect(str(vazio))
    try:
        conn.execute("CREATE TABLE tmp (id INTEGER)")
        conn.commit()
        conn.execute("DROP TABLE tmp")
        conn.commit()
    finally:
        conn.close()  # arquivo com header SQLite e nenhuma tabela
    rc = _run(vazio, tmp_path / "t2.db", tmp_path / "c.json", "--allow-unknown-source")
    assert rc == c.EXIT_OK  # sem tabelas e sem bloqueios
    assert c.loads_json(tmp_path / "c.json")["status"] == "dry-run"


def test_null_tenant_policy_block_and_platform(tmp_path):
    src = _source(tmp_path)
    rc = _run(src, tmp_path / "t.db", tmp_path / "block.json")
    assert rc == c.EXIT_PARTIAL
    report = c.loads_json(tmp_path / "block.json")
    assert "null_tenant" in _issue_rules(report)
    assert report["summary"]["rows_planned"]["clients"] == 5
    assert report["tenants"].get("default") == 22  # distribuição global
    rc = _run(
        src,
        tmp_path / "t2.db",
        tmp_path / "plat.json",
        "--null-tenant",
        "platform",
    )
    assert rc == c.EXIT_PARTIAL
    report = c.loads_json(tmp_path / "plat.json")
    assert report["summary"]["rows_planned"]["clients"] == 6
    assert report["tenants"].get("default") == 23  # linha nula preenchida


def test_row_rules_reported_from_default_seed(tmp_path):
    src = _source(tmp_path)
    rc = _run(src, tmp_path / "t.db", tmp_path / "dry.json")
    assert rc == c.EXIT_PARTIAL
    report = c.loads_json(tmp_path / "dry.json")
    rules = _issue_rules(report)
    assert "null_tenant" in rules
    assert "unique_violation" in rules
    assert "orphan_reference" in rules
    assert "cast_int_failed" in rules
    assert report["summary"]["rows_planned"]["orders"] == 3
    assert report["summary"]["rows_planned"]["financial_ledger"] == 4


def test_immutable_ledger_with_invalid_row_blocks_whole_table(tmp_path):
    src = _source(tmp_path)
    conn = sqlite3.connect(str(src))
    try:
        conn.execute(
            "INSERT INTO financial_ledger VALUES"
            " ('default', 99, 'ERRO', 'nao-numerico', NULL, NULL, 'x',"
            " '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    rc = _run(src, tmp_path / "t.db", tmp_path / "dry.json")
    assert rc == c.EXIT_PARTIAL
    report = c.loads_json(tmp_path / "dry.json")
    plan = _plan_by_table(report, "financial_ledger")
    assert plan["action"] == "block"
    assert plan["reason"] == "ledger_imutavel_com_linhas_invalidas"
    assert "financial_ledger" not in report["summary"]["rows_planned"]


def test_cross_tenant_reference_is_blocked(tmp_path):
    src = _source(tmp_path)
    conn = sqlite3.connect(str(src))
    try:
        conn.execute(
            "INSERT INTO orders VALUES"
            " ('outro-tenant', 50, 'ORD0050', '000001', 10.0, 0.0, 0.0, 10.0,"
            " 'PIX', 'PENDING', 'Rua X', NULL, 'NEW', 'MANUAL', NULL,"
            " '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    rc = _run(src, tmp_path / "t.db", tmp_path / "dry.json")
    assert rc == c.EXIT_PARTIAL
    report = c.loads_json(tmp_path / "dry.json")
    assert "cross_tenant_reference" in _issue_rules(report)
    assert report["summary"]["rows_planned"]["orders"] == 3


def test_existing_target_without_marker_is_blocked(tmp_path):
    src = _source(tmp_path)
    target = tmp_path / "target.db"
    conn = sqlite3.connect(str(target))
    try:
        conn.execute("CREATE TABLE x (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    rc = _run(src, target, tmp_path / "dry.json", "--execute")
    assert rc == c.EXIT_SAFETY
    assert c.loads_json(tmp_path / "dry.json")["status"] == "blocked"
