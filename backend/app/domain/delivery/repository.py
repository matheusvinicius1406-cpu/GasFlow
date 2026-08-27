"""
Repository Interfaces — FASE 14

Abstract repositories for delivery domain entities.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.delivery.delivery import Delivery, DeliveryStatus
from app.domain.delivery.driver import Driver, DriverStatus
from app.domain.delivery.vehicle import Vehicle, VehicleStatus
from app.domain.delivery.route import Route, RouteStatus
from app.domain.delivery.entity import DeliveryDriver


class DeliveryRepository(ABC):
    @abstractmethod
    def save(self, delivery: Delivery) -> Delivery: ...
    @abstractmethod
    def find_by_id(self, delivery_id: str, tenant_id: str) -> Optional[Delivery]: ...
    @abstractmethod
    def find_by_order_id(self, order_id: str, tenant_id: str) -> Optional[Delivery]: ...
    @abstractmethod
    def list_by_tenant(self, tenant_id: str, status: Optional[DeliveryStatus] = None,
                       limit: int = 50, offset: int = 0) -> List[Delivery]: ...
    @abstractmethod
    def list_by_driver(self, driver_id: str, tenant_id: str) -> List[Delivery]: ...
    @abstractmethod
    def count_by_status(self, tenant_id: str) -> dict: ...


class DriverRepository(ABC):
    @abstractmethod
    def save(self, driver: Driver) -> Driver: ...
    @abstractmethod
    def find_by_id(self, driver_id: str, tenant_id: str) -> Optional[Driver]: ...
    @abstractmethod
    def list_by_tenant(self, tenant_id: str, status: Optional[DriverStatus] = None) -> List[Driver]: ...
    @abstractmethod
    def list_available(self, tenant_id: str) -> List[Driver]: ...
    @abstractmethod
    def count_by_status(self, tenant_id: str) -> dict: ...


class VehicleRepository(ABC):
    @abstractmethod
    def save(self, vehicle: Vehicle) -> Vehicle: ...
    @abstractmethod
    def find_by_id(self, vehicle_id: str, tenant_id: str) -> Optional[Vehicle]: ...
    @abstractmethod
    def list_by_tenant(self, tenant_id: str, status: Optional[VehicleStatus] = None) -> List[Vehicle]: ...
    @abstractmethod
    def list_available(self, tenant_id: str) -> List[Vehicle]: ...


class RouteRepository(ABC):
    @abstractmethod
    def save(self, route: Route) -> Route: ...
    @abstractmethod
    def find_by_id(self, route_id: str, tenant_id: str) -> Optional[Route]: ...
    @abstractmethod
    def list_by_tenant(self, tenant_id: str, status: Optional[RouteStatus] = None,
                       limit: int = 50) -> List[Route]: ...
    @abstractmethod
    def list_by_driver(self, driver_id: str, tenant_id: str) -> List[Route]: ...


# Legacy interface — used by orders/assign driver flow
class DeliveryDriverRepository(ABC):
    """Legacy interface for DeliveryDriver (entregador) management."""
    @abstractmethod
    def criar(self, driver: DeliveryDriver) -> DeliveryDriver: ...
    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[DeliveryDriver]: ...
    @abstractmethod
    def listar_todos(self) -> List[DeliveryDriver]: ...
    @abstractmethod
    def desativar(self, codigo: str) -> Optional[DeliveryDriver]: ...
    @abstractmethod
    def proximo_codigo(self) -> str: ...
