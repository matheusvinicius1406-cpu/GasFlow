"""
WhatsApp Conversation — FASE 10

State machine + memory for WhatsApp conversations.
Each conversation is isolated by (account_id, customer_phone).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class ConversationState(str, Enum):
    IDLE = "IDLE"
    BROWSING = "BROWSING"
    BUILDING_ORDER = "BUILDING_ORDER"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    ORDER_CREATED = "ORDER_CREATED"
    HUMAN_PENDING = "HUMAN_PENDING"
    HUMAN_ACTIVE = "HUMAN_ACTIVE"
    CLOSED = "CLOSED"


@dataclass
class ConversationMessage:
    """A single message in a conversation."""

    id: Optional[int] = None
    conversation_id: Optional[int] = None
    direction: str = "INCOMING"  # INCOMING / OUTGOING
    sender: str = ""  # "customer" / "assistant" / "system" / "human"
    content: str = ""
    message_type: str = "TEXT"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class ConversationDraft:
    """Order draft built during conversation."""

    customer_codigo: Optional[str] = None
    customer_name: Optional[str] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    delivery_fee: float = 0.0
    discount: float = 0.0
    notes: Optional[str] = None

    @property
    def subtotal(self) -> float:
        return sum(item.get("subtotal", 0) for item in self.items)

    @property
    def total(self) -> float:
        return self.subtotal + self.delivery_fee - self.discount

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_codigo": self.customer_codigo,
            "customer_name": self.customer_name,
            "items": self.items,
            "subtotal": self.subtotal,
            "delivery_fee": self.delivery_fee,
            "discount": self.discount,
            "total": self.total,
            "notes": self.notes,
        }


@dataclass
class Conversation:
    """WhatsApp conversation entity."""

    id: Optional[int] = None
    account_id: str = ""
    customer_phone: str = ""
    customer_codigo: Optional[str] = None
    state: ConversationState = ConversationState.IDLE
    draft: Optional[ConversationDraft] = None
    human_operator: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: List[ConversationMessage] = field(default_factory=list)

    def __post_init__(self):
        now = datetime.utcnow()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    @property
    def is_ai_active(self) -> bool:
        return self.state not in (
            ConversationState.HUMAN_ACTIVE,
            ConversationState.CLOSED,
        )

    def can_process_message(self) -> bool:
        """Whether AI should process incoming messages."""
        return self.state not in (
            ConversationState.HUMAN_ACTIVE,
            ConversationState.CLOSED,
        )

    def transition_to(self, new_state: ConversationState) -> bool:
        """Validate and apply state transition. Returns True if valid."""
        valid_transitions = {
            ConversationState.IDLE: [
                ConversationState.BROWSING,
                ConversationState.BUILDING_ORDER,
                ConversationState.HUMAN_PENDING,
                ConversationState.CLOSED,
            ],
            ConversationState.BROWSING: [
                ConversationState.BROWSING,
                ConversationState.BUILDING_ORDER,
                ConversationState.HUMAN_PENDING,
                ConversationState.CLOSED,
            ],
            ConversationState.BUILDING_ORDER: [
                ConversationState.BUILDING_ORDER,
                ConversationState.AWAITING_CONFIRMATION,
                ConversationState.ORDER_CREATED,
                ConversationState.BROWSING,
                ConversationState.HUMAN_PENDING,
                ConversationState.CLOSED,
            ],
            ConversationState.AWAITING_CONFIRMATION: [
                ConversationState.ORDER_CREATED,
                ConversationState.BUILDING_ORDER,
                ConversationState.BROWSING,
                ConversationState.HUMAN_PENDING,
                ConversationState.CLOSED,
            ],
            ConversationState.ORDER_CREATED: [
                ConversationState.BROWSING,
                ConversationState.BUILDING_ORDER,
                ConversationState.HUMAN_PENDING,
                ConversationState.CLOSED,
            ],
            ConversationState.HUMAN_PENDING: [
                ConversationState.HUMAN_ACTIVE,
                ConversationState.IDLE,
                ConversationState.CLOSED,
            ],
            ConversationState.HUMAN_ACTIVE: [
                ConversationState.IDLE,
                ConversationState.BROWSING,
                ConversationState.CLOSED,
            ],
            ConversationState.CLOSED: [
                ConversationState.IDLE,
            ],
        }
        allowed = valid_transitions.get(self.state, [])
        if new_state not in allowed:
            return False
        self.state = new_state
        self.updated_at = datetime.utcnow()
        return True
