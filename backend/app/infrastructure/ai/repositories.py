"""
AI Repository Implementations — FASE 9
"""

import json
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.domain.ai.conversation import Conversation, Message, MessageRole
from app.domain.ai.repository import ConversationRepository, MessageRepository
from app.infrastructure.ai.models import ConversationModel, AIMessageModel


class SQLAlchemyConversationRepository(ConversationRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, m: ConversationModel) -> Conversation:
        return Conversation(
            id=m.id,
            external_id=m.external_id,
            title=m.title,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    def create(self, conversation: Conversation) -> Conversation:
        model = ConversationModel(
            external_id=conversation.external_id,
            title=conversation.title,
            created_at=conversation.created_at or datetime.utcnow(),
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_external_id(self, external_id: str) -> Optional[Conversation]:
        model = self.db.query(ConversationModel).filter(ConversationModel.external_id == external_id).first()
        if not model:
            return None
        conv = self._to_entity(model)
        # Load messages
        msg_models = (
            self.db.query(AIMessageModel)
            .filter(AIMessageModel.conversation_id == external_id)
            .order_by(AIMessageModel.created_at)
            .all()
        )
        conv.messages = [self._message_to_entity(m) for m in msg_models]
        return conv

    def list_all(self, limit: int = 50) -> List[Conversation]:
        models = self.db.query(ConversationModel).order_by(ConversationModel.created_at.desc()).limit(limit).all()
        return [self._to_entity(m) for m in models]

    def _message_to_entity(self, m: AIMessageModel) -> Message:
        return Message(
            id=m.id,
            conversation_id=m.conversation_id,
            role=MessageRole(m.role),
            content=m.content,
            metadata=json.loads(m.metadata_json) if m.metadata_json else {},
            created_at=m.created_at,
        )


class SQLAlchemyMessageRepository(MessageRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, message: Message) -> Message:
        model = AIMessageModel(
            conversation_id=message.conversation_id,
            role=message.role.value,
            content=message.content,
            metadata_json=json.dumps(message.metadata) if message.metadata else None,
            created_at=message.created_at or datetime.utcnow(),
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return Message(
            id=model.id,
            conversation_id=model.conversation_id,
            role=MessageRole(model.role),
            content=model.content,
            created_at=model.created_at,
        )

    def list_by_conversation(self, conversation_id: str, limit: int = 50) -> List[Message]:
        models = (
            self.db.query(AIMessageModel)
            .filter(AIMessageModel.conversation_id == conversation_id)
            .order_by(AIMessageModel.created_at.desc())
            .limit(limit)
            .all()
        )
        models.reverse()
        return [
            Message(
                id=m.id,
                conversation_id=m.conversation_id,
                role=MessageRole(m.role),
                content=m.content,
                created_at=m.created_at,
            )
            for m in models
        ]
