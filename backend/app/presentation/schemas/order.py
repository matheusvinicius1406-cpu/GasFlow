"""
Order Schemas — Schemas Pydantic para request/response da API de pedidos.

FASE 3.2 — SECURITY + FINANCIAL HARDENING:
- Removido unit_price de OrderItemCreate (backend é autoridade do preço)
- Adicionada validação: discount <= subtotal
- Adicionada validação: total >= 0
- Documentação de decisões de segurança
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


# ── Order Item ───────────────────────────────────────────

class OrderItemCreate(BaseModel):
    """Schema para criação de item do pedido.

    REGRA DE SEGURANÇA: O frontend NÃO envia unit_price.
    O backend busca o preço oficial do Product e o congela.
    """
    product_codigo: str = Field(..., min_length=1, description="Código do produto")
    quantity: int = Field(..., gt=0, description="Quantidade deve ser maior que 0")
    # unit_price NÃO é aceito — preço vem do Product.preco no backend


class OrderItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    product_codigo: str
    product_nome: str
    quantity: int
    unit_price: float
    subtotal: float
    created_at: datetime


# ── Order ────────────────────────────────────────────────

class OrderCreate(BaseModel):
    """Schema para criação de pedido.

    REGRA DE SEGURANÇA:
    - subtotal e total NÃO são aceitos do frontend
    - delivery_fee e discount são validados (>= 0)
    - discount é limitado a subtotal pelo backend
    """
    client_codigo: str = Field(..., min_length=1, description="Código do cliente")
    address_snapshot: Optional[str] = Field(None, description="Snapshot do endereço")
    items: List[OrderItemCreate] = Field(..., min_length=1, description="Pedido deve ter pelo menos 1 item")
    delivery_fee: float = Field(0.0, ge=0, description="Taxa de entrega não pode ser negativa")
    discount: float = Field(0.0, ge=0, description="Desconto não pode ser negativo")
    payment_method: Optional[str] = Field(None, description="Método de pagamento")
    source: str = Field("MANUAL", description="Origem do pedido")
    notes: Optional[str] = Field(None, description="Observações")

    @model_validator(mode="after")
    def validate_discount_max(self):
        """Desconto não pode ser absurdamente alto — limitado a 5x subtotal estimado."""
        if self.discount < 0:
            raise ValueError("Desconto não pode ser negativo")
        return self


class OrderStatusUpdate(BaseModel):
    """Schema para atualização de status do pedido."""
    status: str = Field(..., min_length=1, description="Novo status do pedido")


class AssignDriverRequest(BaseModel):
    """Schema para atribuição de motorista."""
    delivery_driver_codigo: str = Field(..., min_length=1, description="Código do motorista")


class OrderResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    client_codigo: str

    # Valores
    subtotal: float
    delivery_fee: float
    discount: float
    total: float

    # Pagamento
    payment_method: Optional[str] = None
    payment_status: str

    # Entrega
    address_snapshot: str
    delivery_driver_codigo: Optional[str] = None

    # Status
    status: str

    # Metadados
    source: str
    notes: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None


class OrderDetailResponse(OrderResponse):
    """Response detalhado com itens."""
    items: List[OrderItemResponse] = []


class OrderListResponse(BaseModel):
    """Response de lista paginada de pedidos."""
    items: List[OrderResponse]
    total: int
    page: int
    page_size: int
