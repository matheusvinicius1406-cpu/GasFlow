"""
Client Schemas — Schemas Pydantic para request/response da API de clientes.

FASE 6: Adicionado tipo, email, paginação e Customer 360.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    nome: str = Field(..., min_length=1)
    telefone: str = Field(..., min_length=1)
    telefone_secundario: Optional[str] = None
    rua: str = Field(..., min_length=1)
    numero: str = Field(..., min_length=1)
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    bairro: str = Field(..., min_length=1)
    observacoes: Optional[str] = None
    tipo: Optional[str] = None
    email: Optional[str] = None


class ClientUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1)
    telefone: Optional[str] = Field(None, min_length=1)
    telefone_secundario: Optional[str] = None
    rua: Optional[str] = Field(None, min_length=1)
    numero: Optional[str] = Field(None, min_length=1)
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    bairro: Optional[str] = Field(None, min_length=1)
    observacoes: Optional[str] = None
    tipo: Optional[str] = None
    email: Optional[str] = None


class ClientResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    telefone: str
    telefone_secundario: Optional[str] = None
    rua: str
    numero: str
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    bairro: str
    observacoes: Optional[str] = None
    ativo: bool
    tipo: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    """Response paginado para listagem de clientes."""

    items: List[ClientResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class Customer360Response(BaseModel):
    """Response do Customer 360 — visão consolidada."""

    # Identity
    codigo: str
    nome: str
    telefone: str
    telefone_secundario: Optional[str] = None
    email: Optional[str] = None
    tipo: Optional[str] = None
    ativo: bool

    # Address
    rua: str
    numero: str
    bairro: str
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    observacoes: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # CRM Metrics (derived from orders)
    total_orders: int = 0
    total_spent: float = 0.0
    average_ticket: float = 0.0
    first_order_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
    days_since_last_order: Optional[int] = None
    favorite_product: Optional[str] = None

    # FASE 8: Financial metrics (derived from Payment/Receivable)
    paid_amount: float = 0.0
    outstanding_balance: float = 0.0
    pending_amount: float = 0.0
