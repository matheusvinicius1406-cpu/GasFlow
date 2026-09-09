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


def init_db():
    Base.metadata.create_all(bind=engine)
