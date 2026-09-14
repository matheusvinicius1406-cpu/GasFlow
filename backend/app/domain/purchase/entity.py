"""Purchase Domain Entities — Notas de Compra internas (sem SEFAZ).

Documentam a compra do fornecedor de gás (ex.: "Marcos Gás, CNPJ ...,
compra do dia ..."), dão entrada no estoque na confirmação e podem ser
exportadas em PDF para arquivo do dono.

Regras de negócio:
- Status: DRAFT → CONFIRMED | CANCELLED (só DRAFT pode ser cancelada)
- CONFIRMED entra estoque (ENTRY) em transação atômica, idempotente por
  (reference_type='purchase_note', reference_id, product_codigo, ENTRY)
- note_number é sequencial POR TENANT
- CONFIRMED é imutável (edição só em DRAFT); devolução pós-confirmação
  é nota de devolução (futuro — fora do escopo)
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class PurchaseNoteStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


@dataclass
class PurchaseNoteItem:
    """Item de uma nota de compra (produto + quantidade + preço)."""

    id: Optional[int] = None
    purchase_note_id: str = ""
    product_codigo: str = ""
    product_name: str = ""
    quantity: int = 0
    unit_price_cents: int = 0
    subtotal_cents: int = 0

    def __post_init__(self):
        if not self.product_codigo:
            raise ValueError("product_codigo é obrigatório")
        if self.quantity <= 0:
            raise ValueError("quantity deve ser maior que 0")
        if self.unit_price_cents < 0:
            raise ValueError("unit_price_cents não pode ser negativo")
        if self.subtotal_cents <= 0:
            self.subtotal_cents = self.quantity * self.unit_price_cents


@dataclass
class PurchaseNote:
    """Nota de compra interna de fornecedor (não é NF-e / não vai à SEFAZ)."""

    id: str = ""
    tenant_id: str = "default"
    note_number: int = 0  # sequencial por tenant (1, 2, 3…)
    supplier_name: str = ""
    supplier_cnpj: Optional[str] = None
    issue_date: Optional[date] = None
    total_cents: int = 0
    observations: Optional[str] = None
    status: PurchaseNoteStatus = PurchaseNoteStatus.DRAFT
    pdf_path: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    items: list = field(default_factory=list)

    def __post_init__(self):
        if not self.supplier_name or not self.supplier_name.strip():
            raise ValueError("supplier_name é obrigatório")
        if self.total_cents < 0:
            raise ValueError("total_cents não pode ser negativo")

    @property
    def is_draft(self) -> bool:
        return self.status == PurchaseNoteStatus.DRAFT

    @property
    def is_confirmed(self) -> bool:
        return self.status == PurchaseNoteStatus.CONFIRMED

    def recalculate_total(self) -> int:
        """Total = soma dos subtotais dos itens (em centavos)."""
        self.total_cents = sum(i.subtotal_cents for i in self.items)
        return self.total_cents

    def can_transition_to(self, new_status: PurchaseNoteStatus) -> bool:
        """DRAFT → CONFIRMED | CANCELLED. Terminais não transicionam."""
        if self.status == PurchaseNoteStatus.DRAFT:
            return new_status in (PurchaseNoteStatus.CONFIRMED, PurchaseNoteStatus.CANCELLED)
        return False
