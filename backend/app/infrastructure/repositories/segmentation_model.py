"""
Segmentation SQLAlchemy Model — FASE 13.1

Persists segments and their rules to database.
Rules are stored as JSON for flexibility.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from datetime import datetime
from app.infrastructure.database.base import Base


class SegmentModel(Base):
    __tablename__ = "segments"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    rules_json = Column(Text, nullable=False, default="[]")  # JSON array of rules
    rule_logic = Column(String(10), default="AND")  # AND or OR
    status = Column(String(20), default="DRAFT")  # DRAFT, ACTIVE, ARCHIVED
    member_count = Column(Integer, default=0)
    last_evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_segments_status", "status"),
        Index("ix_segments_tenant_status", "tenant_id", "status"),
    )
