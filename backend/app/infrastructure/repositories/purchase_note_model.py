"""Purchase Note SQLAlchemy Models — Notas de compra internas (Item 2).

Não é NF-e: documento interno de compra do fornecedor, dá entrada no
estoque na confirmação e serve de base para o PDF de arquivo.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class PurchaseNoteModel(Base):
    __tablename__ = "purchase_notes"

    __table_args__ = (
        UniqueConstraint("tenant_id", "note_number", name="uq_purchase_notes_tenant_number"),
        Index("idx_purchase_notes_tenant_status", "tenant_id", "status"),
        Index("idx_purchase_notes_supplier", "supplier_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default", index=True)
    note_number: Mapped[int] = mapped_column(Integer, nullable=False)  # sequencial por tenant
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_cnpj: Mapped[Optional[str]] = mapped_column(String(18), nullable=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")  # DRAFT | CONFIRMED | CANCELLED
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PurchaseNoteItemModel(Base):
    __tablename__ = "purchase_note_items"

    __table_args__ = (Index("idx_purchase_note_items_note", "purchase_note_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_note_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("purchase_notes.id", ondelete="CASCADE"), nullable=False
    )
    product_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
