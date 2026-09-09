"""
Order Domain Entity — Entidade de negócio do Pedido.

FASE 3.2 — SECURITY + FINANCIAL HARDENING:
- Imutabilidade pós-DELIVERED/CANCELLED
- Validação de desconto (>= 0 AND <= subtotal)
- Total não pode ser negativo
- Transições de status validadas

Regras de Negócio:
- Todo pedido pertence a um cliente
- Todo pedido possui código único
- Status segue o fluxo: PENDING → CONFIRMED → PREPARING → DELIVERING → DELIVERED
- Pedido pode ser cancelado
- Nenhum pedido é apagado
- Preço é congelado no momento da criação (via OrderItem)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List


class OrderStatus(str, Enum):
    """Status possíveis de um pedido."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, Enum):
    """Status possíveis de pagamento."""

    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIAL = "PARTIAL"


class OrderSource(str, Enum):
    """Origem do pedido."""

    WHATSAPP = "WHATSAPP"
    PHONE = "PHONE"
    WEB = "WEB"
    COUNTER = "COUNTER"
    MANUAL = "MANUAL"
    API = "API"
    INTEGRATION = "INTEGRATION"  # importado de site de revenda (agente)


# Transições válidas de status
VALID_TRANSITIONS = {
    OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.CONFIRMED: [OrderStatus.PREPARING, OrderStatus.CANCELLED],
    OrderStatus.PREPARING: [OrderStatus.DELIVERING, OrderStatus.CANCELLED],
    OrderStatus.DELIVERING: [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED: [],  # Terminal — nenhuma transição
    OrderStatus.CANCELLED: [],  # Terminal — nenhuma transição
}

# Status terminais — pedido está imutável
TERMINAL_STATUSES = {OrderStatus.DELIVERED, OrderStatus.CANCELLED}


@dataclass
class Order:
    """Entidade de domínio do Pedido."""

    codigo: str
    client_codigo: str
    address_snapshot: str
    status: OrderStatus = OrderStatus.PENDING

    id: Optional[int] = None

    # Valores
    subtotal: float = 0.0
    delivery_fee: float = 0.0
    discount: float = 0.0
    total: float = 0.0

    # Pagamento
    payment_method: Optional[str] = None
    payment_status: PaymentStatus = PaymentStatus.PENDING

    # Entrega
    delivery_driver_codigo: Optional[str] = None

    # Metadados
    source: OrderSource = OrderSource.MANUAL
    notes: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Itens (carregados separadamente)
    items: List = field(default_factory=list)

    def __post_init__(self):
        """Validações de negócio após construção."""
        if not self.codigo or len(self.codigo) != 6:
            raise ValueError("Código do pedido deve ter 6 dígitos")
        if not self.client_codigo:
            raise ValueError("Código do cliente é obrigatório")
        if self.subtotal < 0:
            raise ValueError("Subtotal não pode ser negativo")
        if self.delivery_fee < 0:
            raise ValueError("Taxa de entrega não pode ser negativa")
        if self.discount < 0:
            raise ValueError("Desconto não pode ser negativo")

    def calcular_totais(self):
        """Recalcula totais baseado nos itens — único autoritário de cálculo."""
        self.subtotal = sum(item.subtotal or 0 for item in self.items)

        # Valida desconto
        if self.discount > self.subtotal:
            raise ValueError(f"Desconto (R$ {self.discount:.2f}) não pode exceder subtotal (R$ {self.subtotal:.2f})")

        self.total = self.subtotal + self.delivery_fee - self.discount

        # Total não pode ser negativo
        if self.total < 0:
            raise ValueError(f"Total (R$ {self.total:.2f}) não pode ser negativo")

    def _verificar_imutabilidade(self):
        """Verifica se o pedido pode ser alterado."""
        if self.status in TERMINAL_STATUSES:
            raise ValueError(f"Pedido {self.codigo} está em status {self.status.value} " f"e não pode ser alterado")

    def confirmar(self):
        """Confirma o pedido."""
        self._verificar_imutabilidade()
        self._transicionar_para(OrderStatus.CONFIRMED)

    def preparar(self):
        """Marca o pedido como preparando."""
        self._verificar_imutabilidade()
        self._transicionar_para(OrderStatus.PREPARING)

    def enviar(self):
        """Marca o pedido como em entrega."""
        self._verificar_imutabilidade()
        self._transicionar_para(OrderStatus.DELIVERING)

    def entregar(self):
        """Marca o pedido como entregue — estado terminal."""
        self._verificar_imutabilidade()
        self._transicionar_para(OrderStatus.DELIVERED)

    def cancelar(self):
        """Cancela o pedido — estado terminal."""
        self._verificar_imutabilidade()
        self._transicionar_para(OrderStatus.CANCELLED)

    def atribuir_entregador(self, driver_codigo: str):
        """Atribui um entregador ao pedido."""
        self._verificar_imutabilidade()
        self.delivery_driver_codigo = driver_codigo

    def _transicionar_para(self, novo_status: OrderStatus):
        """Transição segura de status com validação."""
        transicoes_validas = VALID_TRANSITIONS.get(self.status, [])
        if novo_status not in transicoes_validas:
            raise ValueError(
                f"Transição inválida: {self.status.value} → {novo_status.value}. "
                f"Status permitidos: {[s.value for s in transicoes_validas]}"
            )
        self.status = novo_status
        self.updated_at = datetime.utcnow()

    @property
    def resumo(self) -> str:
        """Resumo do pedido para exibição."""
        return (
            f"Pedido {self.codigo} | "
            f"Cliente: {self.client_codigo} | "
            f"Total: R$ {self.total:.2f} | "
            f"Status: {self.status.value}"
        )
