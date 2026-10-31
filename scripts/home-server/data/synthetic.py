"""Fixtures sintéticas de schema legado para o ensaio (OPS-01D, Etapa 4).

Gera SQLite LEGADO fictício em caminho temporário: colunas ausentes nas
versões novas (CRM/geocode), casos-limite controlados (tenant nulo,
duplicata, órfão, cast inválido) e — opcionalmente — tabela e coluna
legadas sem equivalente, para exercitar o bloqueio. Nenhum dado real,
nenhum PII: todos os valores são inventados e determinísticos.

Contagens esperadas do conjunto padrão (``EXPECTED_DEFAULT_COUNTS``) são o
contrato usado pelos testes ``test_ops01d_*``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# DDL legado = subconjunto das colunas atuais (como no banco 07/09 do app,
# ver backend/tests/test_schema_migration.py) + chaves NOT NULL do alvo.
DDL = {
    "clients": """
        CREATE TABLE clients (
        tenant_id TEXT, id INTEGER PRIMARY KEY, codigo TEXT,
        nome TEXT NOT NULL, telefone TEXT NOT NULL, telefone_secundario TEXT,
        rua TEXT NOT NULL, numero TEXT NOT NULL, complemento TEXT,
        referencia TEXT, bairro TEXT NOT NULL, observacoes TEXT,
        ativo BOOLEAN, tipo TEXT, email TEXT,
        updated_at TIMESTAMP, created_at TIMESTAMP)""",
    "orders": """
        CREATE TABLE orders (
        tenant_id TEXT, id INTEGER PRIMARY KEY, codigo TEXT,
        client_codigo TEXT, subtotal NUMERIC NOT NULL,
        delivery_fee NUMERIC NOT NULL, discount NUMERIC NOT NULL,
        total NUMERIC NOT NULL, payment_method TEXT,
        payment_status TEXT NOT NULL, address_snapshot TEXT NOT NULL,
        delivery_driver_codigo TEXT, status TEXT NOT NULL, source TEXT NOT NULL,
        notes TEXT, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP)""",
    "order_items": """
        CREATE TABLE order_items (
        tenant_id TEXT, id INTEGER PRIMARY KEY, order_codigo TEXT NOT NULL,
        product_codigo TEXT NOT NULL, product_nome TEXT NOT NULL,
        quantity INTEGER NOT NULL, unit_price NUMERIC NOT NULL,
        subtotal NUMERIC NOT NULL, created_at TIMESTAMP)""",
    "products": """
        CREATE TABLE products (
        tenant_id TEXT, id INTEGER PRIMARY KEY, codigo TEXT,
        nome TEXT NOT NULL, tipo TEXT NOT NULL, preco REAL NOT NULL,
        preco_cartao_1x REAL, preco_cartao_2x REAL, estoque INTEGER,
        ativo BOOLEAN, updated_at TIMESTAMP, created_at TIMESTAMP)""",
    "delivery_drivers": """
        CREATE TABLE delivery_drivers (
        tenant_id TEXT, id INTEGER PRIMARY KEY, codigo TEXT,
        nome TEXT NOT NULL, telefone TEXT NOT NULL, placa TEXT,
        ativo BOOLEAN, document TEXT, username TEXT, password_hash TEXT,
        status TEXT, vehicle_id TEXT, tracking_epoch INTEGER NOT NULL,
        created_at TIMESTAMP, updated_at TIMESTAMP)""",
    "payments": """
        CREATE TABLE payments (
        tenant_id TEXT, id INTEGER PRIMARY KEY, order_codigo TEXT NOT NULL,
        amount NUMERIC NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL,
        paid_at TIMESTAMP, reference TEXT, idempotency_key TEXT UNIQUE,
        notes TEXT, created_at TIMESTAMP NOT NULL)""",
    "receivables": """
        CREATE TABLE receivables (
        tenant_id TEXT, id INTEGER PRIMARY KEY,
        customer_codigo TEXT NOT NULL, order_codigo TEXT NOT NULL,
        original_amount NUMERIC NOT NULL, paid_amount NUMERIC NOT NULL,
        due_date TIMESTAMP, status TEXT NOT NULL, created_at TIMESTAMP NOT NULL,
        settled_at TIMESTAMP)""",
    "financial_ledger": """
        CREATE TABLE financial_ledger (
        tenant_id TEXT, id INTEGER PRIMARY KEY, event_type TEXT NOT NULL,
        amount NUMERIC NOT NULL, reference_type TEXT, reference_id TEXT,
        description TEXT NOT NULL, created_at TIMESTAMP NOT NULL)""",
    "system_settings": """
        CREATE TABLE system_settings (
        id TEXT PRIMARY KEY, category TEXT NOT NULL, value TEXT NOT NULL,
        description TEXT, is_editable BOOLEAN NOT NULL, updated_by TEXT,
        updated_at TIMESTAMP NOT NULL)""",
    "old_phones": """
        CREATE TABLE old_phones (
        id INTEGER PRIMARY KEY, telefone TEXT, nome TEXT)""",
}

# Contrato de contagem do conjunto padrão (linhas VÁLIDAS esperadas por
# tabela; 7 linhas bloqueadas + 1 tabela bloqueada são esperadas também).
EXPECTED_DEFAULT_COUNTS = {
    "clients": 5,
    "orders": 3,
    "order_items": 3,
    "products": 3,
    "delivery_drivers": 1,
    "payments": 2,
    "receivables": 1,
    "financial_ledger": 4,
    "system_settings": 2,
}

STAMP = "2026-01-01T00:00:00"


def _client_rows() -> list[tuple]:
    rows = []
    for i in range(1, 6):  # 5 válidos (tenant default)
        rows.append(
            (
                "default",
                i,
                f"{i:06d}",
                f"Cliente Sintetico {i}",
                f"1198888{i:04d}",
                None,
                f"Rua Sintetica {i}",
                str(i),
                None,
                None,
                "Centro",
                None,
                1,
                "FISICO",
                None,
                STAMP,
                STAMP,
            )
        )
    # 6: tenant NULO -> bloqueada com politica padrao (block)
    rows.append(
        (
            None,
            6,
            "000006",
            "Cliente Sem Tenant",
            "11988880006",
            None,
            "Rua Sintetica 6",
            "6",
            None,
            None,
            "Centro",
            None,
            1,
            "FISICO",
            None,
            STAMP,
            STAMP,
        )
    )
    # 7: telefone duplicado do cliente 1 (mesmo tenant) -> bloqueada
    rows.append(
        (
            "default",
            7,
            "000007",
            "Cliente Duplicado",
            "11988880001",
            None,
            "Rua Sintetica 7",
            "7",
            None,
            None,
            "Centro",
            None,
            1,
            "FISICO",
            None,
            STAMP,
            STAMP,
        )
    )
    return rows


def _order_rows() -> list[tuple]:
    def order(oid: int, codigo: str, client: str) -> tuple:
        return (
            "default",
            oid,
            codigo,
            client,
            "35.90",
            "0.00",
            "0.00",
            "35.90",
            "PIX",
            "PAID",
            f"Rua Sintetica, {oid} - Centro",
            None,
            "DELIVERED",
            "MANUAL",
            None,
            STAMP,
            STAMP,
        )

    return [
        order(1, "ORD0001", "000001"),
        order(2, "ORD0002", "000002"),
        order(3, "ORD0003", "000003"),
        order(4, "ORD0004", "999999"),  # cliente inexistente -> bloqueado
    ]


def _other_rows() -> dict[str, list[tuple]]:
    return {
        "order_items": [
            ("default", 1, "ORD0001", "GAS01", "Gas 13kg", 1, "35.90", "35.90", STAMP),
            ("default", 2, "ORD0001", "GAS02", "Gas 22kg", 2, "45.00", "90.00", STAMP),
            # quantity invalido -> cast falha -> linha bloqueada
            (
                "default",
                3,
                "ORD0002",
                "GAS01",
                "Gas 13kg",
                "abc",
                "35.90",
                "35.90",
                STAMP,
            ),
            # pedido inexistente -> FK de negocio -> linha bloqueada
            ("default", 4, "ORD8888", "GAS01", "Gas 13kg", 1, "35.90", "35.90", STAMP),
            (
                "default",
                5,
                "ORD0003",
                "GAS03",
                "Gas Cozinha",
                1,
                "55.00",
                "55.00",
                STAMP,
            ),
        ],
        "products": [
            (
                "default",
                1,
                "GAS01",
                "Gas 13kg",
                "GAS",
                "35.90",
                None,
                None,
                10,
                1,
                STAMP,
                STAMP,
            ),
            (
                "default",
                2,
                "GAS02",
                "Gas 22kg",
                "GAS",
                "45.00",
                None,
                None,
                5,
                1,
                STAMP,
                STAMP,
            ),
            (
                "default",
                3,
                "GAS03",
                "Gas Cozinha",
                "GAS",
                "55.00",
                None,
                None,
                2,
                1,
                STAMP,
                STAMP,
            ),
        ],
        "delivery_drivers": [
            (
                "default",
                1,
                "DRV01",
                "Entregador Sintetico",
                "11977770001",
                "ABC1D23",
                1,
                None,
                "drv01",
                "hash-sintetico",
                "AVAILABLE",
                None,
                0,
                STAMP,
                STAMP,
            )
        ],
        "payments": [
            (
                "default",
                1,
                "ORD0001",
                "50.00",
                "CASH",
                "PAID",
                STAMP,
                None,
                "idem-1",
                None,
                STAMP,
            ),
            (
                "default",
                2,
                "ORD0002",
                "30.00",
                "PIX",
                "PAID",
                STAMP,
                None,
                "idem-2",
                None,
                STAMP,
            ),
            # pedido inexistente -> bloqueado
            (
                "default",
                3,
                "ORD8888",
                "10.00",
                "CASH",
                "PAID",
                STAMP,
                None,
                "idem-3",
                None,
                STAMP,
            ),
        ],
        "receivables": [
            (
                "default",
                1,
                "000001",
                "ORD0001",
                "25.00",
                "0.00",
                STAMP,
                "OPEN",
                STAMP,
                None,
            ),
            # cliente inexistente -> bloqueado
            (
                "default",
                2,
                "999999",
                "ORD0001",
                "15.00",
                "0.00",
                STAMP,
                "OPEN",
                STAMP,
                None,
            ),
        ],
        "financial_ledger": [
            (
                "default",
                1,
                "ORDER_CREATED",
                "35.90",
                "order",
                "ORD0001",
                "pedido",
                STAMP,
            ),
            (
                "default",
                2,
                "PAYMENT_RECEIVED",
                "50.00",
                "payment",
                "idem-1",
                "recebido",
                STAMP,
            ),
            (
                "default",
                3,
                "ORDER_CREATED",
                "45.00",
                "order",
                "ORD0002",
                "pedido",
                STAMP,
            ),
            (
                "default",
                4,
                "PAYMENT_RECEIVED",
                "30.00",
                "payment",
                "idem-2",
                "recebido",
                STAMP,
            ),
        ],
        "system_settings": [
            ("delivery_fee", "pricing", "7.50", None, 1, None, STAMP),
            ("quiet_hours", "messaging", '{"start": "22:00"}', None, 1, None, STAMP),
        ],
        "old_phones": [
            (1, "11966660001", "Contato Legado 1"),
            (2, "11966660002", "Contato Legado 2"),
        ],
    }


def create_source_db(
    path: str | Path,
    *,
    with_legacy_only_table: bool = True,
    with_unknown_column: bool = False,
    seed_rows: bool = True,
) -> dict[str, int]:
    """Cria o SQLite legado sintético e devolve as contagens VÁLIDAS esperadas."""
    path = Path(path)
    conn = sqlite3.connect(str(path))
    try:
        tables = dict(DDL)
        if not with_legacy_only_table:
            tables.pop("old_phones")
        for name in sorted(tables):
            ddl = tables[name]
            if name == "orders" and with_unknown_column:
                ddl = ddl.rstrip(")").rstrip() + ", legacy_flag TEXT)"
            conn.execute(ddl)
        if seed_rows:
            _insert_seed(conn, with_legacy_only_table)
        conn.commit()
    finally:
        conn.close()
    expected = dict(EXPECTED_DEFAULT_COUNTS)
    if with_unknown_column:
        expected["orders"] = 0
    if not with_legacy_only_table:
        expected.pop("old_phones", None)
    return expected


def _insert_seed(conn: sqlite3.Connection, with_legacy_only_table: bool) -> None:
    conn.executemany(
        "INSERT INTO clients VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", _client_rows()
    )
    conn.executemany(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", _order_rows()
    )
    others = _other_rows()
    conn.executemany(
        "INSERT INTO order_items VALUES (?,?,?,?,?,?,?,?,?)", others["order_items"]
    )
    conn.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", others["products"]
    )
    conn.executemany(
        "INSERT INTO delivery_drivers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        others["delivery_drivers"],
    )
    conn.executemany(
        "INSERT INTO payments VALUES (?,?,?,?,?,?,?,?,?,?,?)", others["payments"]
    )
    conn.executemany(
        "INSERT INTO receivables VALUES (?,?,?,?,?,?,?,?,?,?)", others["receivables"]
    )
    conn.executemany(
        "INSERT INTO financial_ledger VALUES (?,?,?,?,?,?,?,?)",
        others["financial_ledger"],
    )
    conn.executemany(
        "INSERT INTO system_settings VALUES (?,?,?,?,?,?,?)", others["system_settings"]
    )
    if with_legacy_only_table:
        conn.executemany("INSERT INTO old_phones VALUES (?,?,?)", others["old_phones"])
