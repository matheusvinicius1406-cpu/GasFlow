"""
Delivery Use Cases — FASE 14

Application layer for delivery operations.
Uses domain entities + repositories. No direct DB access.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from app.domain.delivery.delivery import (
    Delivery, DeliveryStatus, DeliveryFailureReason, DeliveryProof,
    ProofType, AddressSnapshot,
)
from app.domain.delivery.driver import Driver, DriverStatus
from app.domain.delivery.vehicle import Vehicle
from app.domain.delivery.route import Route, RouteStop
from app.domain.delivery.routing import RoutingProvider, MockRoutingProvider
from app.domain.delivery.repository import (
    DeliveryRepository, DriverRepository, VehicleRepository, RouteRepository,
)


class CreateDeliveryUseCase:
    """Create a delivery for an order."""

    def __init__(self, delivery_repo: DeliveryRepository,
                 routing_provider: Optional[RoutingProvider] = None):
        self._repo = delivery_repo
        self._routing = routing_provider or MockRoutingProvider()

    def execute(self, tenant_id: str, order_id: str, customer_codigo: str,
                customer_name: str, address: Optional[Dict] = None,
                scheduled_at: Optional[datetime] = None,
                notes: str = "") -> Dict[str, Any]:
        # Check if delivery already exists for this order
        existing = self._repo.find_by_order_id(order_id, tenant_id)
        if existing:
            return {"success": False, "error": "Delivery already exists for this order"}

        addr = AddressSnapshot(**(address or {}))
        delivery = Delivery(
            order_id=order_id,
            tenant_id=tenant_id,
            customer_codigo=customer_codigo,
            customer_name=customer_name,
            address=addr,
            scheduled_at=scheduled_at,
            notes=notes,
        )
        delivery.timeline = [delivery.timeline[0]] if delivery.timeline else []
        saved = self._repo.save(delivery)
        return {"success": True, "delivery": saved.to_dict()}


class AssignDeliveryUseCase:
    """Assign a driver to a delivery."""

    def __init__(self, delivery_repo: DeliveryRepository,
                 driver_repo: DriverRepository,
                 vehicle_repo: Optional[VehicleRepository] = None):
        self._delivery_repo = delivery_repo
        self._driver_repo = driver_repo
        self._vehicle_repo = vehicle_repo

    def execute(self, tenant_id: str, delivery_id: str, driver_id: str,
                vehicle_id: Optional[str] = None) -> Dict[str, Any]:
        delivery = self._delivery_repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}
        if not delivery.can_transition(DeliveryStatus.ASSIGNED):
            return {"success": False, "error": f"Cannot assign in status {delivery.status.value}"}

        driver = self._driver_repo.find_by_id(driver_id, tenant_id)
        if not driver:
            return {"success": False, "error": "Driver not found"}
        if not driver.is_available:
            return {"success": False, "error": f"Driver is {driver.status.value}"}

        # Vehicle check
        if vehicle_id and self._vehicle_repo:
            vehicle = self._vehicle_repo.find_by_id(vehicle_id, tenant_id)
            if not vehicle or not vehicle.is_available:
                return {"success": False, "error": "Vehicle not available"}

        # Assign
        if not delivery.assign(driver_id, vehicle_id):
            return {"success": False, "error": "Assignment failed"}

        driver.set_busy()
        self._driver_repo.save(driver)
        self._delivery_repo.save(delivery)
        return {"success": True, "delivery": delivery.to_dict()}


class DispatchDeliveryUseCase:
    """Dispatch a delivery."""

    def __init__(self, delivery_repo: DeliveryRepository):
        self._repo = delivery_repo

    def execute(self, tenant_id: str, delivery_id: str) -> Dict[str, Any]:
        delivery = self._repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}
        if not delivery.dispatch():
            return {"success": False, "error": f"Cannot dispatch in status {delivery.status.value}"}
        self._repo.save(delivery)
        return {"success": True, "delivery": delivery.to_dict()}


class UpdateDeliveryStatusUseCase:
    """Update delivery status (arrive, complete, fail)."""

    def __init__(self, delivery_repo: DeliveryRepository,
                 driver_repo: Optional[DriverRepository] = None):
        self._delivery_repo = delivery_repo
        self._driver_repo = driver_repo

    def execute(self, tenant_id: str, delivery_id: str, new_status: str,
                failure_reason: Optional[str] = None, failure_notes: str = "",
                proof_type: Optional[str] = None,
                actor_type: str = "DRIVER") -> Dict[str, Any]:
        delivery = self._delivery_repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}

        if new_status == "EN_ROUTE":
            ok = delivery.start_route()
        elif new_status == "ARRIVED":
            ok = delivery.arrive()
        elif new_status == "DELIVERED":
            proof = None
            if proof_type:
                proof = DeliveryProof(
                    delivery_id=delivery_id,
                    proof_type=ProofType(proof_type),
                )
            ok = delivery.complete(proof)
        elif new_status == "FAILED":
            reason = DeliveryFailureReason.OTHER
            if failure_reason:
                try:
                    reason = DeliveryFailureReason(failure_reason)
                except ValueError:
                    pass
            ok = delivery.fail(reason, failure_notes)
        elif new_status == "CANCELLED":
            ok = delivery.cancel(actor_type)
        else:
            return {"success": False, "error": f"Unknown status: {new_status}"}

        if not ok:
            return {"success": False, "error": f"Cannot transition to {new_status}"}

        self._delivery_repo.save(delivery)

        # Release driver if terminal
        if delivery.status in {DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED, DeliveryStatus.FAILED}:
            if delivery.driver_id and self._driver_repo:
                driver = self._driver_repo.find_by_id(delivery.driver_id, tenant_id)
                if driver:
                    driver.set_available()
                    self._driver_repo.save(driver)

        return {"success": True, "delivery": delivery.to_dict()}


class CreateRouteUseCase:
    """Create a route with stops."""

    def __init__(self, route_repo: RouteRepository,
                 delivery_repo: DeliveryRepository):
        self._route_repo = route_repo
        self._delivery_repo = delivery_repo

    def execute(self, tenant_id: str, driver_id: str, vehicle_id: Optional[str] = None,
                stops: Optional[List[Dict]] = None) -> Dict[str, Any]:
        route = Route(tenant_id=tenant_id, driver_id=driver_id, vehicle_id=vehicle_id)
        if stops:
            for i, stop_data in enumerate(stops):
                delivery_id = stop_data.get("delivery_id", "")
                delivery = self._delivery_repo.find_by_id(delivery_id, tenant_id)
                addr_snapshot = ""
                if delivery:
                    addr_snapshot = delivery.address.full_address()
                route.add_stop(
                    delivery_id=delivery_id,
                    sequence=stop_data.get("sequence", i + 1),
                    customer_name=stop_data.get("customer_name", delivery.customer_name if delivery else ""),
                    customer_phone=stop_data.get("customer_phone", ""),
                    address_snapshot=addr_snapshot or stop_data.get("address", ""),
                )
        saved = self._route_repo.save(route)
        return {"success": True, "route": saved.to_dict()}


class DispatchRouteUseCase:
    """Dispatch a route."""

    def __init__(self, route_repo: RouteRepository,
                 delivery_repo: DeliveryRepository):
        self._route_repo = route_repo
        self._delivery_repo = delivery_repo

    def execute(self, tenant_id: str, route_id: str) -> Dict[str, Any]:
        route = self._route_repo.find_by_id(route_id, tenant_id)
        if not route:
            return {"success": False, "error": "Route not found"}
        if not route.dispatch():
            return {"success": False, "error": f"Cannot dispatch route in status {route.status.value}"}
        # Dispatch all deliveries in route
        for stop in route.stops:
            delivery = self._delivery_repo.find_by_id(stop.delivery_id, tenant_id)
            if delivery and delivery.can_transition(DeliveryStatus.DISPATCHED):
                delivery.dispatch()
                self._delivery_repo.save(delivery)
        self._route_repo.save(route)
        return {"success": True, "route": route.to_dict()}


class GetDeliveryUseCase:
    """Get delivery details."""

    def __init__(self, delivery_repo: DeliveryRepository):
        self._repo = delivery_repo

    def execute(self, tenant_id: str, delivery_id: str,
                customer_codigo: Optional[str] = None) -> Dict[str, Any]:
        delivery = self._repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}
        # Customer ownership check
        if customer_codigo and delivery.customer_codigo != customer_codigo:
            return {"success": False, "error": "Access denied"}
        return {"success": True, "delivery": delivery.to_dict()}


class ListDeliveriesUseCase:
    """List deliveries with filters."""

    def __init__(self, delivery_repo: DeliveryRepository):
        self._repo = delivery_repo

    def execute(self, tenant_id: str, status: Optional[str] = None,
                driver_id: Optional[str] = None,
                limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        delivery_status = None
        if status:
            try:
                delivery_status = DeliveryStatus(status)
            except ValueError:
                pass
        if driver_id:
            deliveries = self._repo.list_by_driver(driver_id, tenant_id)
        else:
            deliveries = self._repo.list_by_tenant(tenant_id, delivery_status, limit, offset)
        return {
            "success": True,
            "deliveries": [d.to_dict() for d in deliveries],
            "count": len(deliveries),
        }
