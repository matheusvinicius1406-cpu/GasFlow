from app.infrastructure.database.base import Base
from app.infrastructure.database.connection import engine

# Importa todos os modelos para criar as tabelas
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
from app.infrastructure.repositories.vehicle_model import VehicleModel, VehicleCapacityModel, VehicleLoadModel
from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.financial_models import (
    PaymentModel, ReceivableModel, ExpenseModel,
    CashMovementModel, FinancialLedgerModel
)
from app.infrastructure.ai.models import ConversationModel, AIMessageModel, AIAuditLogModel
from app.infrastructure.repositories.delivery_persistence_model import (
    DeliveryRecord, DriverLocationRecord, OutboxEntry,
    DriverSessionRecord, IdempotencyKeyRecord
)
from app.infrastructure.repositories.auth_model import (
    AuthUserModel, AuthSessionModel, AuthTenantModel,
    AuthRoleModel, AuthMembershipModel, AuthAuditModel
)
from app.infrastructure.repositories.payment_model import (
    PaymentMethodRecord, PixConfigRecord, PaymentServiceRecord
)
from app.infrastructure.repositories.route_model import RouteRecord, RouteStopRecord
# Models adicionais usados em runtime (importados via routers em main.py).
# Mantidos aqui explicitamente para que init_db() e as migrations Alembic
# reflitam o MESMO conjunto de tabelas do app (evita drift de schema).
from app.infrastructure.repositories.whatsapp_automation_model import (
    AutomationRuleModel, AutomationExecutionModel
)
from app.infrastructure.repositories.segmentation_model import SegmentModel



def init_db():
    Base.metadata.create_all(bind=engine)
