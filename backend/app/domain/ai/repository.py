"""
AI Repository Interfaces — FASE 9
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from app.domain.ai.conversation import Conversation, Message


class ConversationRepository(ABC):
    @abstractmethod
    def create(self, conversation: Conversation) -> Conversation: ...

    @abstractmethod
    def get_by_external_id(self, external_id: str) -> Optional[Conversation]: ...

    @abstractmethod
    def list_all(self, limit: int = 50) -> List[Conversation]: ...


class MessageRepository(ABC):
    @abstractmethod
    def create(self, message: Message) -> Message: ...

    @abstractmethod
    def list_by_conversation(self, conversation_id: str, limit: int = 50) -> List[Message]: ...
