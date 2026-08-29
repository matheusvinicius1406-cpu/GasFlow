"""
Route Persistence Models — SQLAlchemy models for delivery routes.

Replaces in-memory shared_store["routes"] with database persistence.
Routes represent the operational plan for a driver's delivery sequence.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON, Index
)
from datetime import datetime
from app.infrastructure.database.base import Base


class RouteRecord(Base):
    """Persistent route record — replaces in-memory store["routes"]."""
    __tablename__ = "route_records"

    __table_args__ = (
        Index("ix_route_tenant", "tenant_id"),
        Index("ix_route_driver", "driver_id"),
        Index("ix_route_status", "status"),
    )

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", nullable=False)
    driver_id = Column(String(36), nullable=False, default="")
    vehicle_id = Column(String(36), nullable=True)
    status = Column(String(20), nullable=False, default="PLANNED")
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    dispatched_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class RouteStopRecord(Base):
    """Persistent route stop — ordered stop in a route."""
    __tablename__ = "route_stop_records"

    __table_args__ = (
        Index("ix_route_stop_route", "route_id"),
    )

    id = Column(String(36), primary_key=True)
    route_id = Column(String(36), nullable=False)
    delivery_id = Column(String(36), nullable=False, default="")
    sequence = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="PENDING")
    customer_name = Column(String(200), default="")
    customer_phone = Column(String(50), default="")
    address_snapshot = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
