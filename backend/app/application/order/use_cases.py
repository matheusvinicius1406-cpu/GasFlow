"""
Order Use Cases — FASE 7.1

CRITICAL CHANGE (Decisão B3(a), 14/09/2026): estoque só é debitado quando a
ENTREGA é finalizada (DELIVERED) — ver delivery_persistence_repository.
- Stock validated against Inventory.quantity (not Product.estoque) at creation
- Order CONFIRMED NÃO debita mais (o caminhão pode sair com reserva; o
  débito é o fato físico da entrega)
- Order CANCELLED não mexe no estoque (nada foi debitado); a reversão do
  débito acontece no cancelamento da ENTREGA após DELIVERED
- All inventory operations are atomic (single transaction)
"""

from datetime import datetime
from typing import Optional, List
from app.domain.order.entity import Order, OrderStatus, PaymentStatus, OrderSource
from app.domain.order.repository import OrderRepository
from app.domain.order_item.entity import OrderItem
from app.domain.order_item.repository import OrderItemRepository
from app.domain.client.repository import ClientRepository
from app.domain.product.repository import ProductRepository
from app.domain.inventory.repository import InventoryRepository


class CreateOrderUseCase:
    """Create a new order with multiple items.

    Stock is validated against Inventory but NOT deducted at creation.
    Deduction happens when the DELIVERY is completed (Decisão B3a).
    """

    def __init__(
        self,
        order_repo: OrderRepository,
        order_item_repo: OrderItemRepository,
        client_repo: ClientRepository,
        product_repo: ProductRepository,
        inventory_repo: Optional[InventoryRepository] = None,
    ):
        self.order_repo = order_repo
        self.order_item_repo = order_item_repo
        self.client_repo = client_repo
        self.product_repo = product_repo
        self.inventory_repo = inventory_repo

    def _available_stock(self, product) -> float:
        """Estoque disponível: Inventory (FASE 7.1) com fallback a Product.estoque."""
        if self.inventory_repo:
            inv = self.inventory_repo.get_by_product(product.codigo)
            return inv.quantity if inv else 0
        # Backward compatibility: fallback to Product.estoque
        return product.estoque

    def _build_item(self, item_data: dict, codigo: str) -> tuple:
        """Valida e monta um OrderItem com preço congelado (backend é a autoridade)."""
        product = self.product_repo.buscar_por_codigo(item_data["product_codigo"])
        if not product:
            raise ValueError(f"Produto {item_data['product_codigo']} não encontrado")

        if not product.ativo:
            raise ValueError(f"Produto {product.nome} está desativado")

        quantity = item_data.get("quantity", 1)
        if quantity <= 0:
            raise ValueError(f"Quantidade inválida para {product.nome}")

        available = self._available_stock(product)
        if available < quantity:
            raise ValueError(
                f"Estoque insuficiente para {product.nome}. Disponível: {available}, solicitado: {quantity}"
            )

        unit_price = product.preco
        item = OrderItem(
            order_codigo=codigo,
            product_codigo=product.codigo,
            product_nome=product.nome,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=unit_price * quantity,
        )
        return item, item.subtotal

    def _build_items(self, items_data: list, codigo: str) -> tuple:
        """Monta todos os itens do pedido e retorna (itens, subtotal)."""
        order_items = []
        subtotal = 0.0
        for item_data in items_data:
            item, item_subtotal = self._build_item(item_data, codigo)
            order_items.append(item)
            subtotal += item_subtotal
        return order_items, subtotal

    def execute(self, data: dict) -> Order:
        # 1. Validate client
        client = self.client_repo.buscar_por_codigo(data["client_codigo"])
        if not client:
            raise ValueError("Cliente não encontrado")
        if not client.ativo:
            raise ValueError("Cliente está desativado")

        # 2. Validate items
        items_data = data.get("items", [])
        if not items_data:
            raise ValueError("Pedido deve ter pelo menos um item")

        # 3. Generate code
        codigo = self.order_repo.proximo_codigo()

        # 4. Address snapshot
        address = data.get("address_snapshot") or f"{client.rua}, {client.numero} - {client.bairro}"
        if client.complemento:
            address += f" ({client.complemento})"
        if client.referencia:
            address += f" - Ref: {client.referencia}"

        # 5. Create items with frozen price (validação de estoque + preço congelado)
        order_items, subtotal = self._build_items(items_data, codigo)

        # 6. Financial calculation
        delivery_fee = data.get("delivery_fee", 0.0)
        if delivery_fee < 0:
            delivery_fee = 0.0

        discount = data.get("discount", 0.0)
        if discount < 0:
            discount = 0.0

        if discount > subtotal:
            raise ValueError(f"Desconto (R$ {discount:.2f}) não pode exceder subtotal (R$ {subtotal:.2f})")

        total = subtotal + delivery_fee - discount
        if total < 0:
            raise ValueError(f"Total (R$ {total:.2f}) não pode ser negativo")

        # 7. Create order
        order = Order(
            codigo=codigo,
            client_codigo=client.codigo,
            address_snapshot=address,
            status=OrderStatus.PENDING,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            discount=discount,
            total=total,
            payment_method=data.get("payment_method"),
            payment_status=PaymentStatus.PENDING,
            source=OrderSource(data.get("source", "MANUAL")),
            notes=data.get("notes"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        order = self.order_repo.criar(order)

        # Save items
        for item in order_items:
            self.order_item_repo.criar(item)

        return order


class GetOrderUseCase:
    def __init__(self, order_repo: OrderRepository, order_item_repo: OrderItemRepository):
        self.order_repo = order_repo
        self.order_item_repo = order_item_repo

    def execute(self, codigo: str) -> Optional[Order]:
        order = self.order_repo.buscar_por_codigo(codigo)
        if order:
            order.items = self.order_item_repo.listar_por_pedido(codigo)
        return order


class ListOrdersUseCase:
    def __init__(self, repository: OrderRepository):
        self.repository = repository

    def execute(self, status: Optional[str] = None) -> List[Order]:
        order_status = None
        if status:
            try:
                order_status = OrderStatus(status)
            except ValueError as exc:
                raise ValueError(f"Status inválido: {status}") from exc
        return self.repository.listar_todos(status=order_status)


class UpdateOrderStatusUseCase:
    """Update order status.

    Decisão B3(a): CONFIRMED/CANCELLED do pedido NÃO tocam estoque.
    O débito acontece na entrega DELIVERED (delivery_persistence_repository
    → deliver_stock_atomic) e a reversão no cancelamento da entrega pós-
    DELIVERED (reverse_delivery_stock_atomic).
    """

    def __init__(
        self, repository: OrderRepository, inventory_repo: Optional[InventoryRepository] = None, order_item_repo=None
    ):
        self.repository = repository
        self.inventory_repo = inventory_repo
        self.order_item_repo = order_item_repo

    def execute(self, codigo: str, status: str) -> Optional[Order]:
        order = self.repository.buscar_por_codigo(codigo)
        if not order:
            return None

        # Immutability check
        from app.domain.order.entity import TERMINAL_STATUSES

        if order.status in TERMINAL_STATUSES:
            raise ValueError(f"Pedido {codigo} está em status {order.status.value} e não pode ser alterado")

        try:
            order_status = OrderStatus(status)
        except ValueError as exc:
            raise ValueError(f"Status inválido: {status}") from exc

        # Decisão B3(a): nenhuma movimentação de estoque aqui.
        # CONFIRMED é apenas confirmação comercial; CANCELLED não devolve
        # nada porque nada foi debitado (o débito é na entrega DELIVERED).

        return self.repository.atualizar_status(codigo, order_status)

    def _deduct_stock(self, order: Order):
        """Deprecated (Decisão B3a): débito movido para a entrega DELIVERED.

        Mantido apenas como documentação da mudança — não é mais chamado.
        """
        raise NotImplementedError(
            "Débito de estoque agora acontece na entrega DELIVERED (deliver_stock_atomic) — Decisão B3(a)."
        )

    def _return_stock(self, order: Order):
        """Deprecated (Decisão B3a): reversão movida para o cancelamento da
        entrega (reverse_delivery_stock_atomic). Não é mais chamado.
        """
        raise NotImplementedError(
            "Reversão de estoque agora acontece no cancelamento da entrega "
            "pós-DELIVERED (reverse_delivery_stock_atomic) — Decisão B3(a)."
        )


class AssignDriverUseCase:
    def __init__(self, order_repo: OrderRepository, driver_repo=None):
        self.order_repo = order_repo
        self.driver_repo = driver_repo

    def execute(self, codigo: str, driver_codigo: str) -> Optional[Order]:
        order = self.order_repo.buscar_por_codigo(codigo)
        if not order:
            raise ValueError("Pedido não encontrado")

        from app.domain.order.entity import TERMINAL_STATUSES

        if order.status in TERMINAL_STATUSES:
            raise ValueError(f"Pedido {codigo} está em status {order.status.value} e não pode ser alterado")

        driver = self.driver_repo.buscar_por_codigo(driver_codigo)
        if not driver or not driver.ativo:
            raise ValueError("Entregador não encontrado ou inativo")

        return self.order_repo.atribuir_entregador(codigo, driver_codigo)
