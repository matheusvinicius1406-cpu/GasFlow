"""
WhatsApp Repositories — FASE 10

SQLAlchemy implementations for conversation and message persistence.
Uses the existing WhatsAppConversationModel and WhatsAppMessageModel.
"""

import json
from typing import Optional, List, Tuple
from datetime import datetime

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.domain.whatsapp.conversation import (
    Conversation,
    ConversationMessage,
    ConversationState,
    ConversationDraft,
)
from app.domain.whatsapp.repository import (
    ConversationRepository,
    ConversationMessageRepository,
)
from app.infrastructure.repositories.whatsapp_model import (
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)


class SQLAlchemyConversationRepository(ConversationRepository):
    """SQLAlchemy conversation repository."""

    def __init__(self, session: Session):
        self.session = session

    def find_by_phone_and_account(self, customer_phone: str, account_id: str) -> Optional[Conversation]:
        model = (
            self.session.query(WhatsAppConversationModel)
            .filter(
                and_(
                    WhatsAppConversationModel.phone_number == customer_phone,
                    WhatsAppConversationModel.account_id == account_id,
                    WhatsAppConversationModel.status.notin_(["CLOSED"]),
                )
            )
            .order_by(WhatsAppConversationModel.updated_at.desc())
            .first()
        )
        if not model:
            return None
        return self._to_domain(model)

    def find_by_id(self, conversation_id: int) -> Optional[Conversation]:
        model = self.session.get(WhatsAppConversationModel, conversation_id)
        if not model:
            return None
        return self._to_domain(model)

    def create(self, conversation: Conversation) -> Conversation:
        draft_json = None
        if conversation.draft:
            draft_json = json.dumps(conversation.draft.to_dict(), ensure_ascii=False)
        model = WhatsAppConversationModel(
            account_id=conversation.account_id,
            phone_number=conversation.customer_phone,
            client_codigo=conversation.customer_codigo,
            status=conversation.state.value,
            human_operator=conversation.human_operator,
            draft_json=draft_json,
            last_message="",
            last_message_at=datetime.utcnow(),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return self._to_domain(model)

    def update_state(self, conversation_id: int, state: ConversationState) -> bool:
        model = self.session.get(WhatsAppConversationModel, conversation_id)
        if not model:
            return False
        model.status = state.value
        model.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def update_customer(self, conversation_id: int, customer_codigo: str) -> bool:
        model = self.session.get(WhatsAppConversationModel, conversation_id)
        if not model:
            return False
        model.client_codigo = customer_codigo
        model.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def update_draft(self, conversation_id: int, draft: Optional[ConversationDraft]) -> bool:
        model = self.session.get(WhatsAppConversationModel, conversation_id)
        if not model:
            return False
        model.draft_json = json.dumps(draft.to_dict(), ensure_ascii=False) if draft else None
        model.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def list_active(
        self, account_id: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Conversation], int]:
        query = self.session.query(WhatsAppConversationModel).filter(
            WhatsAppConversationModel.status.notin_(["CLOSED"])
        )
        if account_id:
            query = query.filter(WhatsAppConversationModel.account_id == account_id)
        total = query.count()
        models = query.order_by(WhatsAppConversationModel.updated_at.desc()).offset(offset).limit(limit).all()
        return [self._to_domain(m) for m in models], total

    def count_active(self, account_id: Optional[str] = None) -> int:
        query = self.session.query(func.count(WhatsAppConversationModel.id)).filter(
            WhatsAppConversationModel.status.notin_(["CLOSED"])
        )
        if account_id:
            query = query.filter(WhatsAppConversationModel.account_id == account_id)
        return query.scalar() or 0

    def takeover(self, conversation_id: int, operator: str) -> bool:
        model = self.session.get(WhatsAppConversationModel, conversation_id)
        if not model:
            return False
        model.human_operator = operator
        model.status = ConversationState.HUMAN_ACTIVE.value
        model.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def release_to_ai(self, conversation_id: int) -> bool:
        model = self.session.get(WhatsAppConversationModel, conversation_id)
        if not model:
            return False
        model.human_operator = None
        model.status = ConversationState.IDLE.value
        model.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def find_duplicate_message(self, provider_message_id: str) -> bool:
        if not provider_message_id:
            return False
        exists_q = self.session.query(
            self.session.query(WhatsAppMessageModel)
            .filter(WhatsAppMessageModel.provider_message_id == provider_message_id)
            .exists()
        )
        return exists_q.scalar()

    def _to_domain(self, model: WhatsAppConversationModel) -> Conversation:
        draft = None
        if model.draft_json:
            try:
                draft_data = json.loads(model.draft_json)
                # Filter out computed properties from to_dict() that aren't valid constructor args
                valid_keys = {"customer_codigo", "customer_name", "items", "delivery_fee", "discount", "notes"}
                filtered = {k: v for k, v in draft_data.items() if k in valid_keys}
                draft = ConversationDraft(**filtered)
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            state = ConversationState(model.status)
        except ValueError:
            state = ConversationState.IDLE
        return Conversation(
            id=model.id,
            account_id=model.account_id,
            customer_phone=model.phone_number,
            customer_codigo=model.client_codigo,
            state=state,
            draft=draft,
            human_operator=model.human_operator,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SQLAlchemyConversationMessageRepository(ConversationMessageRepository):
    """SQLAlchemy message repository."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, message: ConversationMessage) -> ConversationMessage:
        model = WhatsAppMessageModel(
            conversation_id=message.conversation_id,
            provider_message_id=message.metadata.get("provider_message_id"),
            direction=message.direction,
            sender=message.sender,
            content=message.content,
            message_type=message.message_type,
            raw_payload=json.dumps(message.metadata, ensure_ascii=False) if message.metadata else None,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        message.id = model.id

        # Update conversation last_message
        conv = self.session.get(WhatsAppConversationModel, message.conversation_id)
        if conv:
            conv.last_message = message.content[:500] if message.content else None
            conv.last_message_at = datetime.utcnow()
            self.session.commit()

        return message

    def list_by_conversation(self, conversation_id: int, limit: int = 50, offset: int = 0) -> List[ConversationMessage]:
        models = (
            self.session.query(WhatsAppMessageModel)
            .filter(WhatsAppMessageModel.conversation_id == conversation_id)
            .order_by(WhatsAppMessageModel.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_domain(m) for m in models]

    def count_by_conversation(self, conversation_id: int) -> int:
        return (
            self.session.query(
                self.session.query(WhatsAppMessageModel)
                .filter(WhatsAppMessageModel.conversation_id == conversation_id)
                .exists()
            ).scalar()
            or 0
        )

    def _to_domain(self, model: WhatsAppMessageModel) -> ConversationMessage:
        metadata = {}
        if model.raw_payload:
            try:
                metadata = json.loads(model.raw_payload)
            except (json.JSONDecodeError, TypeError):
                pass
        return ConversationMessage(
            id=model.id,
            conversation_id=model.conversation_id,
            direction=model.direction,
            sender=model.sender,
            content=model.content or "",
            message_type=model.message_type,
            metadata=metadata,
            created_at=model.created_at,
        )
