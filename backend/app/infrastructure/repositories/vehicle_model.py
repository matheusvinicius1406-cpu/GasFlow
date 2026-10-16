"""
Vehicle SQLAlchemy Models — Persistent vehicle, capacity, and load data.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class VehicleModel(Base):
    __tablename__ = "vehicles"

    __table_args__ = (UniqueConstraint("tenant_id", "plate", name="uq_vehicle_tenant_plate"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    plate: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    vehicle_type: Mapped[Optional[str]] = mapped_column(String, default="VAN")
    capacity_total: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    status: Mapped[Optional[str]] = mapped_column(String, default="AVAILABLE")
    assigned_driver_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VehicleCapacityModel(Base):
    __tablename__ = "vehicle_capacities"

    __table_args__ = (UniqueConstraint("vehicle_id", "product_codigo", name="uq_capacity_vehicle_product"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    vehicle_id: Mapped[int] = mapped_column(Integer, ForeignKey("vehicles.id"), nullable=False)
    product_codigo: Mapped[str] = mapped_column(String, nullable=False)
    product_name: Mapped[Optional[str]] = mapped_column(String, default="")
    max_capacity: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    unit: Mapped[Optional[str]] = mapped_column(String, default="UNITS")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)


class VehicleLoadModel(Base):
    __tablename__ = "vehicle_loads"

    __table_args__ = (UniqueConstraint("vehicle_id", "product_codigo", name="uq_load_vehicle_product"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    vehicle_id: Mapped[int] = mapped_column(Integer, ForeignKey("vehicles.id"), nullable=False)
    product_codigo: Mapped[str] = mapped_column(String, nullable=False)
    loaded: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    reserved: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
