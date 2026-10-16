"""
Route Persistence Models — SQLAlchemy models for delivery routes.

Replaces in-memory shared_store["routes"] with database persistence.
Routes represent the operational plan for a driver's delivery sequence.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class RouteRecord(Base):
    """Persistent route record — replaces in-memory store["routes"]."""

    __tablename__ = "route_records"

    __table_args__ = (
        Index("ix_route_tenant", "tenant_id"),
        Index("ix_route_driver", "driver_id"),
        Index("ix_route_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", nullable=False)
    driver_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    vehicle_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PLANNED")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RouteStopRecord(Base):
    """Persistent route stop — ordered stop in a route."""

    __tablename__ = "route_stop_records"

    __table_args__ = (Index("ix_route_stop_route", "route_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(36), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    customer_name: Mapped[Optional[str]] = mapped_column(String(200), default="")
    customer_phone: Mapped[Optional[str]] = mapped_column(String(50), default="")
    address_snapshot: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
