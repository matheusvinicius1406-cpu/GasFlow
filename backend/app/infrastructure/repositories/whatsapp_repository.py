"""
WhatsApp Repository Implementation — Implementação SQLAlchemy do repositório de WhatsApp.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.domain.whatsapp.entity import (
    WhatsAppConversation,
    WhatsAppMessage,
    ConversationStatus,
    MessageDirection,
)
from app.domain.whatsapp.repository import WhatsAppRepository
from app.infrastructure.repositories.whatsapp_model import (
from app.infrastructure.repositories.tenant_mixin import TenantMixin
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)


class SQLAlchemyWhatsAppRepository(WhatsAppRepository):
    """Implementação do repositório de WhatsApp usando SQLAlchemy."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    # ── Conversas ──────────────────────────────────────────

    def _to_conversation_entity(self, model: WhatsAppConversationModel) -> WhatsAppConversation:
        return WhatsAppConversation(
            id=model.id,
            phone_number=model.phone_number,
            client_codigo=model.client_codigo,
            status=ConversationStatus(model.status),
            last_message=model.last_message,
            last_message_at=model.last_message_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_conversation_model(self, entity: WhatsAppConversation) -> WhatsAppConversationModel:
        if entity.id:
            model = self._filter_by_tenant(WhatsAppConversationModel).filter(
                WhatsAppConversationModel.id == entity.id
            ).first()
            if model:
                model.phone_number = entity.phone_number
                model.client_codigo = entity.client_codigo
                model.status = entity.status.value
                model.last_message = entity.last_message
                model.last_message_at = entity.last_message_at
                return model

        return WhatsAppConversationModel(
            phone_number=entity.phone_number,
            client_codigo=entity.client_codigo,
            status=entity.status.value,
            last_message=entity.last_message,
            last_message_at=entity.last_message_at,
        )

    def buscar_conversa_por_telefone(self, phone_number: str) -> Optional[WhatsAppConversation]:
        model = self._filter_by_tenant(WhatsAppConversationModel).filter(
            WhatsAppConversationModel.phone_number == phone_number
        ).first()
        return self._to_conversation_entity(model) if model else None

    def criar_conversa(self, conversation: WhatsAppConversation) -> WhatsAppConversation:
        model = self._to_conversation_model(conversation)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_conversation_entity(model)

    def atualizar_conversa(self, conversation: WhatsAppConversation) -> WhatsAppConversation:
        model = self._to_conversation_model(conversation)
        self.db.commit()
        self.db.refresh(model)
        return self._to_conversation_entity(model)

    # ── Mensagens ──────────────────────────────────────────

    def _to_message_entity(self, model: WhatsAppMessageModel) -> WhatsAppMessage:
        return WhatsAppMessage(
            id=model.id,
            conversation_id=model.conversation_id,
            direction=MessageDirection(model.direction),
            content=model.content,
            message_type=model.message_type,
            raw_payload=model.raw_payload,
            status=model.status,
            created_at=model.created_at,
        )

    def salvar_mensagem(self, message: WhatsAppMessage) -> WhatsAppMessage:
        model = WhatsAppMessageModel(
            conversation_id=message.conversation_id,
            direction=message.direction.value,
            content=message.content,
            message_type=message.message_type,
            raw_payload=message.raw_payload,
            status=message.status,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_message_entity(model)

    def listar_mensagens(self, conversation_id: int, limit: int = 50) -> List[WhatsAppMessage]:
        models = self._filter_by_tenant(WhatsAppMessageModel).filter(
            WhatsAppMessageModel.conversation_id == conversation_id
        ).order_by(WhatsAppMessageModel.created_at.desc()).limit(limit).all()
        return [self._to_message_entity(m) for m in reversed(models)]

    # ── Clientes ───────────────────────────────────────────

    def buscar_cliente_por_telefone(self, phone_number: str) -> Optional[str]:
        from app.infrastructure.repositories.client_model import ClientModel
        client = self._filter_by_tenant(ClientModel).filter(ClientModel.telefone == phone_number).first()
        return client.codigo if client else None
