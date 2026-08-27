"""
Dispatch Service — FASE 14

Orchestrates delivery assignment, routing, and driver management.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from app.domain.delivery.delivery import Delivery, DeliveryStatus
from app.domain.delivery.driver import Driver, DriverStatus
from app.domain.delivery.vehicle import Vehicle
from app.domain.delivery.route import Route
from app.domain.delivery.repository import (
    DeliveryRepository, DriverRepository, VehicleRepository, RouteRepository,
)


class DispatchService:
    """Orchestration service for dispatch operations."""

    def __init__(self, delivery_repo: DeliveryRepository,
                 driver_repo: DriverRepository,
                 vehicle_repo: Optional[VehicleRepository] = None,
                 route_repo: Optional[RouteRepository] = None):
        self._delivery_repo = delivery_repo
        self._driver_repo = driver_repo
        self._vehicle_repo = vehicle_repo
        self._route_repo = route_repo

    def get_dispatch_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get dispatch dashboard summary."""
        deliveries = self._delivery_repo.list_by_tenant(tenant_id)
        drivers = self._driver_repo.list_by_tenant(tenant_id)
        statuses = self._delivery_repo.count_by_status(tenant_id)
        driver_statuses = self._driver_repo.count_by_status(tenant_id)

        return {
            "deliveries": {
                "total": len(deliveries),
                "by_status": statuses,
            },
            "drivers": {
                "total": len(drivers),
                "by_status": driver_statuses,
                "available": sum(1 for d in drivers if d.is_available),
            },
        }

    def assign_best_driver(self, tenant_id: str, delivery_id: str) -> Dict[str, Any]:
        """Auto-assign the best available driver to a delivery."""
        delivery = self._delivery_repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}
        if not delivery.can_transition(DeliveryStatus.ASSIGNED):
            return {"success": False, "error": f"Cannot assign in status {delivery.status.value}"}

        available = self._driver_repo.list_available(tenant_id)
        if not available:
            return {"success": False, "error": "No available drivers"}

        # Simple strategy: first available driver
        driver = available[0]
        vehicle_id = driver.vehicle_id

        delivery.assign(driver.id, vehicle_id)
        driver.set_busy()

        self._driver_repo.save(driver)
        self._delivery_repo.save(delivery)
        return {"success": True, "delivery": delivery.to_dict(), "driver": driver.to_dict()}

    def create_batch_route(self, tenant_id: str, delivery_ids: List[str],
                           driver_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a route from multiple deliveries."""
        if not self._route_repo:
            return {"success": False, "error": "Route repository not available"}

        # Find or assign driver
        if not driver_id:
            available = self._driver_repo.list_available(tenant_id)
            if not available:
                return {"success": False, "error": "No available drivers"}
            driver_id = available[0].id

        driver = self._driver_repo.find_by_id(driver_id, tenant_id)
        if not driver:
            return {"success": False, "error": "Driver not found"}

        route = Route(tenant_id=tenant_id, driver_id=driver_id, vehicle_id=driver.vehicle_id)

        for i, did in enumerate(delivery_ids):
            delivery = self._delivery_repo.find_by_id(did, tenant_id)
            if not delivery:
                continue
            addr_snapshot = delivery.address.full_address()
            route.add_stop(
                delivery_id=did,
                sequence=i + 1,
                customer_name=delivery.customer_name,
                address_snapshot=addr_snapshot,
            )

        saved = self._route_repo.save(route)

        # Assign driver
        driver.set_busy()
        self._driver_repo.save(driver)

        return {"success": True, "route": saved.to_dict()}
