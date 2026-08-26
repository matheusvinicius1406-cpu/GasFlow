"""
WhatsApp Domain Entities — Entidades de negócio do WhatsApp.

Regras de Negócio:
- Cada conversa é identificada pelo número de telefone
- Conversa pode estar vinculada a um cliente cadastrado
- Fluxo do bot: idle → product → quantity → address → payment → order
- Mensagens são persistentes (nunca apagadas)
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ConversationStatus(str, Enum):
    """Status possíveis de uma conversa WhatsApp."""
    IDLE = "idle"
    AWAITING_PRODUCT = "awaiting_product"
    AWAITING_QUANTITY = "awaiting_quantity"
    AWAITING_ADDRESS_CONFIRM = "awaiting_address_confirm"
    AWAITING_PAYMENT = "awaiting_payment"
    ORDER_PLACED = "order_placed"


class MessageDirection(str, Enum):
    """Direção da mensagem."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class WhatsAppMessage:
    """Entidade de domínio da Mensagem WhatsApp."""

    conversation_id: int
    direction: MessageDirection
    content: Optional[str] = None
    message_type: str = "text"

    id: Optional[int] = None
    raw_payload: Optional[str] = None
    status: str = "received"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    @property
    def is_inbound(self) -> bool:
        return self.direction == MessageDirection.INBOUND

    @property
    def is_outbound(self) -> bool:
        return self.direction == MessageDirection.OUTBOUND


@dataclass
class WhatsAppConversation:
    """Entidade de domínio da Conversa WhatsApp."""

    phone_number: str
    status: ConversationStatus = ConversationStatus.IDLE

    id: Optional[int] = None
    client_codigo: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def definir_produto(self, product_codigo: str):
        """Salva o produto selecionado no contexto da conversa."""
        self.last_message = f"product:{product_codigo}"
        self.status = ConversationStatus.AWAITING_QUANTITY
        self.updated_at = datetime.utcnow()

    def definir_quantidade(self, product_codigo: str, quantity: int):
        """Salva a quantidade no contexto da conversa."""
        self.last_message = f"product:{product_codigo}:qty:{quantity}"
        self.status = ConversationStatus.AWAITING_ADDRESS_CONFIRM
        self.updated_at = datetime.utcnow()

    def confirmar_endereco(self):
        """Confirma endereço e pede pagamento."""
        self.status = ConversationStatus.AWAITING_PAYMENT
        self.updated_at = datetime.utcnow()

    def pedido_realizado(self):
        """Marca que o pedido foi realizado."""
        self.status = ConversationStatus.ORDER_PLACED
        self.last_message = None
        self.updated_at = datetime.utcnow()

    def resetar(self):
        """Reseta a conversa para o estado inicial."""
        self.status = ConversationStatus.IDLE
        self.last_message = None
        self.updated_at = datetime.utcnow()

    def obter_produto_codigo(self) -> Optional[str]:
        """Extrai o código do produto do contexto."""
        if self.last_message and self.last_message.startswith("product:"):
            return self.last_message.split(":")[1]
        return None

    def obter_quantidade(self) -> int:
        """Extrai a quantidade do contexto."""
        if self.last_message and "qty:" in self.last_message:
            parts = self.last_message.split(":")
            if len(parts) >= 4:
                return int(parts[3])
        return 1
