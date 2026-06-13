from datetime import datetime

from app.models.order import Order
from app.models.client import Client
from app.models.delivery_driver import DeliveryDriver
from app.services.pricing_service import PricingService


class OrderService:

    @staticmethod
    def generate_code(db) -> str:
        last = db.query(Order).order_by(Order.id.desc()).first()

        if not last:
            return "000001"

        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db, data):

        client = db.query(Client).filter(Client.codigo == data.client_codigo).first()

        if not client:
            raise Exception("Cliente não encontrado")

        code = OrderService.generate_code(db)

        address = f"{client.rua}, {client.numero} - {client.bairro}"

        value = PricingService.calculate(db, data.product, data.quantity)

        order = Order(
            codigo=code,
            client_codigo=client.codigo,
            product=data.product,
            quantity=data.quantity,
            value=value,
            address_snapshot=address,
            status="PENDING",
            payment_method=data.payment_method,
            created_at=datetime.utcnow()
        )

        db.add(order)
        db.commit()
        db.refresh(order)

        return order

    @staticmethod
    def get_all(db):
        return db.query(Order).all()

    @staticmethod
    def get_by_code(db, codigo: str):
        return db.query(Order).filter(Order.codigo == codigo).first()

    @staticmethod
    def update_status(db, codigo: str, status: str):
        order = db.query(Order).filter(Order.codigo == codigo).first()

        if not order:
            return None

        order.status = status
        db.commit()
        db.refresh(order)

        return order

    @staticmethod
    def assign_driver(db, codigo: str, driver_codigo: str):
        order = db.query(Order).filter(Order.codigo == codigo).first()

        if not order:
            return None

        driver = db.query(DeliveryDriver).filter(
            DeliveryDriver.codigo == driver_codigo,
            DeliveryDriver.ativo == True
        ).first()

        if not driver:
            raise Exception("Entregador não encontrado ou inativo")

        order.delivery_driver_codigo = driver_codigo
        db.commit()
        db.refresh(order)

        return order