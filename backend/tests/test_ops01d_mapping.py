"""Testes OPS-01D: mapeamento declarativo × schema atual.

Se o schema ganhar/trocar tabelas ou chaves de negócio, estes testes falham
juntos com mapping.py — obrigando atualizar o executável e a documentação
(docs/data-migration/mapping.md).
"""

import sys
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "home-server" / "data"
if str(_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(_DATA_DIR))

import mapping as m  # noqa: E402
import synthetic  # noqa: E402
from app.infrastructure.database.base import Base  # noqa: E402


def _tables() -> dict:
    return Base.metadata.tables


def test_logical_fks_point_to_existing_schema():
    tables = _tables()
    for fk in m.LOGICAL_FKS:
        assert fk.child_table in tables, fk.child_table
        assert fk.parent_table in tables, fk.parent_table
        assert fk.child_column in tables[fk.child_table].columns, fk
        assert fk.parent_column in tables[fk.parent_table].columns, fk


def test_immutable_tables_exist_in_schema():
    tables = _tables()
    for name in m.IMMUTABLE_TABLES:
        assert name in tables, name


def test_backend_signature_and_skip_tables():
    tables = _tables()
    assert m.BACKEND_REQUIRED_TABLES.issubset(set(tables))
    assert "_ops01d_run" in m.SKIP_TABLES
    assert "alembic_version" in m.SKIP_TABLES


def test_platform_tenant_id_mirrors_dependencies():
    from app.presentation.dependencies import PLATFORM_TENANT_ID

    assert m.PLATFORM_TENANT_ID == PLATFORM_TENANT_ID


def test_blocked_tables_have_reasons_and_null_tenant_policies():
    for name, reason in m.BLOCKED_TABLES.items():
        assert reason, name
    assert m.NULL_TENANT_POLICIES == ("block", "platform")
    assert "block" in m.NULL_TENANT_POLICIES


def test_synthetic_fixture_contract():
    ddl_tables = set(synthetic.DDL)
    assert set(synthetic.EXPECTED_DEFAULT_COUNTS) <= ddl_tables
    assert "old_phones" in ddl_tables  # legada de exercício (bloqueada)
    assert synthetic.EXPECTED_DEFAULT_COUNTS["clients"] == 5


def test_marker_table_is_skipped_and_not_migrated():
    # _ops01d_run é criada só no alvo pelo ensaio; a origem nunca a migra.
    assert "_ops01d_run" in m.SKIP_TABLES
    assert m.immutable_loss_blocked("financial_ledger") is True
    assert m.immutable_loss_blocked("clients") is False
