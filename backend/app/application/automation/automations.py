"""
Business Automations — FASE 12

Pre-built automation recipes:
1. Low Stock Alert
2. Receivable Overdue Reminder
3. Customer Inactive Reactivation
4. Order Completion Follow-up
5. Payment Confirmation

Each automation has: trigger → condition → action → idempotency → audit → failure handling.
"""

from app.domain.automation.events import EventType
from app.domain.automation.workflows import WorkflowDefinition, WorkflowStepDef, WorkflowStatus
from app.domain.automation.policy import PolicyEngine, RiskLevel, ActionPolicy


# ── Automation Recipes ──────────────────────────────────

def create_low_stock_workflow() -> WorkflowDefinition:
    """InventoryLow → detect → alert operator."""
    return WorkflowDefinition(
        name="Low Stock Alert",
        description="Alerts operator when inventory drops below minimum",
        trigger_type="EVENT_TRIGGER",
        trigger_event=EventType.INVENTORY_LOW.value,
        steps=[
            WorkflowStepDef(
                id="check_stock", name="Check stock details",
                action_type="tool_call", tool_name="get_inventory",
                arguments={"product_codigo": "{{event.payload.product_codigo}}"},
                next_step_on_success="alert",
            ),
            WorkflowStepDef(
                id="alert", name="Alert operator",
                action_type="notification",
                arguments={"message": "Estoque baixo para {{check_stock.product_codigo}}: {{check_stock.quantity}} unidades"},
                risk_level="LOW",
            ),
        ],
        status=WorkflowStatus.ACTIVE,
    )


def create_receivable_overdue_workflow() -> WorkflowDefinition:
    """ReceivableOverdue → lookup → draft → approve → send."""
    return WorkflowDefinition(
        name="Receivable Overdue Reminder",
        description="Sends payment reminder for overdue receivables",
        trigger_type="EVENT_TRIGGER",
        trigger_event=EventType.RECEIVABLE_OVERDUE.value,
        steps=[
            WorkflowStepDef(
                id="lookup_customer", name="Lookup customer",
                action_type="tool_call", tool_name="get_customer",
                arguments={"customer_codigo": "{{event.payload.customer_codigo}}"},
                next_step_on_success="draft_message",
            ),
            WorkflowStepDef(
                id="draft_message", name="Draft reminder message",
                action_type="notification",
                arguments={"message": "Olá {{lookup_customer.nome}}, você tem um pedido pendente. Por favor, regularize."},
                next_step_on_success="approval",
            ),
            WorkflowStepDef(
                id="approval", name="Approve sending",
                action_type="approval_request",
                arguments={"action": "send_reminder", "risk": "MEDIUM"},
                requires_approval=True, risk_level="MEDIUM",
                next_step_on_success="send",
            ),
            WorkflowStepDef(
                id="send", name="Send via WhatsApp",
                action_type="tool_call", tool_name="send_whatsapp",
                arguments={"phone": "{{lookup_customer.telefone}}", "message": "{{draft_message.message}}"},
                risk_level="MEDIUM",
            ),
        ],
        status=WorkflowStatus.ACTIVE,
    )


def create_customer_reactivation_workflow() -> WorkflowDefinition:
    """CustomerInactive → lookup → 360 → draft → approve → send."""
    return WorkflowDefinition(
        name="Customer Reactivation",
        description="Re-engages inactive customers with personalized message",
        trigger_type="EVENT_TRIGGER",
        trigger_event=EventType.CUSTOMER_INACTIVE.value,
        steps=[
            WorkflowStepDef(
                id="lookup", name="Lookup customer",
                action_type="tool_call", tool_name="get_customer_360",
                arguments={"customer_codigo": "{{event.payload.customer_codigo}}"},
                next_step_on_success="draft",
            ),
            WorkflowStepDef(
                id="draft", name="Draft reactivation message",
                action_type="notification",
                arguments={"message": "Olá {{lookup.nome}}! Sentimos sua falta. Temos novidades para você."},
                next_step_on_success="approval",
            ),
            WorkflowStepDef(
                id="approval", name="Approve sending",
                action_type="approval_request",
                arguments={"action": "send_reactivation", "risk": "MEDIUM"},
                requires_approval=True, risk_level="MEDIUM",
                next_step_on_success="send",
            ),
            WorkflowStepDef(
                id="send", name="Send via WhatsApp",
                action_type="tool_call", tool_name="send_whatsapp",
                arguments={"phone": "{{lookup.telefone}}", "message": "{{draft.message}}"},
                risk_level="MEDIUM",
            ),
        ],
        status=WorkflowStatus.ACTIVE,
    )


def create_order_completion_workflow() -> WorkflowDefinition:
    """OrderDelivered → follow-up → draft → send."""
    return WorkflowDefinition(
        name="Order Completion Follow-up",
        description="Sends follow-up message after order delivery",
        trigger_type="EVENT_TRIGGER",
        trigger_event=EventType.ORDER_DELIVERED.value,
        steps=[
            WorkflowStepDef(
                id="lookup_order", name="Lookup order",
                action_type="tool_call", tool_name="get_order",
                arguments={"order_codigo": "{{event.payload.order_codigo}}"},
                next_step_on_success="draft",
            ),
            WorkflowStepDef(
                id="draft", name="Draft follow-up",
                action_type="notification",
                arguments={"message": "Pedido {{event.payload.order_codigo}} entregue! Obrigado pela preferência."},
            ),
        ],
        status=WorkflowStatus.ACTIVE,
    )


def create_payment_confirmation_workflow() -> WorkflowDefinition:
    """PaymentReceived → confirm → notify."""
    return WorkflowDefinition(
        name="Payment Confirmation",
        description="Confirms payment receipt to customer",
        trigger_type="EVENT_TRIGGER",
        trigger_event=EventType.PAYMENT_RECEIVED.value,
        steps=[
            WorkflowStepDef(
                id="confirm", name="Confirm payment",
                action_type="tool_call", tool_name="get_payments",
                arguments={"order_codigo": "{{event.payload.order_codigo}}"},
                next_step_on_success="notify",
            ),
            WorkflowStepDef(
                id="notify", name="Notify customer",
                action_type="notification",
                arguments={"message": "Pagamento confirmado para o pedido {{event.payload.order_codigo}}. Obrigado!"},
            ),
        ],
        status=WorkflowStatus.ACTIVE,
    )


def register_default_policies(policy_engine: PolicyEngine):
    """Register default action policies."""
    policies = [
        ActionPolicy(action="get_customer", risk_level=RiskLevel.LOW, description="Read customer"),
        ActionPolicy(action="get_order", risk_level=RiskLevel.LOW, description="Read order"),
        ActionPolicy(action="get_inventory", risk_level=RiskLevel.LOW, description="Read inventory"),
        ActionPolicy(action="get_payments", risk_level=RiskLevel.LOW, description="Read payments"),
        ActionPolicy(action="get_financial_summary", risk_level=RiskLevel.LOW, description="Read finance"),
        ActionPolicy(action="search_products", risk_level=RiskLevel.LOW, description="Search products"),
        ActionPolicy(action="get_customer_360", risk_level=RiskLevel.LOW, description="Customer 360"),
        ActionPolicy(action="get_low_stock", risk_level=RiskLevel.LOW, description="Low stock"),
        ActionPolicy(action="get_inventory_summary", risk_level=RiskLevel.LOW, description="Inventory summary"),
        ActionPolicy(action="get_receivables", risk_level=RiskLevel.LOW, description="Read receivables"),
        ActionPolicy(action="get_sales_summary", risk_level=RiskLevel.LOW, description="Sales summary"),
        ActionPolicy(action="create_order", risk_level=RiskLevel.MEDIUM, requires_approval=True,
                     description="Create order"),
        ActionPolicy(action="add_stock", risk_level=RiskLevel.HIGH, requires_approval=True,
                     description="Add stock"),
        ActionPolicy(action="register_payment", risk_level=RiskLevel.HIGH, requires_approval=True,
                     description="Register payment"),
        ActionPolicy(action="send_whatsapp", risk_level=RiskLevel.MEDIUM, requires_approval=True,
                     description="Send WhatsApp message"),
        ActionPolicy(action="send_reactivation", risk_level=RiskLevel.MEDIUM, requires_approval=True,
                     description="Send reactivation"),
    ]
    for p in policies:
        policy_engine.register_policy(p)


def create_default_agents(agent_engine):
    """Register default agents."""
    agent_engine.create_default_agents()
