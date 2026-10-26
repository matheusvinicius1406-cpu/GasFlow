"""Mapeamento declarativo: SQLite legado -> schema atual (OPS-01D, Etapa 3).

Fonte de verdade executável do plano de migração documentado em
``docs/data-migration/mapping.md``. Regras:

* origem com tabela desconhecida no schema atual -> tabela BLOQUEADA
  (relatório), nunca cópia silenciosa;
* coluna de origem sem correspondência -> tabela BLOQUEADA (relatório);
* tabelas derivadas/internas entram em ``SKIP_TABLES`` e são ignoradas
  sem serem erro;
* ledgers imutáveis (``IMMUTABLE_TABLES``) migram só como cópia íntegra:
  se QUALQUER linha estiver inválida, a tabela inteira é bloqueada
  (nunca migração parcial de dado financeiro/log);
* relações por chave de negócio (``LOGICAL_FKS``) são verificadas antes da
  carga — órfãs são bloqueadas linha a linha, com relatório;
* ``tenant_id`` NULO nunca é preenchido por conta própria: a política
  ``block`` (padrão) segura a linha; ``platform`` só é aplicada com flag
  explícita, e usa o mesmo valor documentado do código
  (``PLATFORM_TENANT_ID`` de ``presentation/dependencies.py``).

Revisão obrigatória: se o schema atual ganhar/trocar tabelas ou chaves de
negócio, este arquivo precisa mudar junto (teste ``test_ops01d_mapping``).
"""

from __future__ import annotations

from dataclasses import dataclass

MAPPING_VERSION = "1.0.0"

# Espelha PLATFORM_TENANT_ID em backend/app/presentation/dependencies.py.
# Só é usado com a flag --null-tenant=platform (nunca implicitamente).
PLATFORM_TENANT_ID = "default"

NULL_TENANT_POLICIES = ("block", "platform")

# Tabelas derivadas/metadado: nunca são dados de negócio a migrar.
SKIP_TABLES = frozenset(
    {
        "_schema_version",
        "_ops01d_run",
        "alembic_version",
        "sqlite_sequence",
        "sqlite_stat1",
    }
)

# Assinatura do banco do serviço WhatsApp (Node, fica em SQLite por design —
# fora do escopo da migração para PostgreSQL).
WHATSAPP_SERVICE_MARKERS = frozenset({"_migration_tracking"})

# Assinatura mínima para reconhecer o banco do backend GasFlow.
BACKEND_REQUIRED_TABLES = frozenset({"clients"})

# Ledgers/append-only: cópia íntegra ou nada (ver docstring).
IMMUTABLE_TABLES = frozenset(
    {
        "auth_audit_log",
        "cash_movements",
        "driver_location_history",
        "financial_ledger",
        "idempotency_keys",
        "outbox_entries",
        "stock_movements",
        "whatsapp_messages",
    }
)

# Tabelas que existem nos dois lados mas são bloqueadas por decisão
# explícita (motivo obrigatório). Vazio na baseline OPS-01D: qualquer
# tabela desconhecida já é bloqueada dinamicamente pelo planejador.
BLOCKED_TABLES: dict[str, str] = {}


@dataclass(frozen=True)
class LogicalFk:
    """Relação por chave de negócio (o schema não tem FK para isto)."""

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    nullable: bool = True


LOGICAL_FKS: tuple[LogicalFk, ...] = (
    LogicalFk("orders", "client_codigo", "clients", "codigo", nullable=True),
    LogicalFk("order_items", "order_codigo", "orders", "codigo", nullable=False),
    LogicalFk("order_items", "product_codigo", "products", "codigo", nullable=False),
    LogicalFk("payments", "order_codigo", "orders", "codigo", nullable=False),
    LogicalFk("receivables", "order_codigo", "orders", "codigo", nullable=False),
    LogicalFk("receivables", "customer_codigo", "clients", "codigo", nullable=False),
)


def immutable_loss_blocked(table: str) -> bool:
    return table in IMMUTABLE_TABLES
