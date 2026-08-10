from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError, NotFoundError, ValidationError
from app.models.order import Order, OrderStatus
from app.repositories.client_repository import ClientRepository
from app.repositories.delivery_driver_repository import DeliveryDriverRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.services.pricing_service import PricingService


class OrderService:

    @staticmethod
    def generate_code(db: Session, company_id: int) -> str:
        last = OrderRepository(db, company_id).last()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db: Session, company_id: int, data) -> Order:
        clients = ClientRepository(db, company_id)
        products = ProductRepository(db, company_id)
        orders = OrderRepository(db, company_id)

        client = clients.get_by_code(data.client_codigo)
        if not client:
            raise NotFoundError("Cliente não encontrado")

        # Lock de linha do produto: impede venda concorrente de estoque inexistente.
        product = products.get_for_update(data.product)
        if not product:
            raise NotFoundError("Produto não encontrado")

        if data.quantity <= 0:
            raise ValidationError("Quantidade deve ser maior que zero")

        if product.estoque < data.quantity:
            raise InsufficientStockError(
                f"Estoque insuficiente. Disponível: {product.estoque}, "
                f"solicitado: {data.quantity}"
            )

        code = OrderService.generate_code(db, company_id)
        address = f"{client.rua}, {client.numero} - {client.bairro}"
        value = PricingService.calculate(db, company_id, data.product, data.quantity)

        product.estoque -= data.quantity

        order = Order(
            company_id=company_id,
            codigo=code,
            client_id=client.id,
            product_id=product.id,
            client_codigo=client.codigo,
            product=data.product,
            quantity=data.quantity,
            value=value,
            address_snapshot=address,
            status=OrderStatus.PENDING.value,
            payment_method=data.payment_method,
        )

        orders.add(order)
        return orders.commit_refresh(order)

    @staticmethod
    def get_all(
        db: Session,
        company_id: int,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        filters = {"status": status} if status else {}
        return OrderRepository(db, company_id).list(limit=limit, offset=offset, **filters)

    @staticmethod
    def get_by_code(db: Session, company_id: int, codigo: str) -> Order | None:
        return OrderRepository(db, company_id).get_by_code(codigo)

    @staticmethod
    def update_status(db: Session, company_id: int, codigo: str, status: str) -> Order | None:
        orders = OrderRepository(db, company_id)
        order = orders.get_by_code(codigo)
        if not order:
            return None

        order.status = status
        return orders.commit_refresh(order)

    @staticmethod
    def assign_driver(
        db: Session, company_id: int, codigo: str, driver_codigo: str
    ) -> Order | None:
        orders = OrderRepository(db, company_id)
        drivers = DeliveryDriverRepository(db, company_id)

        order = orders.get_by_code(codigo)
        if not order:
            return None

        driver = drivers.get_by(codigo=driver_codigo, ativo=True)
        if not driver:
            raise ValidationError("Entregador não encontrado ou inativo")

        order.delivery_driver_id = driver.id
        order.delivery_driver_codigo = driver_codigo
        return orders.commit_refresh(order)
