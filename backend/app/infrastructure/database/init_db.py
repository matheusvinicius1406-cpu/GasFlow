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
from app.infrastructure.repositories.driver_stock_model import (  # noqa: F401 — F7
    DriverStockModel,
    DriverStockEventModel,
)
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
from app.infrastructure.repositories.rbac_model import (  # noqa: F401
    PermissionModel,
    RolePermissionModel,
    UserPermissionOverrideModel,
    StockDailySnapshotModel,
)
from app.infrastructure.repositories.purchase_note_model import (  # noqa: F401
    PurchaseNoteModel,
    PurchaseNoteItemModel,
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
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default}'))
        conn.commit()


SCHEMA_VERSION = (
    4  # v4: Reorganização estrutural (docs/reorg-plan.md) — limpeza TOTAL do
    # banco (clients, whatsapp_conversations/messages, ai_conversations/messages)
    # + catálogo real (2 produtos: Água R$10, Gás P13 R$120 com cartão 1x/2x).
    # v3: Decisão B3(a) — débito de estoque movido do pedido CONFIRMED
    # para a entrega DELIVERED (reversão one-shot dos débitos prematuros;
    # ver _revert_premature_stock_debits e docs/migrations/2026-09-delivery-debit.md).
    # v2: colunas CRM de clients (has_name, is_whatsapp, last_interaction_at, last_sync_at, marketing_status)
)


def _backup_before_migration() -> None:
    """Backup automático do arquivo SQLite ANTES de qualquer migration (A.3).

    Roda só quando há migration pendente (versão gravada < SCHEMA_VERSION),
    antes do primeiro ALTER TABLE. Guarda até MAX_BACKUPS cópias em
    `<banco>.backups/gasflow-v<N>-<timestamp>.db` — se a migration corromper
    o banco, o dado do cliente é restaurável sem depender do usuário.
    Silenciosa em falha de backup? Não: loga e PROPAGA — melhor o app não
    migrar do que migrar sem rede de segurança.
    """
    import logging
    import shutil
    from datetime import datetime
    from pathlib import Path

    from sqlalchemy import text

    url = str(engine.url)
    if not url.startswith("sqlite"):
        return  # backup de arquivo só faz sentido para SQLite

    db_path = Path(url.removeprefix("sqlite:///")).resolve()
    if not db_path.exists():
        return  # banco novo — nada a proteger

    # Migration pendente? Compara versão gravada com a do código.
    pending = False
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version FROM _schema_version WHERE id = 1")).fetchone()
            pending = (row[0] if row else 0) < SCHEMA_VERSION
    except Exception:
        # Tabela ausente/ilegível = banco pré-versionamento: tem migration a
        # fazer (a _ensure_schema_version criará a tabela) → backupear.
        pending = True
    if not pending:
        return

    backups_dir = db_path.parent / f"{db_path.name}.backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backups_dir / f"{db_path.stem}-v{stamp}.db"
    shutil.copy2(db_path, dest)

    # Rotação: mantém só os MAX_BACKUPS mais recentes.
    MAX_BACKUPS = 5
    backups = sorted(backups_dir.glob(f"{db_path.stem}-v*.db"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink(missing_ok=True)

    logging.getLogger("gasflow.init_db").warning(
        "schema.backup.created",
        extra={"path": str(dest), "pending_version": True},
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


def _backfill_stock_full_empty() -> None:
    """P0 (Decisão A): backfill idempotente de cheios/vazios.

    Colunas novas criadas por create_all/_ensure_sqlite_columns chegam com 0;
    alinha quantity_full ao total apenas quando os dois detalhes estão
    zerados (primeiro boot após o upgrade) — não sobrescreve estado já
    gerenciado pela troca cheio→vazio da entrega (Decisão B2).
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE inventory SET quantity_full = quantity WHERE quantity_full = 0 AND quantity_empty = 0")
        )


def _seed_rbac_if_needed() -> None:
    """P0 RBAC: popula catálogo/matriz/roles (idempotente).

    Cobre os caminhos onde a migration e4f7a9b1c3d5 não roda: bancos legados
    create_all (stampados no boot do exe) e dev/testes (create_all puro).
    """
    import logging

    from sqlalchemy import text

    from app.infrastructure.database.rbac_seed import seed_rbac

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS permissions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "code VARCHAR(100) NOT NULL, description VARCHAR(200) NOT NULL, "
                "module VARCHAR(50) NOT NULL, created_at DATETIME NOT NULL, "
                "CONSTRAINT uq_permissions_code UNIQUE (code))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS role_permissions ("
                "role_id VARCHAR(36) NOT NULL, permission_id INTEGER NOT NULL, "
                "PRIMARY KEY (role_id, permission_id), "
                "CONSTRAINT uq_role_permissions_role_permission UNIQUE (role_id, permission_id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS user_permissions_override ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id VARCHAR(36) NOT NULL, permission_id INTEGER NOT NULL, "
                "granted BOOLEAN NOT NULL, created_by VARCHAR(36), "
                "created_at DATETIME NOT NULL, "
                "CONSTRAINT uq_user_perm_override_user_permission UNIQUE (user_id, permission_id))"
            )
        )
        stats = seed_rbac(conn)

    if stats["permissions_inserted"] or stats["matrix_rows_inserted"]:
        logging.getLogger("gasflow.init_db").info(
            "rbac.seed.applied",
            extra={**stats},
        )


def _revert_premature_stock_debits() -> None:
    """Decisão B3(a) v3: reverte débitos prematuros de pedidos CONFIRMED.

    A versão anterior debitava estoque no Order CONFIRMED (reserva). Com a
    mudança da regra (débito só na entrega DELIVERED), pedidos confirmados
    e ainda não entregues ficariam com estoque debitado para sempre.

    One-shot e idempotente (marca de controle em system_settings):
    1. Pedidos CONFIRMED (não CANCELLED/DELIVERED) com movimento SALE
       reference_type=ORDER e sem entrega DELIVERED:
       credita de volta quantity/quantity_full via movimento
       RESERVATION_REVERSAL (reference_id = `revert:<codigo>`).
    2. Pedidos DELIVERED sem entrega DELIVERED correspondente (finalizados
       pelo fluxo antigo do pedido): idem — a entrega real vai debitá-los
       de novo (SALE DELIVERY), sem duplo débito líquido.
    3. Pedidos CANCELLED com SALE ORDER sem RETURN correspondente:
       credita de volta (o fluxo antigo podia ter deixado débito órfão).
    4. Audit trail em auth_audit_log (SYSTEM/MIGRATION).
    5. Marca a execução — rodar 2x não faz nada.
    """
    import json
    import logging
    import uuid
    from datetime import datetime

    from sqlalchemy import text

    MARKER = "stock_debit_migration_v3"
    log = logging.getLogger("gasflow.init_db")

    with engine.begin() as conn:
        done = conn.execute(text("SELECT value FROM system_settings WHERE id = :id"), {"id": MARKER}).fetchone()
        if done:
            return

        # Uma linha por (order, product): a constraint de idempotência é
        # (reference_type, reference_id, product_codigo, type) — a SALE do
        # pedido antigo existe, o par de reversão usa type RESERVATION_REVERSAL.
        candidates = conn.execute(
            text(
                """
                SELECT m.reference_id AS order_codigo, m.product_codigo AS product_codigo,
                       m.quantity AS quantity
                FROM stock_movements m
                WHERE m.reference_type = 'ORDER'
                  AND m.type = 'SALE'
                  AND m.reference_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM stock_movements r
                      WHERE r.reference_type = 'RESERVATION_REVERSAL'
                        AND r.reference_id = m.reference_id
                        AND r.product_codigo = m.product_codigo
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM stock_movements r2
                      WHERE r2.reference_type = 'ORDER_RETURN'
                        AND r2.reference_id = m.reference_id
                        AND r2.product_codigo = m.product_codigo
                  )
                """
            )
        ).fetchall()

        reverted = 0
        skipped = 0
        for row in candidates:
            order_codigo = row.order_codigo
            product_codigo = row.product_codigo
            qty = int(row.quantity or 0)
            if qty <= 0:
                continue

            order = conn.execute(
                text("SELECT status FROM orders WHERE codigo = :codigo"),
                {"codigo": order_codigo},
            ).fetchone()
            if order is None:
                skipped += 1
                continue
            status = str(order.status or "")

            delivery_delivered = conn.execute(
                text("SELECT 1 FROM delivery_records WHERE order_id = :oid AND status = 'DELIVERED' LIMIT 1"),
                {"oid": order_codigo},
            ).fetchone()
            # CONFIRMED não entregue = débito prematuro.
            # DELIVERED sem entrega real = será debitado pela entrega —
            # reverter agora evita duplo débito líquido.
            premature = (status == "CONFIRMED" and not delivery_delivered) or (
                status == "DELIVERED" and not delivery_delivered
            )
            # CANCELLED com débito órfão (sem devolução) também reverte.
            orphan_cancel = status == "CANCELLED"
            if not (premature or orphan_cancel):
                skipped += 1
                continue

            inv = conn.execute(
                text("SELECT id FROM inventory WHERE product_codigo = :code LIMIT 1"),
                {"code": product_codigo},
            ).fetchone()
            if inv is None:
                skipped += 1
                continue

            balances = conn.execute(
                text(
                    "SELECT quantity, quantity_full, quantity_empty FROM inventory WHERE product_codigo = :code LIMIT 1"
                ),
                {"code": product_codigo},
            ).fetchone()
            if balances is None:
                skipped += 1
                continue
            balance_before = int(balances.quantity or 0)
            full_before = int(balances.quantity_full or 0)
            empty_before = int(balances.quantity_empty or 0)

            conn.execute(
                text(
                    "UPDATE inventory SET quantity = quantity + :qty, "
                    "quantity_full = quantity_full + :qty, updated_at = :now "
                    "WHERE product_codigo = :code"
                ),
                {"qty": qty, "now": datetime.utcnow(), "code": product_codigo},
            )
            conn.execute(
                text(
                    "INSERT INTO stock_movements (product_codigo, type, quantity, "
                    "quantity_full_delta, quantity_empty_delta, reason, reference_type, "
                    "reference_id, balance_before, balance_after, created_at) "
                    "VALUES (:code, 'RESERVATION_REVERSAL', :qty, :qty, 0, :reason, "
                    "'RESERVATION_REVERSAL', :ref, :bb, :ba, :now)"
                ),
                {
                    "code": product_codigo,
                    "qty": qty,
                    "reason": f"Migration v3 — reversão de débito prematuro do pedido #{order_codigo}",
                    "ref": f"revert:{order_codigo}",
                    "bb": balance_before,
                    "ba": balance_before + qty,
                    "now": datetime.utcnow(),
                },
            )

            conn.execute(
                text(
                    "INSERT INTO auth_audit_log (id, actor_id, actor_type, tenant_id, action, "
                    "resource, resource_id, result, timestamp, ip_address, user_agent, platform, details) "
                    "VALUES (:id, 'system', 'SYSTEM', 'default', 'stock.migration.revert', "
                    "'inventory', :ref, 'SUCCESS', :ts, '', '', 'desktop', :details)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "ref": f"revert:{order_codigo}",
                    "ts": datetime.utcnow(),
                    "details": json.dumps(
                        {
                            "order_codigo": order_codigo,
                            "product_codigo": product_codigo,
                            "quantity": qty,
                            "full_before": full_before,
                            "empty_before": empty_before,
                            "order_status": status,
                        }
                    ),
                },
            )
            reverted += 1

        conn.execute(
            text(
                "INSERT INTO system_settings (id, category, value, description, is_editable, updated_at) "
                "VALUES (:id, 'operations', :value, :description, 0, :ts)"
            ),
            {
                "id": MARKER,
                "value": json.dumps(
                    {
                        "reverted": reverted,
                        "skipped": skipped,
                        "executed_at": datetime.utcnow().isoformat(),
                    }
                ),
                "description": "Decisão B3(a): migração one-shot de débito de estoque (v3)",
                "ts": datetime.utcnow(),
            },
        )

    if reverted:
        log.warning(
            "stock.migration.v3.applied",
            extra={"reverted": reverted, "skipped": skipped},
        )


def _reorg_cleanup() -> None:
    """v4 — Limpeza TOTAL do banco + catálogo real (docs/reorg-plan.md §2).

    Decisão do dono (15/09/2026): zerar clientes/conversas/dados de teste e
    recomeçar com números reais. One-shot e idempotente (marcador em
    system_settings). O backup do arquivo é feito por _backup_before_migration.

    Apaga: clients, whatsapp_conversations, whatsapp_messages,
    ai_conversations, ai_messages, ai_audit_log, site_leads, segments,
    coupons/coupon_redemptions, purchase_notes* (se existirem com dados).
    Re-seeda: catálogo com 2 produtos reais informados pelo dono.
    NUNCA toca: auth_*, permissions, role_permissions, system_settings.
    """
    import logging
    from sqlalchemy import text

    MARKER = "reorg_cleanup_v4"
    logger = logging.getLogger("gasflow.init_db")

    with engine.begin() as conn:
        try:
            row = conn.execute(text("SELECT value FROM system_settings WHERE id = :k"), {"k": MARKER}).fetchone()
        except Exception:
            row = None  # tabela ainda não existe — segue e cria via INSERT
        if row:
            return  # já executada

        logger.warning("reorg.v4.cleanup_start")

        # Apaga dados de operação/teste (ordem respeita FKs lógicas).
        for table in (
            "whatsapp_messages",
            "whatsapp_conversations",
            "ai_messages",
            "ai_conversations",
            "ai_audit_logs",
            "site_leads",
            "segments",
            "coupon_redemptions",
            "coupons",
            "purchase_note_items",
            "purchase_notes",
            "clients",
            "products",
        ):
            try:
                conn.execute(text(f"DELETE FROM {table}"))
            except Exception:
                # Tabela pode não existir em bases novas — seguir.
                pass

        # ── Catálogo REAL informado pelo dono ──
        # Água 20L: R$ 10,00 (dinheiro/pix/débito)
        # Gás P13:  R$ 120,00 (dinheiro/pix/débito) | cartão 1x R$ 125 | 2x R$ 130
        conn.execute(
            text(
                """INSERT INTO products
                (tenant_id, codigo, nome, tipo, preco, cartao_habilitado,
                 preco_cartao_1x, preco_cartao_2x, estoque, ativo, created_at, updated_at)
                VALUES
                ('default', '000001', 'Galao de Agua 20L', 'AGUA', 10.0, 0, NULL, NULL, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('default', '000002', 'Botijao de Gas P13 (13kg)', 'GAS', 120.0, 1, 125.0, 130.0, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
            )
        )

        conn.execute(
            text(
                """INSERT INTO system_settings (id, category, value, description, is_editable, updated_by, updated_at)
                VALUES (:k, 'operations', :v, :d, 0, 'migration', CURRENT_TIMESTAMP)"""
            ),
            {
                "k": MARKER,
                "v": '{"done": true, "date": "2026-09-15"}',
                "d": "Reorganizacao estrutural v4: limpeza total + catalogo real",
            },
        )
        logger.warning("reorg.v4.cleanup_done")


def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        _backup_before_migration()
        _ensure_sqlite_columns()
        _ensure_schema_version()
        _backfill_stock_full_empty()
        _revert_premature_stock_debits()
        _reorg_cleanup()
        _seed_rbac_if_needed()
    except Exception:  # pragma: no cover — nunca derrubar o boot por migration
        import logging

        logging.getLogger("gasflow.init_db").exception("schema migration leve falhou")
