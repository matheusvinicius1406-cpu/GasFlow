"""Purchase Note SQLAlchemy Models — Notas de compra internas (Item 2).

Não é NF-e: documento interno de compra do fornecedor, dá entrada no
estoque na confirmação e serve de base para o PDF de arquivo.
"""

from sqlalchemy import Column, String, Integer, BigInteger, Date, DateTime, ForeignKey, Index, UniqueConstraint, Text
from datetime import datetime

from app.infrastructure.database.base import Base


class PurchaseNoteModel(Base):
    __tablename__ = "purchase_notes"

    __table_args__ = (
        UniqueConstraint("tenant_id", "note_number", name="uq_purchase_notes_tenant_number"),
        Index("idx_purchase_notes_tenant_status", "tenant_id", "status"),
        Index("idx_purchase_notes_supplier", "supplier_name"),
    )

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), nullable=False, default="default", index=True)
    note_number = Column(Integer, nullable=False)  # sequencial por tenant
    supplier_name = Column(String(200), nullable=False)
    supplier_cnpj = Column(String(18), nullable=True)
    issue_date = Column(Date, nullable=False)
    total_cents = Column(BigInteger, nullable=False, default=0)
    observations = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="DRAFT")  # DRAFT | CONFIRMED | CANCELLED
    pdf_path = Column(String(500), nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)


class PurchaseNoteItemModel(Base):
    __tablename__ = "purchase_note_items"

    __table_args__ = (Index("idx_purchase_note_items_note", "purchase_note_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_note_id = Column(String(36), ForeignKey("purchase_notes.id", ondelete="CASCADE"), nullable=False)
    product_codigo = Column(String(50), nullable=False)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price_cents = Column(BigInteger, nullable=False, default=0)
    subtotal_cents = Column(BigInteger, nullable=False, default=0)
