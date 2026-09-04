"""
Reorder Intelligence Service — FASE 13.2

Deterministic engine that analyzes purchase history to predict reorder opportunities.
No LLM dependency — pure statistical analysis.

Scoring weights:
- Recency factor: 30% (how recent is the last order)
- Frequency factor: 25% (order frequency relative to average)
- Regularity factor: 25% (consistency of intervals)
- Product recurrence factor: 20% (repeated product purchases)

Confidence levels:
- HIGH: 6+ orders, low interval variance (CV < 0.3)
- MEDIUM: 3-5 orders, moderate variance (CV < 0.5)
- LOW: < 3 orders or high variance
"""

from datetime import datetime, timedelta
from typing import List, Optional
from app.domain.reorder.entity import ReorderOpportunity, ReorderStatus, ConfidenceLevel, ReorderSummary
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository


# Scoring weights
WEIGHT_RECENCY = 0.30
WEIGHT_FREQUENCY = 0.25
WEIGHT_REGULARITY = 0.25
WEIGHT_PRODUCT = 0.20

# Confidence thresholds
HIGH_CONFIDENCE_MIN_ORDERS = 6
MEDIUM_CONFIDENCE_MIN_ORDERS = 3
LOW_CV_THRESHOLD = 0.3   # coefficient of variation for HIGH
MEDIUM_CV_THRESHOLD = 0.5  # coefficient of variation for MEDIUM

# Status thresholds (in days relative to expected interval)
READY_BUFFER_DAYS = 3      # within 3 days before expected
DUE_BUFFER_DAYS = 7        # within 7 days after expected
OVERDUE_THRESHOLD_DAYS = 14  # more than 14 days after expected
DORMANT_THRESHOLD_DAYS = 30  # more than 30 days after expected


class ReorderService:
    """Service for computing reorder intelligence from real purchase data."""

    def __init__(self, client_repo: SQLAlchemyClientRepository, order_repo: SQLAlchemyOrderRepository):
        self.client_repo = client_repo
        self.order_repo = order_repo

    def analyze_customer(self, client_codigo: str) -> Optional[ReorderOpportunity]:
        """Analyze a single customer's reorder potential.

        Returns None if customer has no orders.
        """
        customer = self.client_repo.buscar_por_codigo(client_codigo)
        if not customer:
            return None

        metrics = self.order_repo.get_customer_metrics(client_codigo)
        if not metrics or metrics["total_orders"] == 0:
            return None

        orders = self.order_repo.listar_todos()
        customer_orders = [o for o in orders if o.client_codigo == client_codigo]
        customer_orders.sort(key=lambda o: o.created_at)

        # Calculate intervals between orders
        intervals = self._calculate_intervals(customer_orders)

        # Calculate expected interval
        avg_interval = sum(intervals) / len(intervals) if intervals else None
        cv = self._coefficient_of_variation(intervals) if intervals else 1.0

        # Determine confidence
        confidence = self._calculate_confidence(metrics["total_orders"], cv)

        # Calculate expected reorder date
        last_order_date = metrics["last_order_at"]
        expected_reorder_date = None
        if last_order_date and avg_interval:
            expected_reorder_date = last_order_date + timedelta(days=avg_interval)

        # Calculate reorder score
        now = datetime.utcnow()
        days_since = metrics["days_since_last_order"] if metrics["days_since_last_order"] is not None else 999

        score = self._calculate_score(
            days_since_last_order=days_since,
            avg_interval=avg_interval,
            total_orders=metrics["total_orders"],
            cv=cv,
            favorite_product=metrics.get("favorite_product"),
        )

        # Determine status
        status = self._determine_status(days_since, avg_interval)

        # Calculate days overdue
        days_overdue = None
        if expected_reorder_date and now > expected_reorder_date:
            days_overdue = (now - expected_reorder_date).days

        # Get order dates for display
        order_dates = [o.created_at.isoformat() for o in customer_orders if o.created_at]

        return ReorderOpportunity(
            customer_codigo=client_codigo,
            customer_nome=customer.nome,
            total_orders=metrics["total_orders"],
            total_spent=metrics["total_spent"],
            average_ticket=metrics["average_ticket"],
            days_since_last_order=days_since,
            last_order_date=last_order_date,
            expected_reorder_date=expected_reorder_date,
            expected_interval_days=round(avg_interval, 1) if avg_interval else None,
            reorder_score=round(score, 1),
            confidence=confidence,
            status=status,
            recommended_product=metrics.get("favorite_product"),
            days_overdue=days_overdue,
            avg_days_between_orders=round(avg_interval, 1) if avg_interval else None,
            order_dates=order_dates,
        )

    def get_opportunities(
        self,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[ReorderOpportunity]:
        """Get all reorder opportunities, optionally filtered."""
        customers = self.client_repo.listar_todos()
        opportunities = []

        for customer in customers:
            opp = self.analyze_customer(customer.codigo)
            if not opp:
                continue

            # Apply filters
            if status and opp.status.value != status:
                continue
            if confidence and opp.confidence.value != confidence:
                continue
            if min_score is not None and opp.reorder_score < min_score:
                continue

            opportunities.append(opp)

        # Sort by score descending
        opportunities.sort(key=lambda o: o.reorder_score, reverse=True)
        return opportunities

    def get_summary(
        self,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
    ) -> ReorderSummary:
        """Get aggregate summary of reorder opportunities."""
        opportunities = self.get_opportunities(status=status, confidence=confidence)

        return ReorderSummary(
            total_customers=len(opportunities),
            ready_count=sum(1 for o in opportunities if o.status == ReorderStatus.READY),
            due_count=sum(1 for o in opportunities if o.status == ReorderStatus.DUE),
            overdue_count=sum(1 for o in opportunities if o.status == ReorderStatus.OVERDUE),
            dormant_count=sum(1 for o in opportunities if o.status == ReorderStatus.DORMANT),
            high_confidence_count=sum(1 for o in opportunities if o.confidence == ConfidenceLevel.HIGH),
            medium_confidence_count=sum(1 for o in opportunities if o.confidence == ConfidenceLevel.MEDIUM),
            low_confidence_count=sum(1 for o in opportunities if o.confidence == ConfidenceLevel.LOW),
            opportunities=opportunities,
        )

    # ── Private helpers ────────────────────────────────

    def _calculate_intervals(self, orders: list) -> List[float]:
        """Calculate days between consecutive orders."""
        if len(orders) < 2:
            return []
        intervals = []
        for i in range(1, len(orders)):
            if orders[i].created_at and orders[i - 1].created_at:
                delta = (orders[i].created_at - orders[i - 1].created_at).total_seconds() / 86400
                if delta > 0:
                    intervals.append(delta)
        return intervals

    def _coefficient_of_variation(self, values: List[float]) -> float:
        """Calculate coefficient of variation (std/mean)."""
        if not values or len(values) < 2:
            return 1.0
        mean = sum(values) / len(values)
        if mean == 0:
            return 1.0
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = variance ** 0.5
        return std / mean

    def _calculate_confidence(self, total_orders: int, cv: float) -> ConfidenceLevel:
        """Determine confidence level based on data quantity and consistency."""
        if total_orders >= HIGH_CONFIDENCE_MIN_ORDERS and cv < LOW_CV_THRESHOLD:
            return ConfidenceLevel.HIGH
        if total_orders >= MEDIUM_CONFIDENCE_MIN_ORDERS and cv < MEDIUM_CV_THRESHOLD:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def _calculate_score(
        self,
        days_since_last_order: int,
        avg_interval: Optional[float],
        total_orders: int,
        cv: float,
        favorite_product: Optional[str],
    ) -> float:
        """Calculate reorder score (0-100) using weighted factors.

        Score components:
        - Recency (30%): how close to expected reorder date
        - Frequency (25%): order frequency relative to 30-day baseline
        - Regularity (25%): consistency of purchase intervals
        - Product (20%): whether customer has a repeated product
        """
        # Recency factor: 0-100 based on how close to expected date
        if avg_interval and avg_interval > 0:
            ratio = days_since_last_order / avg_interval
            if ratio < 0.5:
                recency = 20  # Too early
            elif ratio < 0.8:
                recency = 60  # Approaching
            elif ratio < 1.2:
                recency = 100  # Right on time
            elif ratio < 1.5:
                recency = 80  # Slightly overdue
            elif ratio < 2.0:
                recency = 50  # Overdue
            else:
                recency = 20  # Very overdue / dormant
        else:
            recency = max(0, 100 - days_since_last_order)

        # Frequency factor: normalized to 30-day cycle
        if avg_interval and avg_interval > 0:
            orders_per_month = 30.0 / avg_interval
            frequency = min(100, orders_per_month * 33.3)  # ~3 orders/month = 100
        else:
            frequency = min(100, total_orders * 10)

        # Regularity factor: inverse of CV
        regularity = max(0, min(100, (1.0 - cv) * 100))

        # Product recurrence: binary boost
        product_factor = 80 if favorite_product else 30

        # Weighted score
        score = (
            recency * WEIGHT_RECENCY +
            frequency * WEIGHT_FREQUENCY +
            regularity * WEIGHT_REGULARITY +
            product_factor * WEIGHT_PRODUCT
        )

        return min(100, max(0, score))

    def _determine_status(self, days_since_last_order: int, avg_interval: Optional[float]) -> ReorderStatus:
        """Classify reorder urgency."""
        if not avg_interval or avg_interval == 0:
            if days_since_last_order > DORMANT_THRESHOLD_DAYS:
                return ReorderStatus.DORMANT
            return ReorderStatus.DUE

        ratio = days_since_last_order / avg_interval

        if ratio < 0.8:
            return ReorderStatus.READY
        elif ratio < 1.3:
            return ReorderStatus.DUE
        elif ratio < 2.0:
            return ReorderStatus.OVERDUE
        else:
            return ReorderStatus.DORMANT
