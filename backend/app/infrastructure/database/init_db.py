from app.infrastructure.database.base import Base  # noqa: F401
from app.infrastructure.database.connection import engine

# Importa todos os modelos para criar as tabelas.
# Os imports abaixo são side-effect: registrar a classe no módulo faz o
# SQLAlchemy registrar a tabela no Base.metadata. Por isso F401 é ignorado
# de propósito (os nomes não são usados diretamente aqui).

# Models adicionais usados em runtime (importados via routers em main.py).
# Mantidos aqui explicitamente para que init_db() e as migrations Alembic
# reflitam o MESMO conjunto de tabelas do app (evita drift de schema).
from app.infrastructure.repositories.client_model import ClientModel  # noqa: F401
from app.infrastructure.repositories.order_model import OrderModel  # noqa: F401
from app.infrastructure.repositories.order_item_model import OrderItemModel  # noqa: F401
from app.infrastructure.repositories.product_model import ProductModel  # noqa: F401
from app.infrastructure.repositories.delivery_model import DeliveryDriverModel  # noqa: F401
from app.infrastructure.repositories.vehicle_model import (  # noqa: F401
    VehicleModel,
    VehicleCapacityModel,
    VehicleLoadModel,
)
from app.infrastructure.repositories.whatsapp_model import (  # noqa: F401
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from app.infrastructure.repositories.inventory_model import (  # noqa: F401
    InventoryModel,
    StockMovementModel,
)
from app.infrastructure.repositories.financial_models import (  # noqa: F401
    PaymentModel,
    ReceivableModel,
    ExpenseModel,
    CashMovementModel,
    FinancialLedgerModel,
)
from app.infrastructure.ai.models import (  # noqa: F401
    ConversationModel,
    AIMessageModel,
    AIAuditLogModel,
)
from app.infrastructure.repositories.delivery_persistence_model import (  # noqa: F401
    DeliveryRecord,
    DriverLocationRecord,
    OutboxEntry,
    DriverSessionRecord,
    IdempotencyKeyRecord,
)
from app.infrastructure.repositories.auth_model import (  # noqa: F401
    AuthUserModel,
    AuthSessionModel,
    AuthTenantModel,
    AuthRoleModel,
    AuthMembershipModel,
    AuthAuditModel,
)
from app.infrastructure.repositories.payment_model import (  # noqa: F401
    PaymentMethodRecord,
    PixConfigRecord,
    PaymentServiceRecord,
)
from app.infrastructure.repositories.route_model import (  # noqa: F401
    RouteRecord,
    RouteStopRecord,
)
from app.infrastructure.repositories.whatsapp_automation_model import (  # noqa: F401
    AutomationRuleModel,
    AutomationExecutionModel,
)
from app.infrastructure.repositories.segmentation_model import SegmentModel  # noqa: F401
from app.infrastructure.repositories.settings_model import SystemSettingModel  # noqa: F401
from app.infrastructure.repositories.coupon_model import (  # noqa: F401
    CouponModel,
    CouponRedemptionModel,
)
from app.infrastructure.repositories.lead_model import LeadModel  # noqa: F401
from app.infrastructure.repositories.integration_model import (  # noqa: F401
    IntegrationModel,
    ImportedOrderModel,
    SyncLogModel,
)


def _ensure_sqlite_columns() -> None:
    """Migrations leves e idempotentes para SQLite em produção (app Desktop).

    `Base.metadata.create_all()` cria tabelas NOVAS, mas nunca altera tabelas
    já existentes — um banco criado por uma versão antiga do app fica sem as
    colunas novas (ex.: clients.has_name/is_whatsapp/last_interaction_at/
    last_sync_at/marketing_status), derrubando todo SELECT/INSERT da entidade
    com `OperationalError: no such column`.

    Aqui comparamos o schema real (PRAGMA table_info) com o metadata e
    adicionamos as colunas faltantes via ALTER TABLE. Tipos SQLite são
    permissivos; defaults aplicam-se a linhas novas (NULL para as antigas).
    """
    from sqlalchemy import text

    type_map = {str: "TEXT", bool: "BOOLEAN", int: "INTEGER", float: "REAL"}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info("{table.name}")')).fetchall()}
            if not existing:
                continue  # tabela ainda não existe — create_all cuida dela
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = type_map.get(column.type.python_type, "TEXT")
                default = ""
                if column.nullable is False:
                    default = " DEFAULT ''" if col_type == "TEXT" else " DEFAULT 0"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" ' f"{col_type}{default}"))
        conn.commit()


SCHEMA_VERSION = (
    2  # v2: colunas CRM de clients (has_name, is_whatsapp, last_interaction_at, last_sync_at, marketing_status)
)


def _ensure_schema_version() -> None:
    """Grava a versão de schema aplicada — permite detectar drift em logs.

    Idempotente: a tabela só tem a linha id=1 e o upsert não cria duplicatas.
    Deve rodar DEPOIS de _ensure_sqlite_columns() (que migra o que falta).
    """
    import logging
    from datetime import datetime

    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE IF NOT EXISTS _schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )"""
            )
        )
        row = conn.execute(text("SELECT version FROM _schema_version WHERE id = 1")).fetchone()
        current = row[0] if row else 0
        if current < SCHEMA_VERSION:
            logging.getLogger("gasflow.init_db").warning(
                "schema.version.migrated",
                extra={"from": current, "to": SCHEMA_VERSION},
            )
        conn.execute(
            text(
                """INSERT INTO _schema_version (id, version, updated_at)
                VALUES (1, :v, :ts)
                ON CONFLICT(id) DO UPDATE SET version = :v, updated_at = :ts"""
            ),
            {"v": SCHEMA_VERSION, "ts": datetime.utcnow().isoformat()},
        )


def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        _ensure_sqlite_columns()
        _ensure_schema_version()
    except Exception:  # pragma: no cover — nunca derrubar o boot por migration
        import logging

        logging.getLogger("gasflow.init_db").exception("schema migration leve falhou")
