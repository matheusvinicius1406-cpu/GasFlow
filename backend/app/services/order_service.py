from datetime import datetime

from app.models.order import Order
from app.models.client import Client


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

        order = Order(
            codigo=code,
            client_codigo=client.codigo,
            product=data.product,
            quantity=data.quantity,
            value=0.0,  # depois vamos colocar pricing
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