"""
WhatsApp Repository — FASE 10

Interfaces for conversation and message persistence.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from app.domain.whatsapp.conversation import Conversation, ConversationMessage, ConversationState


class ConversationRepository(ABC):
    """Repository for WhatsApp conversations."""

    @abstractmethod
    def find_by_phone_and_account(self, customer_phone: str, account_id: str) -> Optional[Conversation]:
        """Find active conversation for a phone+account."""
        pass

    @abstractmethod
    def find_by_id(self, conversation_id: int) -> Optional[Conversation]:
        """Find conversation by ID."""
        pass

    @abstractmethod
    def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation."""
        pass

    @abstractmethod
    def update_state(self, conversation_id: int, state: ConversationState) -> bool:
        """Update conversation state."""
        pass

    @abstractmethod
    def update_customer(self, conversation_id: int, customer_codigo: str) -> bool:
        """Link a customer to a conversation."""
        pass

    @abstractmethod
    def list_active(
        self, account_id: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Conversation], int]:
        """List active conversations."""
        pass

    @abstractmethod
    def count_active(self, account_id: Optional[str] = None) -> int:
        """Count active conversations."""
        pass

    @abstractmethod
    def takeover(self, conversation_id: int, operator: str) -> bool:
        """Operator takes over conversation."""
        pass

    @abstractmethod
    def release_to_ai(self, conversation_id: int) -> bool:
        """Release conversation back to AI."""
        pass

    @abstractmethod
    def find_duplicate_message(self, provider_message_id: str) -> bool:
        """Check if message was already processed (idempotency)."""
        pass


class ConversationMessageRepository(ABC):
    """Repository for conversation messages."""

    @abstractmethod
    def create(self, message: ConversationMessage) -> ConversationMessage:
        """Persist a conversation message."""
        pass

    @abstractmethod
    def list_by_conversation(self, conversation_id: int, limit: int = 50, offset: int = 0) -> List[ConversationMessage]:
        """List messages for a conversation."""
        pass

    @abstractmethod
    def count_by_conversation(self, conversation_id: int) -> int:
        """Count messages in a conversation."""
        pass
