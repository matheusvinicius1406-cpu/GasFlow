"""
Conversation Domain — FASE 9

Short-term conversation memory + persistence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CONFIRMATION = "confirmation"


@dataclass
class Message:
    id: Optional[int] = None
    conversation_id: str = ""
    role: MessageRole = MessageRole.USER
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class Conversation:
    id: Optional[int] = None
    external_id: str = ""  # UUID for API
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: List[Message] = field(default_factory=list)

    def add_message(self, role: MessageRole, content: str, **metadata):
        msg = Message(
            conversation_id=self.external_id,
            role=role,
            content=content,
            metadata=metadata,
            created_at=datetime.utcnow(),
        )
        self.messages.append(msg)
        return msg
