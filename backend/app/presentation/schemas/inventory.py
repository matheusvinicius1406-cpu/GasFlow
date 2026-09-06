"""
Inventory Schemas — Schemas Pydantic para request/response da API de inventário.

FASE 7: Inventory Core.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ── Stock Movement ────────────────────────────────────────


class StockMovementResponse(BaseModel):
    """Response de um movimento de estoque."""

    model_config = {"from_attributes": True}

    id: int
    product_codigo: str
    type: str
    quantity: int
    reason: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    balance_before: int
    balance_after: int
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


class StockMovementListResponse(BaseModel):
    """Response paginado de movimentações."""

    items: List[StockMovementResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Inventory ─────────────────────────────────────────────


class InventoryResponse(BaseModel):
    """Response de inventário de um produto."""

    model_config = {"from_attributes": True}

    product_codigo: str
    quantity: int
    minimum_quantity: int
    maximum_quantity: Optional[int] = None
    stock_status: str  # IN_STOCK, LOW_STOCK, OUT_OF_STOCK
    available_quantity: int
    updated_at: Optional[datetime] = None


class InventoryListResponse(BaseModel):
    """Response de lista de inventário."""

    items: List[InventoryResponse]
    total: int


# ── Stock Operations ──────────────────────────────────────


class StockEntryRequest(BaseModel):
    """Request para entrada de estoque."""

    quantity: int = Field(..., gt=0, description="Quantidade a entrar")
    reason: str = Field("Entrada de estoque", description="Motivo da entrada")


class StockAdjustRequest(BaseModel):
    """Request para ajuste de estoque."""

    new_quantity: int = Field(..., ge=0, description="Nova quantidade (contagem física)")
    reason: str = Field("Ajuste de inventário", description="Motivo do ajuste")


class StockLossRequest(BaseModel):
    """Request para registrar perda de estoque."""

    quantity: int = Field(..., gt=0, description="Quantidade perdida")
    reason: str = Field(..., min_length=1, description="Motivo da perda (obrigatório)")


class SetMinimumRequest(BaseModel):
    """Request para definir estoque mínimo."""

    minimum_quantity: int = Field(..., ge=0, description="Quantidade mínima")


class StockOperationResponse(BaseModel):
    """Response de operação de estoque."""

    inventory: InventoryResponse
    movement: Optional[StockMovementResponse] = None


# ── Product with Inventory (joined) ──────────────────────


class ReconciliationResponse(BaseModel):
    """Response de reconciliação inventory/ledger."""

    product_codigo: str
    inventory_quantity: Optional[int] = None
    ledger_balance: Optional[int] = None
    match: Optional[bool] = None
    status: str  # MATCH, MISMATCH, NO_INVENTORY


class ProductInventoryResponse(BaseModel):
    """Response de produto com dados de inventário."""

    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    tipo: str
    preco: float
    ativo: bool
    quantity: int
    minimum_quantity: int
    stock_status: str
