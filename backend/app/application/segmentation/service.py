"""
Segment Service — FASE 13.1

Evaluates customer segments against real data.
Deterministic, auditable, tenant-scoped.

Architecture:
- Receives customer metrics from existing repositories
- Evaluates rules against metrics
- Returns matching customer IDs
"""

from typing import Dict, Any, List
from datetime import datetime

from app.domain.segmentation.entity import Segment


class SegmentService:
    """Service for evaluating customer segments."""

    def __init__(
        self, order_repository=None, client_repository=None, payment_repository=None, receivable_repository=None
    ):
        self.order_repo = order_repository
        self.client_repo = client_repository
        self.payment_repo = payment_repository
        self.receivable_repo = receivable_repository

    def get_customer_metrics(self, client_codigo: str) -> Dict[str, Any]:
        """Get all metrics for a customer needed for segmentation."""
        metrics = {
            "total_orders": 0,
            "total_spent": 0.0,
            "average_ticket": 0.0,
            "days_since_last_order": None,
            "favorite_product": None,
            "client_type": None,
            "is_active": True,
            "has_email": False,
            "order_frequency": 0.0,
            "payment_status": "NONE",
        }

        # Get client info
        if self.client_repo:
            client = self.client_repo.buscar_por_codigo(client_codigo)
            if client:
                metrics["client_type"] = client.tipo or ""
                metrics["is_active"] = client.ativo
                metrics["has_email"] = bool(client.email)

        # Get order metrics
        if self.order_repo:
            order_metrics = self.order_repo.get_customer_metrics(client_codigo)
            metrics["total_orders"] = order_metrics.get("total_orders", 0)
            metrics["total_spent"] = order_metrics.get("total_spent", 0.0)
            metrics["average_ticket"] = order_metrics.get("average_ticket", 0.0)
            metrics["days_since_last_order"] = order_metrics.get("days_since_last_order")
            metrics["favorite_product"] = order_metrics.get("favorite_product", "")

            # Calculate order frequency (orders per month)
            if order_metrics.get("first_order_at") and metrics["total_orders"] > 0:
                first = order_metrics["first_order_at"]
                now = datetime.utcnow()
                months = max((now - first).days / 30.0, 1.0)
                metrics["order_frequency"] = round(metrics["total_orders"] / months, 2)

        # Get payment status
        if self.receivable_repo:
            outstanding = self.receivable_repo.total_outstanding_for_customer(client_codigo)
            if outstanding > 0:
                metrics["payment_status"] = "PENDING"
            else:
                metrics["payment_status"] = "PAID"

        return metrics

    def evaluate_segment(self, segment: Segment, customer_metrics: Dict[str, Any]) -> bool:
        """Evaluate if a customer belongs to a segment."""
        return segment.evaluate_customer(customer_metrics)

    def count_segment_members(self, segment: Segment, all_customer_codes: List[str]) -> int:
        """Count how many customers match a segment."""
        count = 0
        for codigo in all_customer_codes:
            metrics = self.get_customer_metrics(codigo)
            if self.evaluate_segment(segment, metrics):
                count += 1
        return count

    def get_segment_members(
        self, segment: Segment, all_customer_codes: List[str], limit: int = 100, offset: int = 0
    ) -> List[str]:
        """Get customer codes that match a segment."""
        members = []
        for codigo in all_customer_codes:
            metrics = self.get_customer_metrics(codigo)
            if self.evaluate_segment(segment, metrics):
                members.append(codigo)
                if len(members) >= limit + offset:
                    break
        return members[offset : offset + limit]

    def preview_segment(self, segment: Segment, all_customer_codes: List[str]) -> Dict[str, Any]:
        """Preview segment results without persisting."""
        members = []
        for codigo in all_customer_codes:
            metrics = self.get_customer_metrics(codigo)
            if self.evaluate_segment(segment, metrics):
                members.append(
                    {
                        "codigo": codigo,
                        "metrics": metrics,
                    }
                )

        return {
            "total_evaluated": len(all_customer_codes),
            "total_matches": len(members),
            "members": members[:50],  # Preview max 50
        }
