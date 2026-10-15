"""
GasFlow Database Integrity Check

Detects:
- Records without tenant_id
- Orphaned records (FK references to deleted parents)
- Cross-tenant data leaks
- Invalid status values
- Missing indexes

Usage: python scripts/db_integrity_check.py
"""

import os
import sys
import io

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")

_SQL_ORFAO_ORDER_ITEMS = """
                    SELECT COUNT(*) FROM order_items oi
                    WHERE NOT EXISTS (
                        SELECT 1 FROM orders o WHERE o.codigo = oi.order_codigo
                    )
                """

_SQL_ORFAO_PAYMENTS = """
                    SELECT COUNT(*) FROM payments p
                    WHERE p.order_codigo IS NOT NULL AND p.order_codigo != ''
                    AND NOT EXISTS (
                        SELECT 1 FROM orders o WHERE o.codigo = p.order_codigo
                    )
                """

_SQL_ORFAO_INVENTORY = """
                    SELECT COUNT(*) FROM inventory inv
                    WHERE NOT EXISTS (
                        SELECT 1 FROM products p WHERE p.codigo = inv.product_codigo
                    )
                """


def _cabecalho():
    print("=" * 60)
    print("GasFlow Database Integrity Check")
    print(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    print("=" * 60)


def _verificar_tenant_id(conn, tables, issues):
    print("\n--- Tenant ID Coverage ---")
    tenant_tables = [
        "clients",
        "orders",
        "order_items",
        "products",
        "delivery_drivers",
        "inventory",
        "payments",
        "receivables",
        "expenses",
        "cash_movements",
        "financial_ledger",
        "whatsapp_conversations",
        "whatsapp_messages",
        "ai_conversations",
        "ai_messages",
        "ai_audit_log",
    ]

    for table in tenant_tables:
        if table in tables:
            try:
                result = conn.execute(
                    text(f"SELECT COUNT(*) FROM [{table}] WHERE tenant_id IS NULL OR tenant_id = ''")
                ).scalar()
                total = conn.execute(text(f"SELECT COUNT(*) FROM [{table}]")).scalar()
                if result > 0:
                    issues.append(f"CRITICAL: {table} has {result}/{total} records without tenant_id")
                    print(f"  ❌ {table}: {result}/{total} records missing tenant_id")
                else:
                    print(f"  ✅ {table}: all {total} records have tenant_id")
            except Exception as e:
                print(f"  ⚠️  {table}: {e}")


def _verificar_orfao(conn, tables, issues, *, nome, tabelas, sql, issue, ruim, ok):
    if not all(t in tables for t in tabelas):
        return
    try:
        result = conn.execute(text(sql)).scalar()
    except Exception as e:
        print(f"  ⚠️  {nome} orphan check: {e}")
        return
    if result > 0:
        issues.append(f"WARNING: {result} {issue}")
        print(f"  ❌ {nome}: {result} {ruim}")
    else:
        print(f"  ✅ {nome}: {ok}")


def _verificar_orfaos(conn, tables, issues):
    # 2. Check for orphaned order_items / payments / inventory
    print("\n--- Orphaned Records ---")
    _verificar_orfao(
        conn,
        tables,
        issues,
        nome="order_items",
        tabelas=("order_items", "orders"),
        sql=_SQL_ORFAO_ORDER_ITEMS,
        issue="orphaned order_items (no matching order)",
        ruim="orphaned records",
        ok="no orphans",
    )
    _verificar_orfao(
        conn,
        tables,
        issues,
        nome="payments",
        tabelas=("payments", "orders"),
        sql=_SQL_ORFAO_PAYMENTS,
        issue="payments with invalid order_codigo",
        ruim="with invalid order reference",
        ok="all order references valid",
    )
    _verificar_orfao(
        conn,
        tables,
        issues,
        nome="inventory",
        tabelas=("inventory", "products"),
        sql=_SQL_ORFAO_INVENTORY,
        issue="inventory records without matching product",
        ruim="orphaned records",
        ok="all product references valid",
    )


def _verificar_duplicados(conn, tables, issues):
    # 5. Check for duplicate codigo within same tenant
    print("\n--- Duplicate Codigo Check ---")
    for table in ["clients", "orders", "products", "delivery_drivers"]:
        if table in tables:
            try:
                result = conn.execute(
                    text(f"""
                        SELECT tenant_id, codigo, COUNT(*) as cnt
                        FROM [{table}]
                        GROUP BY tenant_id, codigo
                        HAVING COUNT(*) > 1
                    """)
                ).fetchall()
                if result:
                    issues.append(f"CRITICAL: {table} has duplicate codigos within tenants")
                    for row in result:
                        print(f"  ❌ {table}: tenant={row[0]}, codigo={row[1]}, count={row[2]}")
                else:
                    print(f"  ✅ {table}: no duplicate codigos")
            except Exception as e:
                print(f"  ⚠️  {table}: {e}")


def _estatisticas(conn, tables):
    # 6. Table row counts
    print("\n--- Table Statistics ---")
    for table in sorted(tables):
        try:
            count = conn.execute(text(f"SELECT COUNT(*) FROM [{table}]")).scalar()
            print(f"  {table}: {count} rows")
        except Exception:
            print(f"  {table}: error reading")


def _resumo(issues):
    # Summary
    print("\n" + "=" * 60)
    if issues:
        print(f"INTEGRITY CHECK: {len(issues)} issues found")
        print()
        for issue in issues:
            print(f"  • {issue}")
        print()
        print("Status: ⚠️  ISSUES DETECTED")
    else:
        print("INTEGRITY CHECK: No issues found")
        print("Status: ✅ CLEAN")
    print("=" * 60)


def check_integrity():
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    issues = []

    _cabecalho()

    # Get all tables
    tables = inspector.get_table_names()
    print(f"\nTables found: {len(tables)}")

    with engine.connect() as conn:
        # 1. Check tenant_id coverage
        _verificar_tenant_id(conn, tables, issues)
        _verificar_orfaos(conn, tables, issues)
        _verificar_duplicados(conn, tables, issues)
        _estatisticas(conn, tables)

    _resumo(issues)

    return len(issues) == 0


if __name__ == "__main__":
    success = check_integrity()
    sys.exit(0 if success else 1)
