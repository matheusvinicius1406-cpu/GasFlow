"""
WhatsApp Automation Repository — FASE 14

CRUD for automation rules and executions.
Tenant-scoped for security.
"""

from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.domain.whatsapp_automation.entity import (
    AutomationRule, AutomationStatus, AutomationTriggerType,
    AutomationExecution, ExecutionStatus, AutomationMetrics,
)
from app.infrastructure.repositories.whatsapp_automation_model import (
    AutomationRuleModel, AutomationExecutionModel,
)


class SQLAlchemyAutomationRepository:
    """Repository for automation rules and executions."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    # ── Rules ──────────────────────────────────────────

    def create_rule(self, rule: AutomationRule) -> AutomationRule:
        model = AutomationRuleModel(
            tenant_id=self.tenant_id,
            name=rule.name,
            description=rule.description,
            trigger_type=rule.trigger_type.value,
            status=rule.status.value,
            segment_id=rule.segment_id,
            min_score=rule.min_score,
            confidence_filter=rule.confidence_filter,
            message_template=rule.message_template,
            account_id=rule.account_id,
            max_messages_per_day=rule.max_messages_per_day,
            cooldown_days=rule.cooldown_days,
            requires_approval=rule.requires_approval,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._rule_to_entity(model)

    def get_rule(self, rule_id: int) -> Optional[AutomationRule]:
        model = self.db.query(AutomationRuleModel).filter(
            AutomationRuleModel.id == rule_id,
            AutomationRuleModel.tenant_id == self.tenant_id,
        ).first()
        return self._rule_to_entity(model) if model else None

    def list_rules(self, status: Optional[str] = None) -> List[AutomationRule]:
        query = self.db.query(AutomationRuleModel).filter(
            AutomationRuleModel.tenant_id == self.tenant_id,
        )
        if status:
            query = query.filter(AutomationRuleModel.status == status)
        models = query.order_by(AutomationRuleModel.id.desc()).all()
        return [self._rule_to_entity(m) for m in models]

    def update_rule(self, rule_id: int, **kwargs) -> Optional[AutomationRule]:
        model = self.db.query(AutomationRuleModel).filter(
            AutomationRuleModel.id == rule_id,
            AutomationRuleModel.tenant_id == self.tenant_id,
        ).first()
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        model.updated_at = func.now() if hasattr(func, 'now') else None
        self.db.commit()
        self.db.refresh(model)
        return self._rule_to_entity(model)

    def delete_rule(self, rule_id: int) -> bool:
        model = self.db.query(AutomationRuleModel).filter(
            AutomationRuleModel.id == rule_id,
            AutomationRuleModel.tenant_id == self.tenant_id,
        ).first()
        if not model:
            return False
        self.db.delete(model)
        self.db.commit()
        return True

    # ── Executions ─────────────────────────────────────

    def create_execution(self, execution: AutomationExecution) -> AutomationExecution:
        model = AutomationExecutionModel(
            tenant_id=self.tenant_id,
            rule_id=execution.rule_id,
            customer_codigo=execution.customer_codigo,
            customer_nome=execution.customer_nome,
            customer_phone=execution.customer_phone,
            message_text=execution.message_text,
            status=execution.status.value,
            error_message=execution.error_message,
            conversation_id=execution.conversation_id,
            trigger_context=execution.trigger_context,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._execution_to_entity(model)

    def update_execution(self, execution_id: int, **kwargs) -> Optional[AutomationExecution]:
        model = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.id == execution_id,
            AutomationExecutionModel.tenant_id == self.tenant_id,
        ).first()
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        self.db.commit()
        self.db.refresh(model)
        return self._execution_to_entity(model)

    def list_executions(
        self,
        rule_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[AutomationExecution]:
        query = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
        )
        if rule_id:
            query = query.filter(AutomationExecutionModel.rule_id == rule_id)
        if status:
            query = query.filter(AutomationExecutionModel.status == status)
        models = query.order_by(AutomationExecutionModel.id.desc()).limit(limit).all()
        return [self._execution_to_entity(m) for m in models]

    def count_recent_sends(self, customer_codigo: str, rule_id: int, days: int = 1) -> int:
        """Count recent sends to a customer for a specific rule (cooldown check)."""
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
            AutomationExecutionModel.rule_id == rule_id,
            AutomationExecutionModel.customer_codigo == customer_codigo,
            AutomationExecutionModel.status.in_([ExecutionStatus.SENT.value, ExecutionStatus.DELIVERED.value]),
            AutomationExecutionModel.sent_at >= cutoff,
        ).count()
        return count

    def was_recently_contacted(self, customer_codigo: str, cooldown_days: int = 7) -> bool:
        """Check if customer was recently contacted by any automation."""
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=cooldown_days)
        count = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
            AutomationExecutionModel.customer_codigo == customer_codigo,
            AutomationExecutionModel.status.in_([ExecutionStatus.SENT.value, ExecutionStatus.DELIVERED.value]),
            AutomationExecutionModel.sent_at >= cutoff,
        ).count()
        return count > 0

    def get_metrics(self) -> AutomationMetrics:
        """Get aggregate metrics."""
        total_rules = self.db.query(AutomationRuleModel).filter(
            AutomationRuleModel.tenant_id == self.tenant_id,
        ).count()
        active_rules = self.db.query(AutomationRuleModel).filter(
            AutomationRuleModel.tenant_id == self.tenant_id,
            AutomationRuleModel.status == AutomationStatus.ACTIVE.value,
        ).count()
        total_executions = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
        ).count()
        pending = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
            AutomationExecutionModel.status == ExecutionStatus.PENDING.value,
        ).count()
        sent = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
            AutomationExecutionModel.status == ExecutionStatus.SENT.value,
        ).count()
        delivered = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
            AutomationExecutionModel.status == ExecutionStatus.DELIVERED.value,
        ).count()
        failed = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
            AutomationExecutionModel.status == ExecutionStatus.FAILED.value,
        ).count()
        opted_out = self.db.query(AutomationExecutionModel).filter(
            AutomationExecutionModel.tenant_id == self.tenant_id,
            AutomationExecutionModel.status == ExecutionStatus.OPTED_OUT.value,
        ).count()

        success_rate = 0.0
        if total_executions > 0:
            success_rate = round((sent + delivered) / total_executions * 100, 1)

        return AutomationMetrics(
            total_rules=total_rules,
            active_rules=active_rules,
            total_executions=total_executions,
            pending=pending,
            sent=sent,
            delivered=delivered,
            failed=failed,
            opted_out=opted_out,
            success_rate=success_rate,
        )

    # ── Private helpers ────────────────────────────────

    def _rule_to_entity(self, model: AutomationRuleModel) -> AutomationRule:
        return AutomationRule(
            id=model.id,
            name=model.name,
            description=model.description,
            trigger_type=AutomationTriggerType(model.trigger_type),
            status=AutomationStatus(model.status),
            segment_id=model.segment_id,
            min_score=model.min_score,
            confidence_filter=model.confidence_filter,
            message_template=model.message_template,
            account_id=model.account_id,
            max_messages_per_day=model.max_messages_per_day,
            cooldown_days=model.cooldown_days,
            requires_approval=model.requires_approval,
            total_executions=model.total_executions or 0,
            successful_sends=model.successful_sends or 0,
            failed_sends=model.failed_sends or 0,
            opted_out_count=model.opted_out_count or 0,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _execution_to_entity(self, model: AutomationExecutionModel) -> AutomationExecution:
        return AutomationExecution(
            id=model.id,
            rule_id=model.rule_id,
            customer_codigo=model.customer_codigo,
            customer_nome=model.customer_nome,
            customer_phone=model.customer_phone,
            message_text=model.message_text,
            status=ExecutionStatus(model.status),
            error_message=model.error_message,
            conversation_id=model.conversation_id,
            triggered_at=model.triggered_at,
            sent_at=model.sent_at,
            delivered_at=model.delivered_at,
            trigger_context=model.trigger_context,
            created_at=model.created_at,
        )
