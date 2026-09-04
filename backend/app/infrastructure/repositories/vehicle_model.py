"""
Vehicle SQLAlchemy Models — Persistent vehicle, capacity, and load data.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class VehicleModel(Base):
    __tablename__ = "vehicles"

    __table_args__ = (
        UniqueConstraint("tenant_id", "plate", name="uq_vehicle_tenant_plate"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, default="default", index=True)
    plate = Column(String, nullable=False)
    model = Column(String, nullable=False)
    vehicle_type = Column(String, default="VAN")
    capacity_total = Column(Integer, default=0)
    status = Column(String, default="AVAILABLE")
    assigned_driver_id = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VehicleCapacityModel(Base):
    __tablename__ = "vehicle_capacities"

    __table_args__ = (
        UniqueConstraint("vehicle_id", "product_codigo", name="uq_capacity_vehicle_product"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, default="default", index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    product_codigo = Column(String, nullable=False)
    product_name = Column(String, default="")
    max_capacity = Column(Integer, default=0)
    unit = Column(String, default="UNITS")
    created_at = Column(DateTime, default=datetime.utcnow)


class VehicleLoadModel(Base):
    __tablename__ = "vehicle_loads"

    __table_args__ = (
        UniqueConstraint("vehicle_id", "product_codigo", name="uq_load_vehicle_product"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, default="default", index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    product_codigo = Column(String, nullable=False)
    loaded = Column(Integer, default=0)
    reserved = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
