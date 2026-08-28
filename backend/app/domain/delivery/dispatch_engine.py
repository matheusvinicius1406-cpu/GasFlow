"""
Dispatch Engine — Intelligent Delivery Assignment

Receives:
  - Order (customer, items, priority, location)
  - Candidates (drivers with vehicle, location, availability, capacity)

Process:
  1. Filter invalid candidates (availability, capacity, restrictions)
  2. Score valid candidates (distance, capacity, ETA, priority)
  3. Return ranked recommendations

Rules:
  - Physical capacity ALWAYS wins over proximity
  - Driver availability is binary (not scored)
  - ETA is calculated, not invented
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum


class DispatchMode(str, Enum):
    MANUAL = "MANUAL"           # Admin selects driver
    ASSISTED = "ASSISTED"       # System recommends, admin confirms
    AUTOMATIC = "AUTOMATIC"     # System assigns automatically


class CandidateFilter(Enum):
    """Why a candidate was rejected."""
    NOT_ACTIVE = "NOT_ACTIVE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NO_VEHICLE = "NO_VEHICLE"
    VEHICLE_NOT_AVAILABLE = "VEHICLE_NOT_AVAILABLE"
    INSUFFICIENT_CAPACITY = "INSUFFICIENT_CAPACITY"
    PRODUCT_NOT_SUPPORTED = "PRODUCT_NOT_SUPPORTED"
    WRONG_TENANT = "WRONG_TENANT"
    PAUSED = "PAUSED"


@dataclass
class OrderItem:
    """Simplified order item for dispatch."""
    product_codigo: str
    product_name: str
    quantity: int


@dataclass
class OrderRequest:
    """Order details needed for dispatch."""
    order_id: str
    tenant_id: str
    customer_codigo: str
    customer_name: str
    items: List[OrderItem] = field(default_factory=list)
    priority: int = 0           # 0=normal, 1=high, 2=urgent
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    scheduled_at: Optional[datetime] = None
    notes: str = ""


@dataclass
class DriverCandidate:
    """Candidate driver with all relevant data."""
    driver_id: str
    driver_name: str
    vehicle_id: Optional[str] = None
    vehicle_plate: Optional[str] = None
    status: str = "AVAILABLE"
    is_active: bool = True
    is_paused: bool = False
    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    last_seen: Optional[datetime] = None
    # Capacity per product: {product_codigo: available_quantity}
    capacity: Dict[str, int] = field(default_factory=dict)
    # Load per product: {product_codigo: current_load}
    current_load: Dict[str, int] = field(default_factory=dict)
    # Current route
    active_deliveries: int = 0
    current_route_lat: Optional[float] = None
    current_route_lng: Optional[float] = None


@dataclass
class FilterResult:
    """Result of filtering a candidate."""
    valid: bool
    reason: Optional[CandidateFilter] = None
    details: str = ""


@dataclass
class ScoreResult:
    """Score for a valid candidate."""
    score: float = 0.0          # 0-100
    distance_km: float = 0.0
    capacity_score: float = 0.0
    proximity_score: float = 0.0
    route_score: float = 0.0
    priority_score: float = 0.0
    explanation: List[str] = field(default_factory=list)


@dataclass
class DispatchRecommendation:
    """Final recommendation from dispatch engine."""
    driver_id: str
    driver_name: str
    vehicle_id: Optional[str]
    vehicle_plate: Optional[str]
    score: float
    distance_km: float
    capacity_fit: Dict[str, dict]  # Per-product fit
    explanation: List[str]
    estimated_minutes: Optional[int] = None


# ═══════════════════════════════════════════════════════════
# FILTER — Binary eligibility check
# ═══════════════════════════════════════════════════════════

def filter_candidate(candidate: DriverCandidate, order: OrderRequest) -> FilterResult:
    """Check if candidate is eligible. Binary: eligible or not."""

    if not candidate.is_active:
        return FilterResult(False, CandidateFilter.NOT_ACTIVE, "Driver inactive")

    if candidate.status not in ("AVAILABLE", "BUSY"):
        return FilterResult(False, CandidateFilter.NOT_AVAILABLE, f"Driver status: {candidate.status}")

    if candidate.is_paused:
        return FilterResult(False, CandidateFilter.PAUSED, "Driver paused")

    if not candidate.vehicle_id:
        return FilterResult(False, CandidateFilter.NO_VEHICLE, "No vehicle assigned")

    if not candidate.latitude or not candidate.longitude:
        return FilterResult(False, CandidateFilter.NOT_AVAILABLE, "No GPS location")

    # Check capacity for each item
    for item in order.items:
        available = candidate.capacity.get(item.product_codigo, 0)
        if available < item.quantity:
            return FilterResult(
                False,
                CandidateFilter.INSUFFICIENT_CAPACITY,
                f"{item.product_name}: needs {item.quantity}, available {available}",
            )

    return FilterResult(True)


# ═══════════════════════════════════════════════════════════
# SCORE — Ranking for valid candidates
# ═══════════════════════════════════════════════════════════

def score_candidate(candidate: DriverCandidate, order: OrderRequest) -> ScoreResult:
    """Score a valid candidate. Higher = better fit."""

    explanation = []

    # ── Distance (40% weight) ────────────────────────────
    distance_km = 0.0
    if order.latitude and order.longitude and candidate.latitude and candidate.longitude:
        distance_km = _haversine_km(
            candidate.latitude, candidate.longitude,
            order.latitude, order.longitude,
        )

    # Proximity score: closer = higher (max 5km = score 100)
    proximity_score = max(0, 100 - (distance_km * 20))
    if distance_km <= 1:
        explanation.append(f"✓ Very close: {distance_km:.1f} km")
    elif distance_km <= 3:
        explanation.append(f"✓ Near: {distance_km:.1f} km")
    else:
        explanation.append(f"Distan: {distance_km:.1f} km")

    # ── Capacity (30% weight) ────────────────────────────
    capacity_scores = []
    for item in order.items:
        available = candidate.capacity.get(item.product_codigo, 0)
        if available > 0:
            # Higher remaining capacity = better (can serve more future orders)
            ratio = min(available / max(item.quantity, 1), 5.0)  # Cap at 5x
            capacity_scores.append(ratio * 20)  # 0-100 per product
    capacity_score = sum(capacity_scores) / max(len(capacity_scores), 1)

    if capacity_score >= 80:
        explanation.append(f"✓ Ample capacity")
    elif capacity_score >= 50:
        explanation.append(f"Adequate capacity")
    else:
        explanation.append(f"⚠ Limited capacity")

    # ── Route synergy (20% weight) ───────────────────────
    route_score = 0.0
    if candidate.current_route_lat and candidate.current_route_lng and order.latitude and order.longitude:
        route_deviation = _haversine_km(
            candidate.current_route_lat, candidate.current_route_lng,
            order.latitude, order.longitude,
        )
        route_score = max(0, 100 - (route_deviation * 25))
        if route_deviation < 2:
            explanation.append(f"✓ On route (deviation: {route_deviation:.1f} km)")
        elif route_deviation < 5:
            explanation.append(f"Near route (deviation: {route_deviation:.1f} km)")

    # ── Workload (10% weight) ────────────────────────────
    # Fewer active deliveries = better
    workload_score = max(0, 100 - (candidate.active_deliveries * 25))
    if candidate.active_deliveries == 0:
        explanation.append("✓ No active deliveries")
    elif candidate.active_deliveries <= 2:
        explanation.append(f"{candidate.active_deliveries} active deliveries")
    else:
        explanation.append(f"⚠ {candidate.active_deliveries} active deliveries")

    # ── Composite score ──────────────────────────────────
    score = (
        proximity_score * 0.40 +
        capacity_score * 0.30 +
        route_score * 0.20 +
        workload_score * 0.10
    )

    return ScoreResult(
        score=round(score, 1),
        distance_km=round(distance_km, 2),
        capacity_score=round(capacity_score, 1),
        proximity_score=round(proximity_score, 1),
        route_score=round(route_score, 1),
        priority_score=round(workload_score, 1),
        explanation=explanation,
    )


# ═══════════════════════════════════════════════════════════
# DISPATCH ENGINE — Main orchestrator
# ═══════════════════════════════════════════════════════════

class DispatchEngine:
    """
    Intelligent dispatch engine.

    Usage:
        engine = DispatchEngine()
        results = engine.find_candidates(order, all_drivers)
        best = engine.recommend(order, all_drivers)
    """

    def __init__(self, mode: DispatchMode = DispatchMode.ASSISTED):
        self.mode = mode

    def filter_candidates(
        self, order: OrderRequest, candidates: List[DriverCandidate],
    ) -> List[Tuple[DriverCandidate, FilterResult]]:
        """Filter all candidates, returning eligibility results."""
        results = []
        for c in candidates:
            result = filter_candidate(c, order)
            results.append((c, result))
        return results

    def score_candidates(
        self, order: OrderRequest, valid_candidates: List[DriverCandidate],
    ) -> List[Tuple[DriverCandidate, ScoreResult]]:
        """Score all valid candidates."""
        scored = []
        for c in valid_candidates:
            score = score_candidate(c, order)
            scored.append((c, score))
        # Sort by score descending
        scored.sort(key=lambda x: x[1].score, reverse=True)
        return scored

    def recommend(
        self, order: OrderRequest, candidates: List[DriverCandidate],
        top_n: int = 3,
    ) -> Dict[str, Any]:
        """
        Full dispatch analysis: filter → score → recommend.
        Returns recommendations, rejected candidates, and analysis.
        """
        # Step 1: Filter
        all_filtered = self.filter_candidates(order, candidates)
        valid = [(c, f) for c, f in all_filtered if f.valid]
        rejected = [(c, f) for c, f in all_filtered if not f.valid]

        if not valid:
            return {
                "success": False,
                "error": "No eligible drivers",
                "rejected": [
                    {"driver_id": c.driver_id, "driver_name": c.driver_name,
                     "reason": f.reason.value if f.reason else "UNKNOWN",
                     "details": f.details}
                    for c, f in rejected
                ],
                "recommendations": [],
            }

        # Step 2: Score
        scored = self.score_candidates(order, [c for c, _ in valid])

        # Step 3: Build recommendations
        recommendations = []
        for candidate, score_result in scored[:top_n]:
            # Build capacity fit
            capacity_fit = {}
            for item in order.items:
                available = candidate.capacity.get(item.product_codigo, 0)
                capacity_fit[item.product_codigo] = {
                    "product": item.product_name,
                    "needed": item.quantity,
                    "available": available,
                    "fits": available >= item.quantity,
                }

            recommendations.append(DispatchRecommendation(
                driver_id=candidate.driver_id,
                driver_name=candidate.driver_name,
                vehicle_id=candidate.vehicle_id,
                vehicle_plate=candidate.vehicle_plate,
                score=score_result.score,
                distance_km=score_result.distance_km,
                capacity_fit=capacity_fit,
                explanation=score_result.explanation,
            ))

        return {
            "success": True,
            "order_id": order.order_id,
            "total_candidates": len(candidates),
            "eligible": len(valid),
            "rejected_count": len(rejected),
            "rejected": [
                {"driver_id": c.driver_id, "driver_name": c.driver_name,
                 "reason": f.reason.value if f.reason else "UNKNOWN",
                 "details": f.details}
                for c, f in rejected
            ],
            "recommendations": [
                {
                    "driver_id": r.driver_id,
                    "driver_name": r.driver_name,
                    "vehicle_id": r.vehicle_id,
                    "vehicle_plate": r.vehicle_plate,
                    "score": r.score,
                    "distance_km": r.distance_km,
                    "capacity_fit": r.capacity_fit,
                    "explanation": r.explanation,
                }
                for r in recommendations
            ],
        }


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in km."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
