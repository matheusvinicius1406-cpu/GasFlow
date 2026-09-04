"""
Vehicle Repository — SQLAlchemy implementation for vehicle persistence.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.infrastructure.repositories.vehicle_model import VehicleModel, VehicleCapacityModel, VehicleLoadModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class VehicleRepository(TenantMixin):
    """Repository for vehicle CRUD + capacity + load operations."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    # ── Vehicle CRUD ───────────────────────────────────

    def create_vehicle(self, plate: str, model: str, vehicle_type: str = "VAN",
                       capacity_total: int = 0) -> VehicleModel:
        vehicle = VehicleModel(
            tenant_id=self.tenant_id,
            plate=plate,
            model=model,
            vehicle_type=vehicle_type,
            capacity_total=capacity_total,
        )
        self.db.add(vehicle)
        self.db.commit()
        self.db.refresh(vehicle)
        return vehicle

    def get_vehicle(self, vehicle_id: int) -> Optional[VehicleModel]:
        return self._filter_by_tenant(VehicleModel).filter(
            VehicleModel.id == vehicle_id
        ).first()

    def get_vehicle_by_plate(self, plate: str) -> Optional[VehicleModel]:
        return self._filter_by_tenant(VehicleModel).filter(
            VehicleModel.plate == plate
        ).first()

    def list_vehicles(self, status: Optional[str] = None) -> List[VehicleModel]:
        q = self._filter_by_tenant(VehicleModel).filter(VehicleModel.active == True)
        if status:
            q = q.filter(VehicleModel.status == status)
        return q.all()

    def assign_driver(self, vehicle_id: int, driver_id: str) -> bool:
        v = self.get_vehicle(vehicle_id)
        if not v:
            return False
        v.assigned_driver_id = driver_id
        v.status = "IN_USE"
        self.db.commit()
        return True

    def unassign_driver(self, vehicle_id: int) -> bool:
        v = self.get_vehicle(vehicle_id)
        if not v:
            return False
        v.assigned_driver_id = None
        v.status = "AVAILABLE"
        self.db.commit()
        return True

    # ── Capacity ───────────────────────────────────────

    def set_capacity(self, vehicle_id: int, product_codigo: str,
                     max_capacity: int, product_name: str = "", unit: str = "UNITS"):
        existing = self._filter_by_tenant(VehicleCapacityModel).filter(
            VehicleCapacityModel.vehicle_id == vehicle_id,
            VehicleCapacityModel.product_codigo == product_codigo,
        ).first()
        if existing:
            existing.max_capacity = max_capacity
            existing.product_name = product_name
            existing.unit = unit
        else:
            cap = VehicleCapacityModel(
                tenant_id=self.tenant_id,
                vehicle_id=vehicle_id,
                product_codigo=product_codigo,
                product_name=product_name,
                max_capacity=max_capacity,
                unit=unit,
            )
            self.db.add(cap)
        self.db.commit()

    def get_capacities(self, vehicle_id: int) -> List[VehicleCapacityModel]:
        return self._filter_by_tenant(VehicleCapacityModel).filter(
            VehicleCapacityModel.vehicle_id == vehicle_id
        ).all()

    # ── Load ───────────────────────────────────────────

    def get_load(self, vehicle_id: int, product_codigo: str) -> Optional[VehicleLoadModel]:
        return self._filter_by_tenant(VehicleLoadModel).filter(
            VehicleLoadModel.vehicle_id == vehicle_id,
            VehicleLoadModel.product_codigo == product_codigo,
        ).first()

    def get_all_loads(self, vehicle_id: int) -> List[VehicleLoadModel]:
        return self._filter_by_tenant(VehicleLoadModel).filter(
            VehicleLoadModel.vehicle_id == vehicle_id
        ).all()

    def can_carry(self, vehicle_id: int, product_codigo: str, quantity: int) -> bool:
        """Check if vehicle has capacity for the given product and quantity."""
        cap = self._filter_by_tenant(VehicleCapacityModel).filter(
            VehicleCapacityModel.vehicle_id == vehicle_id,
            VehicleCapacityModel.product_codigo == product_codigo,
        ).first()
        if not cap:
            return False

        load = self.get_load(vehicle_id, product_codigo)
        current_loaded = load.loaded if load else 0
        current_reserved = load.reserved if load else 0
        available = cap.max_capacity - current_loaded - current_reserved
        return available >= quantity

    def reserve_load(self, vehicle_id: int, product_codigo: str, quantity: int) -> bool:
        """Reserve capacity for a delivery. Returns False if insufficient."""
        if not self.can_carry(vehicle_id, product_codigo, quantity):
            return False

        load = self.get_load(vehicle_id, product_codigo)
        if load:
            load.reserved += quantity
        else:
            load = VehicleLoadModel(
                tenant_id=self.tenant_id,
                vehicle_id=vehicle_id,
                product_codigo=product_codigo,
                loaded=0,
                reserved=quantity,
            )
            self.db.add(load)
        self.db.commit()
        return True

    def consume_reserved(self, vehicle_id: int, product_codigo: str, quantity: int):
        """Move reserved to loaded (delivery started)."""
        load = self.get_load(vehicle_id, product_codigo)
        if load:
            load.reserved = max(0, load.reserved - quantity)
            load.loaded += quantity
            self.db.commit()

    def release_reserved(self, vehicle_id: int, product_codigo: str, quantity: int):
        """Release reserved capacity (delivery cancelled)."""
        load = self.get_load(vehicle_id, product_codigo)
        if load:
            load.reserved = max(0, load.reserved - quantity)
            self.db.commit()

    def unload(self, vehicle_id: int, product_codigo: str, quantity: int):
        """Reduce loaded count (delivery completed)."""
        load = self.get_load(vehicle_id, product_codigo)
        if load:
            load.loaded = max(0, load.loaded - quantity)
            self.db.commit()

    def get_load_summary(self, vehicle_id: int) -> dict:
        """Get complete load summary for a vehicle."""
        capacities = self.get_capacities(vehicle_id)
        loads = self.get_all_loads(vehicle_id)
        load_map = {ld.product_codigo: ld for ld in loads}

        summary = {}
        for cap in capacities:
            ld = load_map.get(cap.product_codigo)
            loaded = ld.loaded if ld else 0
            reserved = ld.reserved if ld else 0
            summary[cap.product_codigo] = {
                "product": cap.product_name or cap.product_codigo,
                "max_capacity": cap.max_capacity,
                "loaded": loaded,
                "reserved": reserved,
                "available": cap.max_capacity - loaded - reserved,
                "unit": cap.unit,
            }
        return summary
