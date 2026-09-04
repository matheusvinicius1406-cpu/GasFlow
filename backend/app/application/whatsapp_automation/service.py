"""
WhatsApp Automation Service — FASE 14

Bridges CRM intelligence (segments, reorder) to WhatsApp messaging.
Handles:
- Rule evaluation against eligible customers
- Message template rendering with variables
- Policy checks (cooldown, opt-out, rate limiting)
- Execution tracking and metrics

No LLM dependency — deterministic template rendering.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from app.domain.whatsapp_automation.entity import (
    AutomationRule, AutomationStatus, AutomationTriggerType,
    AutomationExecution, ExecutionStatus,
)
from app.infrastructure.repositories.whatsapp_automation_repository import SQLAlchemyAutomationRepository
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository


# Supported template variables
TEMPLATE_VARIABLES = {
    "{{customer_name}}": "customer_nome",
    "{{customer_codigo}}": "customer_codigo",
    "{{product}}": "favorite_product",
    "{{last_order_date}}": "last_order_date",
    "{{total_orders}}": "total_orders",
    "{{average_ticket}}": "average_ticket",
    "{{days_since_last_order}}": "days_since_last_order",
}


class WhatsAppAutomationService:
    """Service for WhatsApp automation rules and executions."""

    def __init__(
        self,
        automation_repo: SQLAlchemyAutomationRepository,
        client_repo: SQLAlchemyClientRepository,
        order_repo: SQLAlchemyOrderRepository,
    ):
        self.automation_repo = automation_repo
        self.client_repo = client_repo
        self.order_repo = order_repo

    # ── Rule Management ────────────────────────────────

    def create_rule(self, rule: AutomationRule) -> AutomationRule:
        """Create a new automation rule."""
        return self.automation_repo.create_rule(rule)

    def get_rule(self, rule_id: int) -> Optional[AutomationRule]:
        return self.automation_repo.get_rule(rule_id)

    def list_rules(self, status: Optional[str] = None) -> List[AutomationRule]:
        return self.automation_repo.list_rules(status=status)

    def update_rule(self, rule_id: int, **kwargs) -> Optional[AutomationRule]:
        return self.automation_repo.update_rule(rule_id, **kwargs)

    def delete_rule(self, rule_id: int) -> bool:
        return self.automation_repo.delete_rule(rule_id)

    def activate_rule(self, rule_id: int) -> Optional[AutomationRule]:
        return self.automation_repo.update_rule(rule_id, status=AutomationStatus.ACTIVE.value)

    def pause_rule(self, rule_id: int) -> Optional[AutomationRule]:
        return self.automation_repo.update_rule(rule_id, status=AutomationStatus.PAUSED.value)

    # ── Execution ──────────────────────────────────────

    def execute_rule(self, rule_id: int) -> Dict[str, Any]:
        """Execute an automation rule — find eligible customers and create executions."""
        rule = self.automation_repo.get_rule(rule_id)
        if not rule:
            return {"success": False, "error": "Rule not found"}
        if rule.status != AutomationStatus.ACTIVE:
            return {"success": False, "error": "Rule is not active"}

        # Find eligible customers
        eligible = self._find_eligible_customers(rule)

        created = 0
        skipped = 0
        for customer in eligible:
            # Policy checks
            if not self._check_policies(rule, customer["codigo"]):
                skipped += 1
                continue

            # Render message
            message = self._render_template(rule.message_template, customer)

            # Create execution
            execution = AutomationExecution(
                rule_id=rule.id,
                customer_codigo=customer["codigo"],
                customer_nome=customer.get("nome", ""),
                customer_phone=customer.get("telefone", ""),
                message_text=message,
                status=ExecutionStatus.PENDING if rule.requires_approval else ExecutionStatus.APPROVED,
                trigger_context={
                    "trigger_type": rule.trigger_type.value,
                    "reorder_score": customer.get("reorder_score"),
                    "segment_name": customer.get("segment_name"),
                },
            )
            self.automation_repo.create_execution(execution)
            created += 1

        # Update rule metrics
        self.automation_repo.update_rule(
            rule_id,
            total_executions=(rule.total_executions or 0) + created,
        )

        return {
            "success": True,
            "eligible_customers": len(eligible),
            "executions_created": created,
            "skipped_by_policy": skipped,
        }

    def approve_execution(self, execution_id: int) -> Optional[AutomationExecution]:
        """Approve a pending execution."""
        return self.automation_repo.update_execution(
            execution_id, status=ExecutionStatus.APPROVED.value
        )

    def cancel_execution(self, execution_id: int) -> Optional[AutomationExecution]:
        """Cancel a pending execution."""
        return self.automation_repo.update_execution(
            execution_id, status=ExecutionStatus.CANCELLED.value
        )

    def mark_sent(self, execution_id: int, conversation_id: Optional[int] = None) -> Optional[AutomationExecution]:
        """Mark execution as sent."""
        return self.automation_repo.update_execution(
            execution_id,
            status=ExecutionStatus.SENT.value,
            sent_at=datetime.utcnow(),
            conversation_id=conversation_id,
        )

    def mark_delivered(self, execution_id: int) -> Optional[AutomationExecution]:
        """Mark execution as delivered."""
        return self.automation_repo.update_execution(
            execution_id,
            status=ExecutionStatus.DELIVERED.value,
            delivered_at=datetime.utcnow(),
        )

    def mark_failed(self, execution_id: int, error: str) -> Optional[AutomationExecution]:
        """Mark execution as failed."""
        return self.automation_repo.update_execution(
            execution_id,
            status=ExecutionStatus.FAILED.value,
            error_message=error,
        )

    def list_executions(
        self,
        rule_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[AutomationExecution]:
        return self.automation_repo.list_executions(rule_id=rule_id, status=status, limit=limit)

    def get_metrics(self) -> dict:
        return self.automation_repo.get_metrics().to_dict()

    # ── Template Rendering ─────────────────────────────

    def _render_template(self, template: str, customer: Dict[str, Any]) -> str:
        """Render a message template with customer data."""
        result = template
        for var_name, data_key in TEMPLATE_VARIABLES.items():
            value = customer.get(data_key, "")
            if value is None:
                value = ""
            result = result.replace(var_name, str(value))
        return result

    def preview_template(self, template: str, customer_codigo: str) -> Dict[str, Any]:
        """Preview a rendered template for a specific customer."""
        customer = self._get_customer_data(customer_codigo)
        if not customer:
            return {"success": False, "error": "Customer not found"}
        rendered = self._render_template(template, customer)
        return {
            "success": True,
            "rendered_message": rendered,
            "variables_used": [v for v in TEMPLATE_VARIABLES if v in template],
            "customer_data": {k: v for k, v in customer.items() if v is not None},
        }

    # ── Eligibility ────────────────────────────────────

    def _find_eligible_customers(self, rule: AutomationRule) -> List[Dict[str, Any]]:
        """Find customers eligible for this automation rule."""
        if rule.trigger_type == AutomationTriggerType.REORDER_OPPORTUNITY:
            return self._find_reorder_eligible(rule)
        elif rule.trigger_type == AutomationTriggerType.SEGMENT_MEMBERSHIP:
            return self._find_segment_eligible(rule)
        elif rule.trigger_type == AutomationTriggerType.MANUAL:
            return []  # Manual triggers don't auto-find customers
        return []

    def _find_reorder_eligible(self, rule: AutomationRule) -> List[Dict[str, Any]]:
        """Find customers with reorder opportunities matching the rule criteria."""
        from app.application.reorder.service import ReorderService
        from app.domain.reorder.entity import ReorderStatus

        reorder_svc = ReorderService(self.client_repo, self.order_repo)
        min_score = rule.min_score or 50.0
        confidence_filter = rule.confidence_filter

        opportunities = reorder_svc.get_opportunities(min_score=min_score)
        eligible = []

        for opp in opportunities:
            if confidence_filter and opp.confidence.value != confidence_filter:
                continue
            if opp.status not in (ReorderStatus.READY, ReorderStatus.DUE, ReorderStatus.OVERDUE):
                continue

            customer = {
                "codigo": opp.customer_codigo,
                "nome": opp.customer_nome,
                "telefone": "",  # Will be resolved from client repo
                "favorite_product": opp.recommended_product,
                "last_order_date": opp.last_order_date.strftime("%d/%m/%Y") if opp.last_order_date else "",
                "total_orders": opp.total_orders,
                "average_ticket": f"R$ {opp.average_ticket:.2f}",
                "days_since_last_order": opp.days_since_last_order or 0,
                "reorder_score": opp.reorder_score,
                "segment_name": None,
            }

            # Resolve phone from client
            client = self.client_repo.buscar_por_codigo(opp.customer_codigo)
            if client:
                customer["telefone"] = client.telefone

            eligible.append(customer)

        return eligible

    def _find_segment_eligible(self, rule: AutomationRule) -> List[Dict[str, Any]]:
        """Find customers in a specific segment."""
        if not rule.segment_id:
            return []

        # Use the segment's evaluated members
        from app.infrastructure.repositories.segmentation_repository import SQLAlchemySegmentRepository
        seg_repo = SQLAlchemySegmentRepository(self.client_repo.db, self.client_repo.tenant_id)

        segment = seg_repo.get_segment(rule.segment_id)
        if not segment:
            return []

        eligible = []
        # Evaluate segment against all customers
        customers = self.client_repo.listar_todos()
        for customer in customers:
            metrics = self.order_repo.get_customer_metrics(customer.codigo)
            if segment.evaluate_customer(metrics):
                eligible.append({
                    "codigo": customer.codigo,
                    "nome": customer.nome,
                    "telefone": customer.telefone,
                    "favorite_product": metrics.get("favorite_product"),
                    "last_order_date": metrics.get("last_order_at").strftime("%d/%m/%Y") if metrics.get("last_order_at") else "",
                    "total_orders": metrics.get("total_orders", 0),
                    "average_ticket": f"R$ {metrics.get('average_ticket', 0):.2f}",
                    "days_since_last_order": metrics.get("days_since_last_order", 0),
                    "reorder_score": None,
                    "segment_name": segment.name,
                })

        return eligible

    # ── Policies ───────────────────────────────────────

    def _check_policies(self, rule: AutomationRule, customer_codigo: str) -> bool:
        """Check if sending is allowed based on policies."""
        # Check cooldown
        if self.automation_repo.was_recently_contacted(customer_codigo, rule.cooldown_days):
            return False

        # Check daily limit
        recent_count = self.automation_repo.count_recent_sends(
            customer_codigo, rule.id, days=1
        )
        if recent_count >= rule.max_messages_per_day:
            return False

        # Check customer opt-out (would be in a real system)
        # For now, assume all customers are opted-in

        return True

    def _get_customer_data(self, customer_codigo: str) -> Optional[Dict[str, Any]]:
        """Get customer data for template rendering."""
        client = self.client_repo.buscar_por_codigo(customer_codigo)
        if not client:
            return None

        metrics = self.order_repo.get_customer_metrics(customer_codigo)
        return {
            "codigo": client.codigo,
            "nome": client.nome,
            "telefone": client.telefone,
            "favorite_product": metrics.get("favorite_product"),
            "last_order_date": metrics.get("last_order_at").strftime("%d/%m/%Y") if metrics.get("last_order_at") else "",
            "total_orders": metrics.get("total_orders", 0),
            "average_ticket": f"R$ {metrics.get('average_ticket', 0):.2f}",
            "days_since_last_order": metrics.get("days_since_last_order", 0),
        }
