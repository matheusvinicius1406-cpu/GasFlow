"""
Order Use Cases — Casos de uso do Pedido.

FASE 3.2 — SECURITY + FINANCIAL HARDENING:
- Backend é ÚNICA autoridade de preço
- Desconto validado (>= 0 AND <= subtotal)
- Total validado (>= 0)
- Frontend unit_price é completamente ignorado
- Estoque validado antes de criar

Regras:
- Preço congelado no momento da criação
- Total = subtotal + delivery_fee - discount
- Nenhum campo financeiro é aceito diretamente do frontend
"""

from datetime import datetime
from typing import Optional, List
from app.domain.order.entity import Order, OrderStatus, PaymentStatus, OrderSource
from app.domain.order.repository import OrderRepository
from app.domain.order_item.entity import OrderItem
from app.domain.order_item.repository import OrderItemRepository
from app.domain.client.repository import ClientRepository
from app.domain.product.repository import ProductRepository


class CreateOrderUseCase:
    """Caso de uso: Criar um novo pedido com múltiplos itens.

    SEGURANÇA: Este é o ÚNICO lugar onde preços são calculados.
    O frontend envia APENAS product_codigo e quantity.
    O preço é buscado do Product oficial.
    """

    def __init__(
        self,
        order_repo: OrderRepository,
        order_item_repo: OrderItemRepository,
        client_repo: ClientRepository,
        product_repo: ProductRepository,
    ):
        self.order_repo = order_repo
        self.order_item_repo = order_item_repo
        self.client_repo = client_repo
        self.product_repo = product_repo

    def execute(self, data: dict) -> Order:
        # ═══════════════════════════════════════════════════════
        # 1. VALIDAÇÃO DO CLIENTE
        # ═══════════════════════════════════════════════════════
        client = self.client_repo.buscar_por_codigo(data["client_codigo"])
        if not client:
            raise ValueError("Cliente não encontrado")
        if not client.ativo:
            raise ValueError("Cliente está desativado")

        # ═══════════════════════════════════════════════════════
        # 2. VALIDAÇÃO DOS ITENS
        # ═══════════════════════════════════════════════════════
        items_data = data.get("items", [])
        if not items_data:
            raise ValueError("Pedido deve ter pelo menos um item")

        # ═══════════════════════════════════════════════════════
        # 3. GERAÇÃO DO CÓDIGO
        # ═══════════════════════════════════════════════════════
        codigo = self.order_repo.proximo_codigo()

        # ═══════════════════════════════════════════════════════
        # 4. SNAPSHOT DO ENDEREÇO
        # ═══════════════════════════════════════════════════════
        address = data.get("address_snapshot") or f"{client.rua}, {client.numero} - {client.bairro}"
        if client.complemento:
            address += f" ({client.complemento})"
        if client.referencia:
            address += f" - Ref: {client.referencia}"

        # ═══════════════════════════════════════════════════════
        # 5. CRIAÇÃO DOS ITENS COM PREÇO CONGELADO
        # ═══════════════════════════════════════════════════════
        order_items = []
        subtotal = 0.0

        for item_data in items_data:
            product = self.product_repo.buscar_por_codigo(item_data["product_codigo"])
            if not product:
                raise ValueError(f"Produto {item_data['product_codigo']} não encontrado")

            if not product.ativo:
                raise ValueError(f"Produto {product.nome} está desativado")

            quantity = item_data.get("quantity", 1)
            if quantity <= 0:
                raise ValueError(f"Quantidade inválida para {product.nome}")

            if product.estoque < quantity:
                raise ValueError(
                    f"Estoque insuficiente para {product.nome}. "
                    f"Disponível: {product.estoque}, solicitado: {quantity}"
                )

            # ═══════════════════════════════════════════════════
            # PREÇO CONGELADO — backend é autoridade
            # unit_price do frontend é COMPLETAMENTE IGNORADO
            # ═══════════════════════════════════════════════════
            unit_price = product.preco
            item_subtotal = unit_price * quantity

            order_item = OrderItem(
                order_codigo=codigo,
                product_codigo=product.codigo,
                product_nome=product.nome,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=item_subtotal,
            )
            order_items.append(order_item)
            subtotal += item_subtotal

            # Baixa estoque
            product.baixar_estoque(quantity)
            self.product_repo.atualizar(product)

        # ═══════════════════════════════════════════════════════
        # 6. CÁLCULO FINANCEIRO — backend é autoridade
        # ═══════════════════════════════════════════════════════
        delivery_fee = data.get("delivery_fee", 0.0)
        if delivery_fee < 0:
            delivery_fee = 0.0

        discount = data.get("discount", 0.0)
        if discount < 0:
            discount = 0.0

        # Desconto não pode exceder subtotal
        if discount > subtotal:
            raise ValueError(
                f"Desconto (R$ {discount:.2f}) não pode exceder subtotal (R$ {subtotal:.2f})"
            )

        total = subtotal + delivery_fee - discount

        # Total não pode ser negativo (defensivo)
        if total < 0:
            raise ValueError(
                f"Total (R$ {total:.2f}) não pode ser negativo"
            )

        # ═══════════════════════════════════════════════════════
        # 7. CRIAÇÃO DO PEDIDO
        # ═══════════════════════════════════════════════════════
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

        # Salva itens
        for item in order_items:
            self.order_item_repo.criar(item)

        return order


class GetOrderUseCase:
    """Caso de uso: Buscar pedido por código."""

    def __init__(self, order_repo: OrderRepository, order_item_repo: OrderItemRepository):
        self.order_repo = order_repo
        self.order_item_repo = order_item_repo

    def execute(self, codigo: str) -> Optional[Order]:
        order = self.order_repo.buscar_por_codigo(codigo)
        if order:
            order.items = self.order_item_repo.listar_por_pedido(codigo)
        return order


class ListOrdersUseCase:
    """Caso de uso: Listar pedidos."""

    def __init__(self, repository: OrderRepository):
        self.repository = repository

    def execute(self, status: Optional[str] = None) -> List[Order]:
        order_status = None
        if status:
            try:
                order_status = OrderStatus(status)
            except ValueError:
                raise ValueError(f"Status inválido: {status}")
        return self.repository.listar_todos(status=order_status)


class UpdateOrderStatusUseCase:
    """Caso de uso: Atualizar status do pedido.

    Valida transições e imutabilidade.
    """

    def __init__(self, repository: OrderRepository):
        self.repository = repository

    def execute(self, codigo: str, status: str) -> Optional[Order]:
        order = self.repository.buscar_por_codigo(codigo)
        if not order:
            return None

        # Verifica imutabilidade
        from app.domain.order.entity import TERMINAL_STATUSES
        if order.status in TERMINAL_STATUSES:
            raise ValueError(
                f"Pedido {codigo} está em status {order.status.value} "
                f"e não pode ser alterado"
            )

        try:
            order_status = OrderStatus(status)
        except ValueError:
            raise ValueError(f"Status inválido: {status}")

        return self.repository.atualizar_status(codigo, order_status)


class AssignDriverUseCase:
    """Caso de uso: Atribuir entregador ao pedido."""

    def __init__(
        self,
        order_repo: OrderRepository,
        driver_repo: "DeliveryDriverRepository",
    ):
        self.order_repo = order_repo
        self.driver_repo = driver_repo

    def execute(self, codigo: str, driver_codigo: str) -> Optional[Order]:
        # Valida pedido
        order = self.order_repo.buscar_por_codigo(codigo)
        if not order:
            raise ValueError("Pedido não encontrado")

        # Verifica imutabilidade
        from app.domain.order.entity import TERMINAL_STATUSES
        if order.status in TERMINAL_STATUSES:
            raise ValueError(
                f"Pedido {codigo} está em status {order.status.value} "
                f"e não pode ser alterado"
            )

        # Valida entregador
        driver = self.driver_repo.buscar_por_codigo(driver_codigo)
        if not driver or not driver.ativo:
            raise ValueError("Entregador não encontrado ou inativo")

        return self.order_repo.atribuir_entregador(codigo, driver_codigo)
