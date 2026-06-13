from app.database.base import Base
from app.database.connection import engine

from app.models.client import Client
from app.models.order import Order
from app.models.product import Product
from app.models.delivery_driver import DeliveryDriver


def init_db():
    Base.metadata.create_all(bind=engine)