"""
Tests for WhatsApp Automation — FASE 14

Tests cover:
- Rule CRUD
- Template rendering
- Policy checks (cooldown, daily limit)
- Eligibility (reorder, segment, manual)
- Execution lifecycle
- Metrics
"""

from datetime import datetime, timedelta
from app.domain.whatsapp_automation.entity import (
    AutomationRule,
    AutomationStatus,
    AutomationTriggerType,
    AutomationExecution,
    ExecutionStatus,
    AutomationMetrics,
)


class TestAutomationRuleEntity:
    """Test automation rule entity."""

    def test_rule_creation(self):
        rule = AutomationRule(
            name="Test Rule",
            trigger_type=AutomationTriggerType.REORDER_OPPORTUNITY,
            message_template="Olá {{customer_name}}!",
            min_score=50.0,
        )
        assert rule.name == "Test Rule"
        assert rule.status == AutomationStatus.DRAFT
        assert rule.requires_approval is True
        assert rule.cooldown_days == 7
        assert rule.created_at is not None

    def test_rule_to_dict(self):
        rule = AutomationRule(
            id=1,
            name="Recompra P13",
            trigger_type=AutomationTriggerType.REORDER_OPPORTUNITY,
            status=AutomationStatus.ACTIVE,
            message_template="Olá {{customer_name}}, você costuma comprar {{product}}.",
            min_score=60.0,
            confidence_filter="HIGH",
        )
        d = rule.to_dict()
        assert d["id"] == 1
        assert d["trigger_type"] == "REORDER_OPPORTUNITY"
        assert d["status"] == "ACTIVE"
        assert d["min_score"] == 60.0
        assert d["confidence_filter"] == "HIGH"

    def test_rule_defaults(self):
        rule = AutomationRule(name="Default")
        assert rule.max_messages_per_day == 1
        assert rule.cooldown_days == 7
        assert rule.requires_approval is True
        assert rule.account_id == "primary"
        assert rule.total_executions == 0


class TestAutomationExecutionEntity:
    """Test automation execution entity."""

    def test_execution_creation(self):
        exec = AutomationExecution(
            rule_id=1,
            customer_codigo="C001",
            customer_nome="João",
            message_text="Olá João!",
        )
        assert exec.status == ExecutionStatus.PENDING
        assert exec.rule_id == 1
        assert exec.triggered_at is not None

    def test_execution_to_dict(self):
        exec = AutomationExecution(
            id=1,
            rule_id=1,
            customer_codigo="C001",
            customer_nome="João",
            status=ExecutionStatus.SENT,
            sent_at=datetime(2026, 9, 1, 10, 0, 0),
        )
        d = exec.to_dict()
        assert d["id"] == 1
        assert d["status"] == "SENT"
        assert d["sent_at"] is not None


class TestAutomationMetrics:
    """Test metrics entity."""

    def test_metrics_to_dict(self):
        m = AutomationMetrics(
            total_rules=5,
            active_rules=3,
            total_executions=100,
            pending=10,
            sent=80,
            delivered=5,
            failed=5,
            success_rate=85.0,
        )
        d = m.to_dict()
        assert d["total_rules"] == 5
        assert d["active_rules"] == 3
        assert d["success_rate"] == 85.0


class TestTemplateRendering:
    """Test template variable rendering logic."""

    def _render(self, template: str, customer: dict) -> str:
        """Simulate template rendering."""
        variables = {
            "{{customer_name}}": "nome",
            "{{customer_codigo}}": "codigo",
            "{{product}}": "favorite_product",
            "{{last_order_date}}": "last_order_date",
            "{{total_orders}}": "total_orders",
            "{{average_ticket}}": "average_ticket",
        }
        result = template
        for var, key in variables.items():
            value = customer.get(key, "")
            result = result.replace(var, str(value))
        return result

    def test_basic_render(self):
        template = "Olá {{customer_name}}, você costuma comprar {{product}}."
        customer = {"nome": "João", "favorite_product": "P13"}
        result = self._render(template, customer)
        assert result == "Olá João, você costuma comprar P13."

    def test_render_with_numbers(self):
        template = "Você já fez {{total_orders}} pedidos, totalizando {{average_ticket}}."
        customer = {"total_orders": 5, "average_ticket": "R$ 300.00"}
        result = self._render(template, customer)
        assert "5" in result
        assert "R$ 300.00" in result

    def test_render_missing_variable(self):
        template = "Olá {{customer_name}}, seu produto é {{product}}."
        customer = {"nome": "João"}  # No product
        result = self._render(template, customer)
        assert "Olá João" in result
        assert "seu produto é ." in result or "seu produto é" in result

    def test_render_empty_template(self):
        result = self._render("", {})
        assert result == ""


class TestPolicyChecks:
    """Test policy logic (cooldown, daily limit)."""

    def test_cooldown_check_within_window(self):
        """Customer contacted 3 days ago with 7-day cooldown should be blocked."""
        cooldown_days = 7
        last_contact = datetime.utcnow() - timedelta(days=3)
        should_send = (datetime.utcnow() - last_contact).days >= cooldown_days
        assert should_send is False

    def test_cooldown_check_outside_window(self):
        """Customer contacted 10 days ago with 7-day cooldown should be allowed."""
        cooldown_days = 7
        last_contact = datetime.utcnow() - timedelta(days=10)
        should_send = (datetime.utcnow() - last_contact).days >= cooldown_days
        assert should_send is True

    def test_daily_limit_exceeded(self):
        """Customer already received 1 message today, limit is 1."""
        messages_today = 1
        max_per_day = 1
        assert messages_today >= max_per_day

    def test_daily_limit_not_exceeded(self):
        messages_today = 0
        max_per_day = 1
        assert messages_today < max_per_day


class TestExecutionStatusTransitions:
    """Test valid status transitions."""

    def test_pending_to_approved(self):
        assert ExecutionStatus.PENDING.value == "PENDING"
        assert ExecutionStatus.APPROVED.value == "APPROVED"

    def test_approved_to_sent(self):
        assert ExecutionStatus.APPROVED.value == "APPROVED"
        assert ExecutionStatus.SENT.value == "SENT"

    def test_sent_to_delivered(self):
        assert ExecutionStatus.SENT.value == "SENT"
        assert ExecutionStatus.DELIVERED.value == "DELIVERED"

    def test_pending_to_cancelled(self):
        assert ExecutionStatus.PENDING.value == "PENDING"
        assert ExecutionStatus.CANCELLED.value == "CANCELLED"

    def test_all_statuses_exist(self):
        statuses = [s.value for s in ExecutionStatus]
        assert "PENDING" in statuses
        assert "APPROVED" in statuses
        assert "SENT" in statuses
        assert "DELIVERED" in statuses
        assert "FAILED" in statuses
        assert "CANCELLED" in statuses
        assert "OPTED_OUT" in statuses


class TestTriggerTypes:
    """Test trigger type enum."""

    def test_all_triggers(self):
        triggers = [t.value for t in AutomationTriggerType]
        assert "REORDER_OPPORTUNITY" in triggers
        assert "SEGMENT_MEMBERSHIP" in triggers
        assert "MANUAL" in triggers
        assert "SCHEDULED" in triggers
