"""
Communication Templates — Customer Notification System

Templates for WhatsApp/SMS notifications based on delivery events.
Each template is configurable per tenant.

Rules:
  - IA can enhance templates but cannot replace them
  - Fallback: IA → Smart Template → Default Template
  - Cooldown: max 1 message per event type per delivery
  - Never invent: location, ETA, price, payment status
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import uuid


class CommunicationChannel(str, Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    PUSH = "PUSH"


class CommunicationEvent(str, Enum):
    PROXIMITY = "PROXIMITY"           # Driver near customer
    ARRIVAL = "ARRIVAL"               # Driver arrived
    CUSTOMER_ABSENT = "CUSTOMER_ABSENT"  # Customer not found
    ADDRESS_DIFFICULTY = "ADDRESS_DIFFICULTY"  # Hard to find address
    DELAY = "DELAY"                   # Delivery delayed
    POST_DELIVERY = "POST_DELIVERY"   # After delivery completed
    PAYMENT_REMINDER = "PAYMENT_REMINDER"  # Payment pending
    HELP_REQUEST = "HELP_REQUEST"     # Driver needs help


@dataclass
class MessageTemplate:
    """A communication template."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event: CommunicationEvent = CommunicationEvent.PROXIMITY
    channel: CommunicationChannel = CommunicationChannel.WHATSAPP
    subject: str = ""
    body: str = ""
    variables: List[str] = field(default_factory=list)  # e.g., [customer_name, driver_name]
    enabled: bool = True
    cooldown_minutes: int = 30  # Min time between same event messages
    require_event: bool = True  # Only send on real events

    def render(self, context: Dict[str, str]) -> str:
        """Render template with context variables."""
        result = self.body
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event": self.event.value,
            "channel": self.channel.value,
            "subject": self.subject,
            "body": self.body,
            "variables": self.variables,
            "enabled": self.enabled,
            "cooldown_minutes": self.cooldown_minutes,
        }


# ── Default Templates ────────────────────────────────────

DEFAULT_TEMPLATES = {
    CommunicationEvent.PROXIMITY: MessageTemplate(
        event=CommunicationEvent.PROXIMITY,
        subject="Entregador próximo",
        body=(
            "Olá, {customer_name}! O entregador da {company_name} "
            "já está próximo do seu endereço. "
            "Se puder sinalizar para ele, agradecemos!"
        ),
        variables=["customer_name", "company_name"],
        cooldown_minutes=30,
    ),
    CommunicationEvent.ARRIVAL: MessageTemplate(
        event=CommunicationEvent.ARRIVAL,
        subject="Entregador chegou",
        body=(
            "Olá, {customer_name}! O entregador acabou de chegar "
            "ao local da entrega do pedido #{order_code}."
        ),
        variables=["customer_name", "order_code"],
        cooldown_minutes=60,
    ),
    CommunicationEvent.CUSTOMER_ABSENT: MessageTemplate(
        event=CommunicationEvent.CUSTOMER_ABSENT,
        subject="Cliente não localizado",
        body=(
            "Olá, {customer_name}! Nosso entregador está no endereço "
            "da entrega e não conseguiu localizar você. "
            "Pode nos retornar por aqui, por favor?"
        ),
        variables=["customer_name"],
        cooldown_minutes=15,
    ),
    CommunicationEvent.ADDRESS_DIFFICULTY: MessageTemplate(
        event=CommunicationEvent.ADDRESS_DIFFICULTY,
        subject="Dificuldade com endereço",
        body=(
            "Olá, {customer_name}! Nosso entregador está com dificuldade "
            "para localizar o endereço do pedido #{order_code}. "
            "Pode nos enviar um ponto de referência?"
        ),
        variables=["customer_name", "order_code"],
        cooldown_minutes=15,
    ),
    CommunicationEvent.DELAY: MessageTemplate(
        event=CommunicationEvent.DELAY,
        subject="Atraso na entrega",
        body=(
            "Olá, {customer_name}! Tivemos um pequeno atraso "
            "na entrega do seu pedido. Agradecemos a paciência!"
        ),
        variables=["customer_name"],
        cooldown_minutes=60,
    ),
    CommunicationEvent.POST_DELIVERY: MessageTemplate(
        event=CommunicationEvent.POST_DELIVERY,
        subject="Entrega realizada",
        body=(
            "Obrigado pela preferência, {customer_name}! "
            "Seu pedido foi entregue com sucesso. "
            "Qualquer dúvida, estamos à disposição!"
        ),
        variables=["customer_name"],
        cooldown_minutes=1440,  # 24h
    ),
    CommunicationEvent.PAYMENT_REMINDER: MessageTemplate(
        event=CommunicationEvent.PAYMENT_REMINDER,
        subject="Lembrete de pagamento",
        body=(
            "Olá, {customer_name}! Identificamos que o pagamento "
            "do pedido #{order_code} ainda está pendente. "
            "Valor: R$ {amount}. "
            "{payment_instructions}"
        ),
        variables=["customer_name", "order_code", "amount", "payment_instructions"],
        cooldown_minutes=120,
    ),
}


@dataclass
class CommunicationPolicy:
    """Tenant-specific communication policy."""
    tenant_id: str = ""
    enabled_events: List[CommunicationEvent] = field(default_factory=lambda: list(CommunicationEvent))
    channels: Dict[CommunicationEvent, CommunicationChannel] = field(default_factory=dict)
    custom_templates: Dict[CommunicationEvent, MessageTemplate] = field(default_factory=dict)
    # Cooldown tracking: {(delivery_id, event): last_sent_timestamp}
    cooldowns: Dict[str, float] = field(default_factory=dict)

    def get_template(self, event: CommunicationEvent) -> MessageTemplate:
        """Get template for event (custom or default)."""
        if event in self.custom_templates:
            return self.custom_templates[event]
        return DEFAULT_TEMPLATES.get(event, MessageTemplate(event=event, body=""))

    def is_enabled(self, event: CommunicationEvent) -> bool:
        return event in self.enabled_events

    def check_cooldown(self, delivery_id: str, event: CommunicationEvent) -> bool:
        """Check if message can be sent (not in cooldown)."""
        key = f"{delivery_id}:{event.value}"
        import time
        last_sent = self.cooldowns.get(key, 0)
        template = self.get_template(event)
        return (time.time() - last_sent) >= (template.cooldown_minutes * 60)

    def record_sent(self, delivery_id: str, event: CommunicationEvent):
        """Record that a message was sent."""
        import time
        key = f"{delivery_id}:{event.value}"
        self.cooldowns[key] = time.time()

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "enabled_events": [e.value for e in self.enabled_events],
            "templates": {
                e.value: t.to_dict() for e, t in self.custom_templates.items()
            },
        }


# ── Communication Service ────────────────────────────────

class CommunicationService:
    """
    Handles customer notifications based on delivery events.

    Flow:
      Event → Policy Check → Template Render → Channel Send → Record

    Rules:
      - Never invent data
      - Cooldown prevents spam
      - Fallback: IA → Smart Template → Default Template
    """

    def __init__(self):
        self._policies: Dict[str, CommunicationPolicy] = {}
        self._history: List[Dict] = []

    def get_policy(self, tenant_id: str) -> CommunicationPolicy:
        """Get or create policy for tenant."""
        if tenant_id not in self._policies:
            self._policies[tenant_id] = CommunicationPolicy(tenant_id=tenant_id)
        return self._policies[tenant_id]

    def should_send(self, tenant_id: str, delivery_id: str,
                    event: CommunicationEvent) -> bool:
        """Check if message should be sent."""
        policy = self.get_policy(tenant_id)
        if not policy.is_enabled(event):
            return False
        if not policy.check_cooldown(delivery_id, event):
            return False
        return True

    def render_message(self, tenant_id: str, event: CommunicationEvent,
                       context: Dict[str, str]) -> str:
        """Render message template with context."""
        policy = self.get_policy(tenant_id)
        template = policy.get_template(event)
        return template.render(context)

    def record_communication(self, tenant_id: str, delivery_id: str,
                            event: CommunicationEvent, channel: CommunicationChannel,
                            message: str, status: str = "QUEUED"):
        """Record a communication attempt."""
        import uuid
        record = {
            "communication_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "delivery_id": delivery_id,
            "event": event.value,
            "channel": channel.value,
            "message": message,
            "status": status,
            "created_at": __import__('datetime').datetime.utcnow().isoformat(),
        }
        self._history.append(record)

        # Record cooldown
        policy = self.get_policy(tenant_id)
        policy.record_sent(delivery_id, event)

        return record

    def get_history(self, tenant_id: str, delivery_id: Optional[str] = None,
                   limit: int = 50) -> List[Dict]:
        """Get communication history."""
        records = [r for r in self._history if r["tenant_id"] == tenant_id]
        if delivery_id:
            records = [r for r in records if r["delivery_id"] == delivery_id]
        return records[-limit:]


# ── Singleton ────────────────────────────────────────────

_communication_service = CommunicationService()


def get_communication_service() -> CommunicationService:
    return _communication_service
