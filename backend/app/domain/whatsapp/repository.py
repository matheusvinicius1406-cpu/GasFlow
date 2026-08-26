"""
WhatsApp Repository Interface — Interface de repositório do WhatsApp.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from app.domain.whatsapp.entity import WhatsAppConversation, WhatsAppMessage


class WhatsAppRepository(ABC):
    """Interface abstrata para repositório de WhatsApp."""

    # ── Conversas ──────────────────────────────────────────

    @abstractmethod
    def buscar_conversa_por_telefone(self, phone_number: str) -> Optional[WhatsAppConversation]:
        """Busca uma conversa pelo número de telefone."""
        ...

    @abstractmethod
    def criar_conversa(self, conversation: WhatsAppConversation) -> WhatsAppConversation:
        """Cria uma nova conversa."""
        ...

    @abstractmethod
    def atualizar_conversa(self, conversation: WhatsAppConversation) -> WhatsAppConversation:
        """Atualiza os dados de uma conversa."""
        ...

    # ── Mensagens ──────────────────────────────────────────

    @abstractmethod
    def salvar_mensagem(self, message: WhatsAppMessage) -> WhatsAppMessage:
        """Salva uma mensagem na conversa."""
        ...

    @abstractmethod
    def listar_mensagens(self, conversation_id: int, limit: int = 50) -> List[WhatsAppMessage]:
        """Lista as mensagens de uma conversa."""
        ...

    # ── Clientes ───────────────────────────────────────────

    @abstractmethod
    def buscar_cliente_por_telefone(self, phone_number: str) -> Optional[str]:
        """Busca o código do cliente vinculado ao telefone."""
        ...
