from app.infrastructure.database.base import Base
from app.infrastructure.database.connection import engine

# Importa todos os modelos para criar as tabelas
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel


def init_db():
    Base.metadata.create_all(bind=engine)
