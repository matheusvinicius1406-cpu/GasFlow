"""
Lead SQLAlchemy Model — captura pública do site institucional.

Newsletter e pedidos de demonstração. Sem tenant (origem pública).
"""

from sqlalchemy import Column, String, DateTime
from datetime import datetime
from app.infrastructure.database.base import Base


class LeadModel(Base):
    __tablename__ = "site_leads"

    id = Column(String(36), primary_key=True)
    type = Column(String(20), nullable=False, default="LEAD")  # LEAD | DEMO
    email = Column(String(255), nullable=False, index=True)
    name = Column(String(120), nullable=True)
    phone = Column(String(40), nullable=True)
    message = Column(String(2000), nullable=True)
    source = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
