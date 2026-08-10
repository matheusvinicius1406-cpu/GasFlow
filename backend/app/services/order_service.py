from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError, NotFoundError, ValidationError
from app.core.order_state import can_transition
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.repositories.client_repository import ClientRepository
from app.repositories.delivery_driver_repository import DeliveryDriverRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.services.stock_service import StockService


class OrderService:

    @staticmethod
    def generate_code(db: Session, company_id: int) -> str:
        last = OrderRepository(db, company_id).last()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db: Session, company_id: int, data, user_id: int | None = None) -> Order:
        clients = ClientRepository(db, company_id)
        products = ProductRepository(db, company_id)
        orders = OrderRepository(db, company_id)

        client = clients.get_by_code(data.client_codigo)
        if not client:
            raise NotFoundError("Cliente não encontrado")

        if not data.items:
            raise ValidationError("Pedido deve conter ao menos um item")

        # Consolida itens repetidos do mesmo produto em uma única linha.
        requested: dict[str, int] = {}
        for item in data.items:
            if item.quantity <= 0:
                raise ValidationError("Quantidade deve ser maior que zero")
            requested[item.product] = requested.get(item.product, 0) + item.quantity

        # Carrega e valida todos os produtos com lock de linha (ordem estável
        # por código evita deadlock entre pedidos concorrentes).
        priced: list[tuple] = []
        total = 0.0
        for product_codigo in sorted(requested):
            quantity = requested[product_codigo]
            product = products.get_for_update(product_codigo)
            if not product:
                raise NotFoundError(f"Produto {product_codigo} não encontrado")
            if product.estoque < quantity:
                raise InsufficientStockError(
                    f"Estoque insuficiente para {product_codigo}. "
                    f"Disponível: {product.estoque}, solicitado: {quantity}"
                )
            subtotal = product.preco * quantity
            total += subtotal
            priced.append((product, quantity, product.preco, subtotal))

        code = OrderService.generate_code(db, company_id)
        address = f"{client.rua}, {client.numero} - {client.bairro}"

        order = Order(
            company_id=company_id,
            codigo=code,
            client_id=client.id,
            client_codigo=client.codigo,
            value=total,
            address_snapshot=address,
            status=OrderStatus.PENDING.value,
            payment_method=data.payment_method,
        )
        orders.add(order)  # flush -> order.id

        for product, quantity, unit_price, subtotal in priced:
            order.items.append(
                OrderItem(
                    product_id=product.id,
                    product_codigo=product.codigo,
                    product_nome=product.nome,
                    quantity=quantity,
                    unit_price=unit_price,
                    subtotal=subtotal,
                )
            )
            StockService.sell(db, company_id, product, quantity, order.id)

        OrderService._record_status(db, order, None, OrderStatus.PENDING.value, user_id)

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
    def get_history(db: Session, company_id: int, codigo: str) -> list[OrderStatusHistory] | None:
        order = OrderRepository(db, company_id).get_by_code(codigo)
        if not order:
            return None
        return order.status_history

    @staticmethod
    def update_status(
        db: Session, company_id: int, codigo: str, status: str, user_id: int | None = None
    ) -> Order | None:
        orders = OrderRepository(db, company_id)
        products = ProductRepository(db, company_id)

        order = orders.get_by_code(codigo)
        if not order:
            return None

        if status == order.status:
            return order

        if not can_transition(order.status, status):
            raise ValidationError(
                f"Transição de status inválida: {order.status} -> {status}"
            )

        # Cancelamento devolve o estoque reservado pelo pedido.
        if status == OrderStatus.CANCELLED.value:
            for item in order.items:
                if item.product_codigo:
                    product = products.get_for_update(item.product_codigo)
                    if product:
                        StockService.restock(db, company_id, product, item.quantity, order.id)

        previous = order.status
        order.status = status
        OrderService._record_status(db, order, previous, status, user_id)

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

    @staticmethod
    def _record_status(
        db: Session, order: Order, from_status: str | None, to_status: str, user_id: int | None
    ) -> None:
        order.status_history.append(
            OrderStatusHistory(
                from_status=from_status,
                to_status=to_status,
                changed_by_user_id=user_id,
            )
        )
