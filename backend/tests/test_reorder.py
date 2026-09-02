"""
Tests for Reorder Intelligence Engine — FASE 13.2

Tests cover:
- Score calculation
- Confidence levels
- Status classification
- Interval calculation
- Edge cases (no orders, single order, many orders)
- Coefficient of variation
"""

import pytest
from datetime import datetime, timedelta
from app.domain.reorder.entity import ReorderOpportunity, ReorderStatus, ConfidenceLevel, ReorderSummary
from app.application.reorder.service import (
    ReorderService, WEIGHT_RECENCY, WEIGHT_FREQUENCY, WEIGHT_REGULARITY, WEIGHT_PRODUCT,
    HIGH_CONFIDENCE_MIN_ORDERS, MEDIUM_CONFIDENCE_MIN_ORDERS,
    LOW_CV_THRESHOLD, MEDIUM_CV_THRESHOLD,
)


class TestReorderStatus:
    """Test status classification."""

    def test_status_ready(self):
        svc = ReorderService.__new__(ReorderService)
        # 70% of interval = READY (ratio < 0.8)
        assert svc._determine_status(21, 30) == ReorderStatus.READY

    def test_status_due(self):
        svc = ReorderService.__new__(ReorderService)
        # 100% of interval = DUE
        assert svc._determine_status(30, 30) == ReorderStatus.DUE

    def test_status_overdue(self):
        svc = ReorderService.__new__(ReorderService)
        # 150% of interval = OVERDUE
        assert svc._determine_status(45, 30) == ReorderStatus.OVERDUE

    def test_status_dormant(self):
        svc = ReorderService.__new__(ReorderService)
        # 200%+ of interval = DORMANT
        assert svc._determine_status(60, 30) == ReorderStatus.DORMANT

    def test_status_no_interval_many_days(self):
        svc = ReorderService.__new__(ReorderService)
        # No interval data, many days = DORMANT
        assert svc._determine_status(60, None) == ReorderStatus.DORMANT

    def test_status_no_interval_few_days(self):
        svc = ReorderService.__new__(ReorderService)
        # No interval data, few days = DUE
        assert svc._determine_status(10, None) == ReorderStatus.DUE


class TestConfidenceLevel:
    """Test confidence calculation."""

    def test_high_confidence(self):
        svc = ReorderService.__new__(ReorderService)
        assert svc._calculate_confidence(6, 0.2) == ConfidenceLevel.HIGH

    def test_medium_confidence(self):
        svc = ReorderService.__new__(ReorderService)
        assert svc._calculate_confidence(4, 0.4) == ConfidenceLevel.MEDIUM

    def test_low_confidence_few_orders(self):
        svc = ReorderService.__new__(ReorderService)
        assert svc._calculate_confidence(2, 0.2) == ConfidenceLevel.LOW

    def test_low_confidence_high_variance(self):
        svc = ReorderService.__new__(ReorderService)
        assert svc._calculate_confidence(6, 0.6) == ConfidenceLevel.LOW


class TestScoreCalculation:
    """Test score calculation with weighted factors."""

    def test_score_perfect(self):
        """Customer right on time, consistent, many orders, has favorite product."""
        svc = ReorderService.__new__(ReorderService)
        score = svc._calculate_score(
            days_since_last_order=28,
            avg_interval=30,
            total_orders=10,
            cv=0.1,
            favorite_product="P13",
        )
        assert 70 <= score <= 100

    def test_score_zero_days(self):
        """Customer just ordered — should have low recency but high other factors."""
        svc = ReorderService.__new__(ReorderService)
        score = svc._calculate_score(
            days_since_last_order=0,
            avg_interval=30,
            total_orders=5,
            cv=0.2,
            favorite_product="P13",
        )
        # Recency is low (too early) but frequency/regularity/product boost it
        assert score <= 60

    def test_score_overdue(self):
        """Customer is very overdue."""
        svc = ReorderService.__new__(ReorderService)
        score = svc._calculate_score(
            days_since_last_order=90,
            avg_interval=30,
            total_orders=5,
            cv=0.2,
            favorite_product=None,
        )
        assert score < 70  # Lower score

    def test_score_no_product(self):
        """Score without favorite product should be lower."""
        svc = ReorderService.__new__(ReorderService)
        score_with = svc._calculate_score(28, 30, 10, 0.1, "P13")
        score_without = svc._calculate_score(28, 30, 10, 0.1, None)
        assert score_with > score_without

    def test_score_range(self):
        """Score should always be 0-100."""
        svc = ReorderService.__new__(ReorderService)
        for days in [0, 10, 30, 60, 90, 180]:
            for interval in [7, 14, 30, 60, None]:
                score = svc._calculate_score(days, interval, 5, 0.3, None)
                assert 0 <= score <= 100, f"Score {score} out of range for days={days}, interval={interval}"


class TestCoefficientOfVariation:
    """Test CV calculation."""

    def test_cv_consistent(self):
        """Consistent intervals should have low CV."""
        svc = ReorderService.__new__(ReorderService)
        cv = svc._coefficient_of_variation([30, 30, 30, 30])
        assert cv < 0.05

    def test_cv_variable(self):
        """Variable intervals should have high CV."""
        svc = ReorderService.__new__(ReorderService)
        cv = svc._coefficient_of_variation([10, 50, 15, 45])
        assert cv > 0.3

    def test_cv_empty(self):
        svc = ReorderService.__new__(ReorderService)
        assert svc._coefficient_of_variation([]) == 1.0

    def test_cv_single(self):
        svc = ReorderService.__new__(ReorderService)
        assert svc._coefficient_of_variation([30]) == 1.0


class TestIntervalCalculation:
    """Test interval calculation between orders."""

    def test_intervals_basic(self):
        svc = ReorderService.__new__(ReorderService)
        now = datetime.utcnow()
        orders = [
            type('Order', (), {'created_at': now - timedelta(days=60)})(),
            type('Order', (), {'created_at': now - timedelta(days=30)})(),
            type('Order', (), {'created_at': now})(),
        ]
        intervals = svc._calculate_intervals(orders)
        assert len(intervals) == 2
        assert intervals[0] == pytest.approx(30.0, abs=0.1)
        assert intervals[1] == pytest.approx(30.0, abs=0.1)

    def test_intervals_single_order(self):
        svc = ReorderService.__new__(ReorderService)
        now = datetime.utcnow()
        orders = [type('Order', (), {'created_at': now})()]
        intervals = svc._calculate_intervals(orders)
        assert intervals == []

    def test_intervals_empty(self):
        svc = ReorderService.__new__(ReorderService)
        assert svc._calculate_intervals([]) == []


class TestReorderOpportunity:
    """Test ReorderOpportunity serialization."""

    def test_to_dict(self):
        opp = ReorderOpportunity(
            customer_codigo="C001",
            customer_nome="João",
            total_orders=5,
            total_spent=1500.0,
            average_ticket=300.0,
            days_since_last_order=35,
            last_order_date=datetime(2026, 8, 1),
            expected_reorder_date=datetime(2026, 8, 31),
            expected_interval_days=30.0,
            reorder_score=75.5,
            confidence=ConfidenceLevel.HIGH,
            status=ReorderStatus.DUE,
            recommended_product="P13",
            days_overdue=5,
        )
        d = opp.to_dict()
        assert d["customer_codigo"] == "C001"
        assert d["confidence"] == "HIGH"
        assert d["status"] == "DUE"
        assert d["reorder_score"] == 75.5
        assert "last_order_date" in d


class TestReorderSummary:
    """Test ReorderSummary serialization."""

    def test_to_dict(self):
        s = ReorderSummary(
            total_customers=10,
            ready_count=3,
            due_count=4,
            overdue_count=2,
            dormant_count=1,
            high_confidence_count=5,
            medium_confidence_count=3,
            low_confidence_count=2,
        )
        d = s.to_dict()
        assert d["total_customers"] == 10
        assert d["ready_count"] == 3
        assert len(d["opportunities"]) == 0
