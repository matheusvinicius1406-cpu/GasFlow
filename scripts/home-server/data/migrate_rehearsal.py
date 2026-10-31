#!/usr/bin/env python3
"""Ensaio de migração SQLite legado -> schema atual (OPS-01D, Etapa 4).

Dry-run POR PADRÃO: sem ``--execute`` nada é gravado — só planeja, valida e
reporta. Com ``--execute`` grava SOMENTE em ``--target`` (arquivo novo),
após as guardas de segurança:

- alvo precisa ser caminho explícito e inexistente (ou conter o marcador
  ``_ops01d_run`` deste ferramenta com a MESMA origem, o que ativa o modo
  reconciliação idempotente);
- alvo nunca pode coincidir com a origem (nem pelo caminho nem pelo nome);
- alvo ``postgresql://`` é RECUSADO nesta fase (dependência registrada para
  o integrador — ver docs/data-migration/README.md);
- falha no meio remove SOMENTE o arquivo de alvo criado nesta execução.

Validações (no dry-run e no execute): cast de tipos, NOT NULL, PK/unicidades,
tenant nulo (política ``block`` por padrão), chaves de negócio
(``mapping.LOGICAL_FKS``), FKs declaradas no modelo, ordenação de dependência
e — pós-carga — contagens, somas financeiras e ``PRAGMA foreign_key_check``.
Reexecução sobre alvo com marcador válido = reconciliação somente-leitura
(idempotente; nunca reescreve). Relatório nunca sobrescreve arquivo existente.

Códigos: 0 ok | 1 falha | 2 segurança | 3 migração parcial (bloqueios).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402
import mapping as m  # noqa: E402
from sqlalchemy import create_engine, event, text  # noqa: E402

REPORT_ISSUE_CAP = 500
MARKER_TABLE = "_ops01d_run"
MARKER_DDL = (
    f"CREATE TABLE IF NOT EXISTS {MARKER_TABLE} ("
    "id INTEGER PRIMARY KEY, tool_version TEXT NOT NULL, "
    "source_fingerprint TEXT NOT NULL, source_kind TEXT NOT NULL, "
    "started_at TEXT NOT NULL, finished_at TEXT NOT NULL, "
    "counters TEXT NOT NULL)"
)
FINANCIAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "orders": ("subtotal", "delivery_fee", "discount", "total"),
    "order_items": ("unit_price", "subtotal"),
    "payments": ("amount",),
    "receivables": ("original_amount", "paid_amount"),
    "financial_ledger": ("amount",),
}
_CENT = Decimal("0.01")


@dataclass
class TablePlan:
    table: str
    action: str  # migrate | skip | block
    reason: str = ""
    insert_columns: tuple[str, ...] = ()
    missing_target: tuple[str, ...] = ()
    unknown_source: tuple[str, ...] = ()


@dataclass
class RowIssue:
    table: str
    pk: str
    column: str
    rule: str


@dataclass
class Validation:
    plans: list[TablePlan] = field(default_factory=list)
    target_only: list[str] = field(default_factory=list)
    accepted: dict[str, list[dict]] = field(default_factory=dict)
    issues: list[RowIssue] = field(default_factory=list)
    tenants: dict[str, int] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="SQLite legado de origem")
    parser.add_argument("--target", required=True, help="arquivo de destino (novo)")
    parser.add_argument("--execute", action="store_true", help="grava no alvo")
    parser.add_argument("--report", help="gravar o relatório JSON em arquivo")
    parser.add_argument(
        "--null-tenant",
        choices=m.NULL_TENANT_POLICIES,
        default="block",
        help="política para tenant_id nulo (padrão: block = bloqueia a linha)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="qualquer bloqueio impede a gravação (fail-closed)",
    )
    parser.add_argument(
        "--allow-unknown-source",
        action="store_true",
        help="prossegue mesmo sem reconhecer a assinatura do banco",
    )
    return parser.parse_args(argv)


def _import_models():
    """Importa o metadata do schema atual (requer backend no sys.path)."""
    repo_root = Path(__file__).resolve().parents[3]
    backend = str(repo_root / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.infrastructure.database.base import Base  # noqa: PLC0415
    import app.infrastructure.database.init_db  # noqa: F401, PLC0415

    return Base.metadata


def detect_source_kind(conn: sqlite3.Connection) -> str:
    names = set(c.table_names(conn))
    if names & m.WHATSAPP_SERVICE_MARKERS:
        return "whatsapp-service"
    if m.BACKEND_REQUIRED_TABLES.issubset(names):
        return "backend"
    return "unknown"


def source_fingerprint(path: Path) -> str:
    return f"{path.stat().st_size}:{c.sha256_file(path)}"


def load_source_rows(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    for name in c.table_names(conn):
        cursor = conn.execute(f'SELECT * FROM "{name}"')
        cols = [d[0] for d in cursor.description or []]
        rows[name] = [dict(zip(cols, rec)) for rec in cursor.fetchall()]
    return rows


def _fillable_missing(column) -> tuple[str, Any] | None:
    """Como preencher coluna do alvo ausente na origem.

    Retorno: None (tenant — política do chamador) | ('value', v) |
    ('omit', None) (pk autogerada: coluna fica de fora do INSERT) |
    ('block', motivo).
    """
    if column.name == "tenant_id":
        return None  # tratado pela política de tenant (chamador)
    if column.primary_key and column.autoincrement is not False:
        return ("omit", None)  # pk ausente na origem: gera no destino
    default = column.default
    if default is not None and default.is_scalar:
        return ("value", default.arg)
    if default is not None and callable(default.arg):
        try:
            return ("value", default.arg())
        except Exception:  # noqa: BLE001 — default application-defined
            return ("block", "default_indisponivel")
    if column.nullable:
        return ("value", None)
    if column.server_default is not None:
        return ("omit", None)  # default do servidor aplica no INSERT
    return ("block", f"coluna_obrigatoria_ausente:{column.name}")


def build_plan(source_schema: dict, metadata) -> tuple[list[TablePlan], list[str]]:
    plans: list[TablePlan] = []
    target_tables = set(metadata.tables)
    source_tables = set(source_schema)
    for name in sorted(source_tables):
        plans.append(
            _plan_for_table(name, source_schema[name], metadata, target_tables)
        )
    target_only = sorted(target_tables - source_tables - set(m.SKIP_TABLES))
    return plans, target_only


def _plan_for_table(name: str, source_cols: dict, metadata, target_tables) -> TablePlan:
    if name in m.SKIP_TABLES:
        return TablePlan(name, "skip", "metadado/derivada")
    if name in m.BLOCKED_TABLES:
        return TablePlan(name, "block", m.BLOCKED_TABLES[name])
    if name not in target_tables:
        return TablePlan(name, "block", "tabela_legada_sem_equivalente")
    target = metadata.tables[name]
    unknown = tuple(sorted(set(source_cols) - set(target.columns.keys())))
    if unknown:
        return TablePlan(name, "block", "coluna_sem_equivalente", (), (), unknown)
    insert_cols = tuple(col.name for col in target.columns if col.name in source_cols)
    missing = tuple(col.name for col in target.columns if col.name not in source_cols)
    for col_name in missing:
        resolved = _fillable_missing(target.columns[col_name])
        if resolved is None:  # tenant_id: depende da política, validado por linha
            continue
        if resolved[0] == "block":
            return TablePlan(
                name, "block", f"coluna_obrigatoria_ausente:{col_name}", (), missing
            )
    return _apply_pk_rules(
        TablePlan(name, "migrate", "", insert_cols, missing), target, source_cols
    )


def _apply_pk_rules(plan: TablePlan, target, source_cols: dict) -> TablePlan:
    """PK ausente na origem: bloqueia, ou (pk autogerada) tira do INSERT."""
    pk_cols = [col.name for col in target.primary_key.columns]
    if not pk_cols or all(pk in source_cols for pk in pk_cols):
        return plan
    if len(pk_cols) > 1:
        return TablePlan(plan.table, "block", "pk_composta_ausente_na_origem")
    if not target.primary_key.columns[0].autoincrement:
        return TablePlan(plan.table, "block", "pk_ausente_na_origem")
    plan.insert_cols = tuple(col for col in plan.insert_cols if col not in pk_cols)
    return plan


def _python_type(column) -> type | None:
    try:
        return column.type.python_type
    except (NotImplementedError, AttributeError):
        return None


def cast_value(value: Any, column) -> tuple[Any, str | None]:
    if value is None:
        return None, None
    py = _python_type(column)
    try:
        return _cast_by_type(value, py)
    except (ValueError, TypeError, InvalidOperation):
        return None, f"cast_{getattr(py, '__name__', 'any')}_failed"


def _cast_by_type(value: Any, py: type | None) -> tuple[Any, str | None]:
    if py is None:
        return value, None  # tipo desconhecido: passa adiante (SQLite é dinâmico)
    if py is str:
        return (value if isinstance(value, str) else str(value)), None
    if py is bool:
        return _to_bool(value), None
    if py is int:
        return _to_int(value), None
    if py is float:
        return float(value), None
    if py is Decimal:
        dec = Decimal(str(value))
        if not dec.is_finite():
            raise InvalidOperation
        return dec, None
    if py is datetime:
        return _to_datetime(value), None
    if py in (dict, list):
        return _to_json(value), None
    return value, None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in {"0", "1", "true", "false"}:
        return value.lower() in {"true", "1"}
    raise ValueError(value)


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError(value)


def _to_datetime(value: Any) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).strip())
    )
    if parsed.tzinfo is not None:
        raise ValueError("timezone nao suportado")
    return parsed


def _to_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    raise ValueError(value)


def _pk_repr(values: tuple) -> str:
    return "/".join(str(v) for v in values)


def _resolve_tenant(value: Any, policy: str) -> tuple[Any, str | None]:
    if value is not None:
        return value, None
    if policy == "platform":
        return m.PLATFORM_TENANT_ID, None
    return None, "null_tenant"


def prepare_table(
    plan: TablePlan, source_rows: list[dict], metadata, policy: str
) -> tuple[list[dict], list[RowIssue]]:
    target = metadata.tables[plan.table]
    pk_cols = [col.name for col in target.primary_key.columns]
    accepted: list[dict] = []
    issues: list[RowIssue] = []
    seen_pk: set[tuple] = set()
    for src in source_rows:
        row, issue = _convert_row(plan, src, target, pk_cols, policy)
        if issue is not None:
            issues.append(issue)
            continue
        pk = tuple(row.get(k) for k in pk_cols)
        if any(v is None for v in pk):
            accepted.append(row)  # pk autogera no destino — unicidade é do DB
            continue
        norm = tuple(str(v) for v in pk)
        if norm in seen_pk:
            issues.append(RowIssue(plan.table, _pk_repr(norm), "", "duplicate_pk"))
            continue
        seen_pk.add(norm)
        accepted.append(row)
    return accepted, issues


def _convert_row(
    plan: TablePlan, src: dict, target, pk_cols: list[str], policy: str
) -> tuple[dict | None, RowIssue | None]:
    row: dict[str, Any] = {}
    pk_hint = _pk_repr(tuple(str(src.get(k)) for k in pk_cols if k in src)) or "?"
    for col in target.columns:
        if col.name in plan.insert_columns:
            raw = src.get(col.name)
            if col.name == "tenant_id":
                value, rule = _resolve_tenant(raw, policy)
                if rule:
                    return None, RowIssue(plan.table, pk_hint, col.name, rule)
            else:
                value, rule = cast_value(raw, col)
                if rule:
                    return None, RowIssue(plan.table, pk_hint, col.name, rule)
        else:
            status, payload = _missing_column_value(col, policy)
            if status == "block":
                return None, RowIssue(plan.table, pk_hint, col.name, payload)
            if status == "omit":
                continue  # pk autogerada / default de servidor: fora do INSERT
            value = payload
        if value is None and not col.nullable:
            return None, RowIssue(plan.table, pk_hint, col.name, "not_null_violation")
        row[col.name] = value
    return row, None


def _missing_column_value(col, policy: str) -> tuple[str, Any]:
    """Valor para coluna do alvo ausente na origem: ('value'|'omit'|'block', x)."""
    resolved = _fillable_missing(col)
    if resolved is None:  # tenant_id: depende da política de tenant
        value, rule = _resolve_tenant(None, policy)
        if rule:
            return ("block", rule)
        return ("value", value)
    if resolved[0] == "block":
        return ("block", resolved[1])
    if resolved[0] == "omit":
        return ("omit", None)
    return ("value", resolved[1])


def _unique_groups(target) -> list[tuple[str, ...]]:
    groups: list[tuple[str, ...]] = []
    for col in target.columns:
        if col.unique:
            groups.append((col.name,))
    for constraint in target.constraints:
        if constraint.__class__.__name__ == "UniqueConstraint":
            groups.append(tuple(cc.name for cc in constraint.columns))
    for index in target.indexes:
        if index.unique:
            groups.append(tuple(cc.name for cc in index.columns))
    return groups


def check_uniques(
    plan: TablePlan, accepted: list[dict], metadata
) -> tuple[list[dict], list[RowIssue]]:
    target = metadata.tables[plan.table]
    kept = accepted
    issues: list[RowIssue] = []
    for group in _unique_groups(target):
        kept, group_issues = _filter_unique(plan, kept, group)
        issues.extend(group_issues)
    return kept, issues


def _filter_unique(
    plan: TablePlan, rows: list[dict], group: tuple[str, ...]
) -> tuple[list[dict], list[RowIssue]]:
    seen: set[tuple] = set()
    kept: list[dict] = []
    issues: list[RowIssue] = []
    for row in rows:
        key = tuple(row.get(name) for name in group)
        if any(v is None for v in key):
            kept.append(row)  # NULLs são distintos em SQL
            continue
        norm = tuple(str(v) for v in key)
        if norm in seen:
            issues.append(
                RowIssue(
                    plan.table,
                    _pk_repr((row.get("id"),)),
                    ",".join(group),
                    "unique_violation",
                )
            )
            continue
        seen.add(norm)
        kept.append(row)
    return kept, issues


def all_foreign_keys(plans: list[TablePlan], metadata) -> list[Any]:
    declared = []
    migrating = {p.table for p in plans if p.action == "migrate"}
    for plan in plans:
        if plan.action != "migrate":
            continue
        for fk in metadata.tables[plan.table].foreign_keys:
            declared.append(
                m.LogicalFk(
                    plan.table,
                    fk.parent.name,
                    fk.column.table.name,
                    fk.column.name,
                    nullable=fk.parent.nullable,
                )
            )
    business = [fk for fk in m.LOGICAL_FKS if fk.child_table in migrating]
    return declared + business


def topo_order(fks: list[Any], tables: set[str]) -> list[str]:
    """Ordenação por dependência (pais primeiro); ciclos caem em ordem alfabética."""
    pending = set(tables)
    ordered: list[str] = []
    while pending:
        ready = {
            t
            for t in pending
            if not any(
                fk.child_table == t
                and fk.parent_table in pending
                and fk.parent_table != t
                for fk in fks
            )
        }
        if not ready:
            ordered.extend(sorted(pending))
            break
        ordered.extend(sorted(ready))
        pending -= ready
    return ordered


def check_foreign_keys(validation: Validation, fks: list[Any]) -> None:
    for fk in fks:
        parent_plan = _plan_by_name(validation, fk.parent_table)
        child_plan = _plan_by_name(validation, fk.child_table)
        if child_plan is None or child_plan.action != "migrate":
            continue
        child_rows = validation.accepted.get(fk.child_table, [])
        parent_rows, parent_blocked = _parent_lookup(validation, parent_plan, fk)
        kept: list[dict] = []
        for row in child_rows:
            value = row.get(fk.child_column)
            issue = _fk_issue(row, fk, value, parent_rows, parent_blocked)
            if issue is None:
                kept.append(row)
            else:
                validation.issues.append(issue)
        validation.accepted[fk.child_table] = kept


def _plan_by_name(validation: Validation, name: str) -> TablePlan | None:
    for plan in validation.plans:
        if plan.table == name:
            return plan
    return None


def _parent_lookup(validation: Validation, parent_plan, fk) -> tuple[dict, bool]:
    if parent_plan is None or parent_plan.action != "migrate":
        return {}, True
    lookup: dict[str, dict] = {}
    for row in validation.accepted.get(fk.parent_table, []):
        lookup[str(row.get(fk.parent_column))] = row
    return lookup, False


def _fk_issue(row, fk, value, parent_rows, parent_blocked) -> RowIssue | None:
    pk_hint = _pk_repr((row.get("id"),))
    if value is None:
        return (
            None
            if fk.nullable
            else RowIssue(
                fk.child_table, pk_hint, fk.child_column, "not_null_reference"
            )
        )
    if parent_blocked:
        return RowIssue(
            fk.child_table, pk_hint, fk.child_column, "parent_table_blocked"
        )
    parent = parent_rows.get(str(value))
    if parent is None:
        return RowIssue(fk.child_table, pk_hint, fk.child_column, "orphan_reference")
    child_tenant = row.get("tenant_id")
    parent_tenant = parent.get("tenant_id")
    if (
        child_tenant is not None
        and parent_tenant is not None
        and child_tenant != parent_tenant
    ):
        return RowIssue(
            fk.child_table, pk_hint, fk.child_column, "cross_tenant_reference"
        )
    return None


def promote_immutable_blocks(validation: Validation) -> None:
    """Ledger imutável com qualquer linha inválida -> tabela inteira bloqueada."""
    for plan in validation.plans:
        if plan.action != "migrate" or plan.table not in m.IMMUTABLE_TABLES:
            continue
        if any(issue.table == plan.table for issue in validation.issues):
            plan.action = "block"
            plan.reason = "ledger_imutavel_com_linhas_invalidas"
            validation.accepted[plan.table] = []


def validate_source(
    source_schema: dict, source_rows: dict, metadata, args
) -> Validation:
    validation = Validation()
    validation.plans, validation.target_only = build_plan(source_schema, metadata)
    for plan in validation.plans:
        if plan.action != "migrate":
            continue
        rows = source_rows.get(plan.table, [])
        accepted, issues = prepare_table(plan, rows, metadata, args.null_tenant)
        accepted, unique_issues = check_uniques(plan, accepted, metadata)
        validation.accepted[plan.table] = accepted
        validation.issues.extend(issues)
        validation.issues.extend(unique_issues)
    fks = all_foreign_keys(validation.plans, metadata)
    validation.order = topo_order(
        fks, {p.table for p in validation.plans if p.action == "migrate"}
    )
    check_foreign_keys(validation, fks)
    promote_immutable_blocks(validation)
    validation.tenants = _tenant_distribution(validation)
    return validation


def _tenant_distribution(validation: Validation) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for table, rows in validation.accepted.items():
        if not rows or "tenant_id" not in rows[0]:
            continue
        for row in rows:
            key = str(row.get("tenant_id"))
            distribution[key] = distribution.get(key, 0) + 1
    return distribution


@dataclass
class Prepared:
    source: Path
    target: Path
    kind: str
    validation: Validation
    metadata: Any
    report: dict


def _kind_gate(kind: str, allow_unknown: bool) -> str | None:
    if kind == "whatsapp-service":
        return "banco do serviço WhatsApp: fora do escopo da migração"
    if kind == "unknown" and not allow_unknown:
        return (
            "assinatura da origem não reconhecida "
            "(use --allow-unknown-source se for seguro)"
        )
    return None


def _prepare(args: argparse.Namespace) -> Prepared | int:
    target_str = str(args.target)
    if target_str.startswith(("postgresql://", "postgres://")):
        return c.die(
            c.EXIT_SAFETY,
            "alvo postgresql:// recusado nesta fase "
            "(ver docs/data-migration/README.md)",
        )
    source = Path(args.source).expanduser()
    if not source.exists() or not source.is_file():
        return c.die(c.EXIT_SAFETY, f"origem inexistente ou não é arquivo: {source}")
    source = source.resolve()
    if not c.has_sqlite_magic(source):
        return c.die(c.EXIT_FAIL, f"origem não é SQLite: {source.name}")
    target = Path(args.target).expanduser().resolve()
    try:
        conn, _mode = c.open_readonly(source)
    except c.ReadOnlyOpenError as exc:
        return c.die(c.EXIT_SAFETY, str(exc))
    try:
        kind = detect_source_kind(conn)
        gate = _kind_gate(kind, args.allow_unknown_source)
        if gate:
            return c.die(c.EXIT_SAFETY, gate)
        source_schema = c.schema_snapshot(conn)
        source_rows = load_source_rows(conn)
    finally:
        conn.close()
    try:
        metadata = _import_models()
    except Exception as exc:  # noqa: BLE001 — diagnóstico sem traceback de ambiente
        return c.die(c.EXIT_FAIL, f"schema atual indisponível: {type(exc).__name__}")
    validation = validate_source(source_schema, source_rows, metadata, args)
    report = _base_report(args, source, target, kind, validation, metadata)
    return Prepared(source, target, kind, validation, metadata, report)


def _base_report(
    args: argparse.Namespace,
    source: Path,
    target: Path,
    kind: str,
    validation: Validation,
    metadata: Any,
) -> dict:
    return {
        "tool": c.TOOL,
        "tool_version": c.TOOL_VERSION,
        "command": "rehearsal",
        "generated_at": c.utc_now(),
        "mode": "execute" if args.execute else "dry-run",
        "source": {
            "path": str(source),
            "kind": kind,
            "size_bytes": source.stat().st_size,
            "fingerprint": source_fingerprint(source),
            "target_schema_tables": len(metadata.tables),
        },
        "target": {"path": str(target), "exists": target.exists()},
        "policy": {
            "null_tenant": args.null_tenant,
            "strict": bool(args.strict),
            "allow_unknown_source": bool(args.allow_unknown_source),
        },
        "summary": _summary(validation),
        "plans": _plan_dicts(validation.plans),
        "issues": _issue_dicts(validation.issues),
        "issues_total": len(validation.issues),
        "tenants": validation.tenants,
        "order": validation.order,
        "target_only": validation.target_only,
        "status": "pending",
    }


def _summary(validation: Validation) -> dict:
    tables = {"migrate": 0, "skip": 0, "block": 0}
    blocked: list[str] = []
    for plan in validation.plans:
        tables[plan.action] += 1
        if plan.action == "block":
            blocked.append(plan.table)
    rows_planned = {
        name: len(rows) for name, rows in validation.accepted.items() if rows
    }
    return {
        "tables": tables,
        "rows_planned": rows_planned,
        "rows_total": sum(rows_planned.values()),
        "issues": len(validation.issues),
        "blocked_tables": blocked,
        "has_blocks": _has_blocks(validation),
    }


def _plan_dicts(plans: list[TablePlan]) -> list[dict]:
    return [
        {
            "table": plan.table,
            "action": plan.action,
            "reason": plan.reason,
            "missing_target": list(plan.missing_target),
            "unknown_source": list(plan.unknown_source),
        }
        for plan in plans
    ]


def _issue_dicts(issues: list[RowIssue]) -> list[dict]:
    return [
        {
            "table": issue.table,
            "pk": issue.pk,
            "column": issue.column,
            "rule": issue.rule,
        }
        for issue in issues[:REPORT_ISSUE_CAP]
    ]


def _has_blocks(validation: Validation) -> bool:
    if any(plan.action == "block" for plan in validation.plans):
        return True
    return bool(validation.issues)


def plan_target_mode(
    source: Path, target: Path, fingerprint: str
) -> tuple[str, str | None, dict | None]:
    """('fresh'|'reconcile'|'blocked', motivo|None, marcador|None) — nunca grava."""
    if target.name == source.name:
        return ("blocked", "nome do alvo coincide com o nome da origem", None)
    if not target.exists():
        return ("fresh", None, None)
    info = _marker_info(target)
    if isinstance(info, str):
        return ("blocked", info, None)
    if info["fingerprint"] != fingerprint:
        return ("blocked", "alvo criado para OUTRA origem — reexecução bloqueada", None)
    return ("reconcile", None, info)


def _marker_info(target: Path) -> dict | str:
    """Lê o marcador do alvo (somente-leitura). Retorna dict ou motivo de bloqueio."""
    try:
        conn, _mode = c.open_readonly(target)
    except Exception as exc:  # noqa: BLE001 — qualquer falha de leitura bloqueia
        return f"alvo ilegível: {type(exc).__name__}"
    try:
        if MARKER_TABLE not in set(c.table_names(conn)):
            return "alvo existente sem marcador _ops01d_run (sobrescrita proibida)"
        row = conn.execute(
            f'SELECT source_fingerprint, counters FROM "{MARKER_TABLE}"'
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return "marcador _ops01d_run vazio — execução anterior incompleta"
    try:
        counters = json.loads(row[1])
    except ValueError:
        return "marcador _ops01d_run corrompido"
    return {"fingerprint": row[0], "counters": counters}


def _rows(conn: Any, sql: str) -> list[tuple]:
    """Consulta simples sobre conexão sqlite3 (leitura) ou SQLAlchemy (txn)."""
    if isinstance(conn, sqlite3.Connection):
        return conn.execute(sql).fetchall()
    return conn.execute(text(sql)).fetchall()


def _expected_counts(validation: Validation, metadata: Any) -> dict[str, int]:
    """Contagens esperadas no alvo por tabela do schema atual (só migração)."""
    counts: dict[str, int] = {}
    for name in sorted(set(metadata.tables) - {MARKER_TABLE}):
        counts[name] = len(validation.accepted.get(name) or [])
    return counts


def _count_mismatches(conn: Any, validation: Validation, metadata: Any) -> list[dict]:
    mismatches = []
    for name, expected in _expected_counts(validation, metadata).items():
        actual = _rows(conn, f'SELECT COUNT(*) FROM "{name}"')[0][0]
        if actual != expected:
            mismatches.append({"table": name, "expected": expected, "actual": actual})
    return mismatches


def _quantized(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _expected_financial_value(row: dict, col: str, target: Any) -> Decimal | None:
    """Valor esperado de coluna financeira (espelha o DEFAULT aplicado no INSERT)."""
    if col in row:
        value = row[col]
    else:
        default = target.columns[col].default
        value = default.arg if default is not None and default.is_scalar else None
    if value is None:
        return None
    return Decimal(str(value))


def _financial_diffs(conn: Any, validation: Validation, metadata: Any) -> list[dict]:
    """Soma por coluna financeira no destino vs linhas aceitas (NULL = ignora)."""
    diffs = []
    for table, cols in FINANCIAL_COLUMNS.items():
        rows = validation.accepted.get(table) or []
        if not rows:
            continue
        target = metadata.tables[table]
        exprs = ", ".join(f'SUM("{col}")' for col in cols)
        actual_row = _rows(conn, f'SELECT {exprs} FROM "{table}"')[0]
        for col, raw in zip(cols, actual_row):
            expected = _quantized(
                sum(
                    (
                        Decimal(str(v))
                        for r in rows
                        if (v := _expected_financial_value(r, col, target)) is not None
                    ),
                    Decimal("0.00"),
                )
            )
            if _quantized(raw) != expected:
                diffs.append(
                    {
                        "table": table,
                        "column": col,
                        "expected": str(expected),
                        "actual": str(_quantized(raw)),
                    }
                )
    return diffs


def _target_engine(target: Path):
    engine = create_engine(f"sqlite:///{target.as_posix()}")

    @event.listens_for(engine, "connect")
    def _enable_fks(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def _load_rows(conn: Any, validation: Validation, metadata: Any) -> None:
    for table_name in validation.order:
        rows = validation.accepted.get(table_name) or []
        if not rows:
            continue
        conn.execute(metadata.tables[table_name].insert(), rows)


def _write_marker(
    conn: Any,
    fingerprint: str,
    kind: str,
    started_at: str,
    counts: dict[str, int],
) -> None:
    conn.execute(text(MARKER_DDL))
    conn.execute(
        text(
            f"INSERT INTO {MARKER_TABLE} (tool_version, source_fingerprint,"
            " source_kind, started_at, finished_at, counters) VALUES"
            " (:tool_version, :source_fingerprint, :source_kind,"
            " :started_at, :finished_at, :counters)"
        ),
        {
            "tool_version": c.TOOL_VERSION,
            "source_fingerprint": fingerprint,
            "source_kind": kind,
            "started_at": started_at,
            "finished_at": c.utc_now(),
            "counters": json.dumps(counts, sort_keys=True),
        },
    )


def _remove_target(target: Path) -> None:
    """Remove SOMENTE o arquivo de alvo criado nesta execução (nunca a origem)."""
    for suffix in ("", "-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)


def _safe_error(exc: BaseException) -> str:
    message = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {message[:300]}"


def _finish(report: dict, args: argparse.Namespace) -> None:
    if args.report:
        c.write_json(args.report, report)
    c.emit(report)


def _fail(
    report: dict,
    args: argparse.Namespace,
    code: int,
    message: str,
    *,
    status: str = "failed",
) -> int:
    report["status"] = status
    report["error"] = message
    _finish(report, args)
    return c.die(code, message)


def _dry_run(prepared: Prepared, args: argparse.Namespace) -> int:
    blocks = _has_blocks(prepared.validation)
    prepared.report["status"] = "dry-run-partial" if blocks else "dry-run"
    _finish(prepared.report, args)
    c.note("dry-run: nenhum arquivo gravado")
    return c.EXIT_PARTIAL if blocks else c.EXIT_OK


def _strict_blocked(prepared: Prepared, args: argparse.Namespace) -> int:
    prepared.report["status"] = "strict-blocked"
    _finish(prepared.report, args)
    c.note("--strict: bloqueios impedem a gravação (fail-closed)")
    return c.EXIT_PARTIAL


def _reconcile_path(prepared: Prepared, args: argparse.Namespace, marker: dict) -> int:
    report = prepared.report
    try:
        conn, _mode = c.open_readonly(prepared.target)
    except Exception as exc:  # noqa: BLE001 — falha de leitura = bloqueio
        return _fail(
            report,
            args,
            c.EXIT_SAFETY,
            f"alvo ilegível na reconciliação: {type(exc).__name__}",
            status="blocked",
        )
    try:
        mismatches = _count_mismatches(conn, prepared.validation, prepared.metadata)
        diffs = _financial_diffs(conn, prepared.validation, prepared.metadata)
    finally:
        conn.close()
    drifted = marker.get("counters") != _expected_counts(
        prepared.validation, prepared.metadata
    )
    if mismatches or diffs or drifted:
        report["reconcile"] = {
            "count_mismatches": mismatches,
            "financial_diffs": diffs,
            "marker_drift": drifted,
        }
        return _fail(
            report,
            args,
            c.EXIT_SAFETY,
            "reconciliação reprovada — o alvo diverge do ensaio original",
            status="reconcile-mismatch",
        )
    report["reconcile"] = {
        "status": "ok",
        "count_mismatches": [],
        "financial_diffs": [],
        "marker_drift": False,
    }
    blocks = _has_blocks(prepared.validation)
    report["status"] = "reconciled-partial" if blocks else "reconciled"
    _finish(report, args)
    c.note("reconciliação confirmada: alvo consistente com o ensaio original")
    return c.EXIT_PARTIAL if blocks else c.EXIT_OK


def _execute_migration(prepared: Prepared, args: argparse.Namespace) -> int:
    report = prepared.report
    target = prepared.target
    report["target"]["created"] = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(
            report,
            args,
            c.EXIT_FAIL,
            f"diretório do alvo indisponível: {_safe_error(exc)}",
        )
    engine = _target_engine(target)
    try:
        prepared.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            _load_rows(conn, prepared.validation, prepared.metadata)
            violations = _rows(conn, "PRAGMA foreign_key_check")
            if violations:
                raise RuntimeError(
                    f"foreign_key_check: {len(violations)} violação(ões)"
                )
            mismatches = _count_mismatches(conn, prepared.validation, prepared.metadata)
            if mismatches:
                raise RuntimeError(f"contagens divergentes: {mismatches[:3]}")
            diffs = _financial_diffs(conn, prepared.validation, prepared.metadata)
            if diffs:
                raise RuntimeError(f"financeiro divergente: {diffs[:3]}")
            _write_marker(
                conn,
                report["source"]["fingerprint"],
                prepared.kind,
                c.utc_now(),
                _expected_counts(prepared.validation, prepared.metadata),
            )
    except Exception as exc:  # noqa: BLE001 — falha -> rollback + remoção do alvo
        engine.dispose()
        _remove_target(target)
        return _fail(
            report,
            args,
            c.EXIT_FAIL,
            f"ensaio falhou (alvo removido): {_safe_error(exc)}",
        )
    engine.dispose()
    report["target"]["created"] = True
    blocks = _has_blocks(prepared.validation)
    report["status"] = "migrated-partial" if blocks else "migrated"
    report["verification"] = {
        "foreign_key_check": "ok",
        "count_mismatches": 0,
        "financial_diffs": 0,
        "marker": "escrito",
    }
    _finish(report, args)
    c.note(f"ensaio concluído: {target}")
    return c.EXIT_PARTIAL if blocks else c.EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    refusal = c.guard_report_path(args.report)
    if refusal:
        return c.die(c.EXIT_SAFETY, refusal)
    prepared = _prepare(args)
    if isinstance(prepared, int):
        return prepared
    mode, block_reason, marker = plan_target_mode(
        prepared.source, prepared.target, prepared.report["source"]["fingerprint"]
    )
    if mode == "blocked":
        return _fail(
            prepared.report,
            args,
            c.EXIT_SAFETY,
            block_reason or "alvo bloqueado",
            status="blocked",
        )
    prepared.report["target"]["plan"] = mode
    if mode == "reconcile" and marker is not None:
        return _reconcile_path(prepared, args, marker)
    if args.execute and args.strict and _has_blocks(prepared.validation):
        return _strict_blocked(prepared, args)
    if not args.execute:
        return _dry_run(prepared, args)
    return _execute_migration(prepared, args)


if __name__ == "__main__":
    raise SystemExit(main())
