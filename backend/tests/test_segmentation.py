"""
CRM Segmentation Tests — FASE 13.1

Tests for rule evaluation, AND/OR logic, edge cases, and tenant isolation.
"""

import pytest
from app.domain.segmentation.entity import (
    Segment,
    SegmentRule,
    RuleField,
    RuleOperator,
    SegmentStatus,
)


# ── Rule Evaluation Tests ────────────────────────────────


class TestSegmentRuleEvaluation:
    """Test individual rule evaluation against customer metrics."""

    def test_numeric_greater_than(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_THAN, value=5)
        assert rule.evaluate({"total_orders": 10}) is True
        assert rule.evaluate({"total_orders": 5}) is False
        assert rule.evaluate({"total_orders": 3}) is False

    def test_numeric_less_than(self):
        rule = SegmentRule(field=RuleField.TOTAL_SPENT, operator=RuleOperator.LESS_THAN, value=1000)
        assert rule.evaluate({"total_spent": 500}) is True
        assert rule.evaluate({"total_spent": 1000}) is False
        assert rule.evaluate({"total_spent": 1500}) is False

    def test_numeric_equals(self):
        rule = SegmentRule(field=RuleField.AVERAGE_TICKET, operator=RuleOperator.EQUALS, value=50.0)
        assert rule.evaluate({"average_ticket": 50.0}) is True
        assert rule.evaluate({"average_ticket": 50.1}) is False

    def test_numeric_not_equals(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.NOT_EQUALS, value=0)
        assert rule.evaluate({"total_orders": 5}) is True
        assert rule.evaluate({"total_orders": 0}) is False

    def test_numeric_greater_or_equal(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_OR_EQUAL, value=10)
        assert rule.evaluate({"total_orders": 10}) is True
        assert rule.evaluate({"total_orders": 11}) is True
        assert rule.evaluate({"total_orders": 9}) is False

    def test_numeric_less_or_equal(self):
        rule = SegmentRule(field=RuleField.DAYS_SINCE_LAST_ORDER, operator=RuleOperator.LESS_OR_EQUAL, value=30)
        assert rule.evaluate({"days_since_last_order": 30}) is True
        assert rule.evaluate({"days_since_last_order": 29}) is True
        assert rule.evaluate({"days_since_last_order": 31}) is False

    def test_string_equals(self):
        rule = SegmentRule(field=RuleField.CLIENT_TYPE, operator=RuleOperator.EQUALS, value="RESTAURANT")
        assert rule.evaluate({"client_type": "RESTAURANT"}) is True
        assert rule.evaluate({"client_type": "restaurant"}) is True  # Case insensitive
        assert rule.evaluate({"client_type": "COMPANY"}) is False

    def test_string_not_equals(self):
        rule = SegmentRule(field=RuleField.CLIENT_TYPE, operator=RuleOperator.NOT_EQUALS, value="OTHER")
        assert rule.evaluate({"client_type": "COMPANY"}) is True
        assert rule.evaluate({"client_type": "OTHER"}) is False

    def test_string_contains(self):
        rule = SegmentRule(field=RuleField.FAVORITE_PRODUCT, operator=RuleOperator.CONTAINS, value="P13")
        assert rule.evaluate({"favorite_product": "Gás P13"}) is True
        assert rule.evaluate({"favorite_product": "Água 20L"}) is False

    def test_string_not_contains(self):
        rule = SegmentRule(field=RuleField.FAVORITE_PRODUCT, operator=RuleOperator.NOT_CONTAINS, value="Água")
        assert rule.evaluate({"favorite_product": "Gás P13"}) is True
        assert rule.evaluate({"favorite_product": "Água 20L"}) is False

    def test_boolean_is_true(self):
        rule = SegmentRule(field=RuleField.IS_ACTIVE, operator=RuleOperator.IS_TRUE)
        assert rule.evaluate({"is_active": True}) is True
        assert rule.evaluate({"is_active": False}) is False
        assert rule.evaluate({"is_active": 1}) is True

    def test_boolean_is_false(self):
        rule = SegmentRule(field=RuleField.HAS_EMAIL, operator=RuleOperator.IS_FALSE)
        assert rule.evaluate({"has_email": False}) is True
        assert rule.evaluate({"has_email": True}) is False
        assert rule.evaluate({"has_email": ""}) is True


# ── Edge Cases ───────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_customer_no_orders(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_THAN, value=0)
        assert rule.evaluate({"total_orders": 0}) is False

    def test_customer_one_order(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_OR_EQUAL, value=1)
        assert rule.evaluate({"total_orders": 1}) is True

    def test_customer_many_orders(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_THAN, value=100)
        assert rule.evaluate({"total_orders": 500}) is True

    def test_zero_value(self):
        rule = SegmentRule(field=RuleField.TOTAL_SPENT, operator=RuleOperator.EQUALS, value=0)
        assert rule.evaluate({"total_spent": 0}) is True

    def test_none_field_value(self):
        rule = SegmentRule(field=RuleField.DAYS_SINCE_LAST_ORDER, operator=RuleOperator.GREATER_THAN, value=30)
        assert rule.evaluate({"days_since_last_order": None}) is False

    def test_missing_field(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_THAN, value=5)
        assert rule.evaluate({}) is False

    def test_none_value_for_boolean(self):
        rule = SegmentRule(field=RuleField.IS_ACTIVE, operator=RuleOperator.IS_FALSE)
        assert rule.evaluate({"is_active": None}) is True

    def test_payment_status_pending(self):
        rule = SegmentRule(field=RuleField.PAYMENT_STATUS, operator=RuleOperator.EQUALS, value="PENDING")
        assert rule.evaluate({"payment_status": "PENDING"}) is True
        assert rule.evaluate({"payment_status": "PAID"}) is False

    def test_order_frequency(self):
        rule = SegmentRule(field=RuleField.ORDER_FREQUENCY, operator=RuleOperator.GREATER_THAN, value=2.0)
        assert rule.evaluate({"order_frequency": 3.5}) is True
        assert rule.evaluate({"order_frequency": 1.0}) is False


# ── AND/OR Logic Tests ───────────────────────────────────


class TestSegmentLogic:
    """Test AND/OR rule composition."""

    def test_and_all_match(self):
        segment = Segment(
            name="High Value Active",
            rules=[
                SegmentRule(field=RuleField.TOTAL_SPENT, operator=RuleOperator.GREATER_THAN, value=1000),
                SegmentRule(field=RuleField.IS_ACTIVE, operator=RuleOperator.IS_TRUE),
            ],
            rule_logic="AND",
        )
        assert segment.evaluate_customer({"total_spent": 2000, "is_active": True}) is True

    def test_and_one_fails(self):
        segment = Segment(
            name="High Value Active",
            rules=[
                SegmentRule(field=RuleField.TOTAL_SPENT, operator=RuleOperator.GREATER_THAN, value=1000),
                SegmentRule(field=RuleField.IS_ACTIVE, operator=RuleOperator.IS_TRUE),
            ],
            rule_logic="AND",
        )
        assert segment.evaluate_customer({"total_spent": 2000, "is_active": False}) is False

    def test_or_one_matches(self):
        segment = Segment(
            name="VIP or Restaurant",
            rules=[
                SegmentRule(field=RuleField.TOTAL_SPENT, operator=RuleOperator.GREATER_THAN, value=5000),
                SegmentRule(field=RuleField.CLIENT_TYPE, operator=RuleOperator.EQUALS, value="RESTAURANT"),
            ],
            rule_logic="OR",
        )
        assert segment.evaluate_customer({"total_spent": 200, "client_type": "RESTAURANT"}) is True

    def test_or_none_match(self):
        segment = Segment(
            name="VIP or Restaurant",
            rules=[
                SegmentRule(field=RuleField.TOTAL_SPENT, operator=RuleOperator.GREATER_THAN, value=5000),
                SegmentRule(field=RuleField.CLIENT_TYPE, operator=RuleOperator.EQUALS, value="RESTAURANT"),
            ],
            rule_logic="OR",
        )
        assert segment.evaluate_customer({"total_spent": 200, "client_type": "COMPANY"}) is False

    def test_empty_rules_returns_false(self):
        segment = Segment(name="Empty", rules=[], rule_logic="AND")
        assert segment.evaluate_customer({"total_orders": 10}) is False

    def test_single_rule(self):
        segment = Segment(
            name="Single",
            rules=[SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_THAN, value=5)],
            rule_logic="AND",
        )
        assert segment.evaluate_customer({"total_orders": 10}) is True
        assert segment.evaluate_customer({"total_orders": 3}) is False


# ── Serialization Tests ──────────────────────────────────


class TestSerialization:
    """Test rule and segment serialization."""

    def test_rule_to_dict(self):
        rule = SegmentRule(field=RuleField.TOTAL_ORDERS, operator=RuleOperator.GREATER_THAN, value=5)
        d = rule.to_dict()
        assert d["field"] == "total_orders"
        assert d["operator"] == "greater_than"
        assert d["value"] == 5

    def test_rule_from_dict(self):
        d = {"field": "total_spent", "operator": "less_than", "value": 1000}
        rule = SegmentRule.from_dict(d)
        assert rule.field == RuleField.TOTAL_SPENT
        assert rule.operator == RuleOperator.LESS_THAN
        assert rule.value == 1000

    def test_segment_to_dict(self):
        segment = Segment(
            id=1,
            name="Test",
            rules=[SegmentRule(field=RuleField.IS_ACTIVE, operator=RuleOperator.IS_TRUE)],
            rule_logic="AND",
            status=SegmentStatus.ACTIVE,
        )
        d = segment.to_dict()
        assert d["id"] == 1
        assert d["name"] == "Test"
        assert len(d["rules"]) == 1
        assert d["status"] == "ACTIVE"

    def test_invalid_field_raises(self):
        with pytest.raises(ValueError):
            SegmentRule(field="invalid_field", operator=RuleOperator.EQUALS, value=1)

    def test_invalid_operator_raises(self):
        with pytest.raises(ValueError):
            SegmentRule(field=RuleField.TOTAL_ORDERS, operator="invalid_op", value=1)
