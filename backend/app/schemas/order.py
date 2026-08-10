from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

OrderStatus = Literal[
    "PENDING",
    "CONFIRMED",
    "PREPARING",
    "DELIVERING",
    "DELIVERED",
    "CANCELLED",
]


class OrderItemCreate(BaseModel):
    product: str  # código do produto
    quantity: int = Field(default=1, ge=1)


class OrderCreate(BaseModel):
    client_codigo: str
    items: list[OrderItemCreate] = Field(min_length=1)
    payment_method: str | None = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class AssignDriverRequest(BaseModel):
    delivery_driver_codigo: str


class OrderItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    product_codigo: str
    product_nome: str
    quantity: int
    unit_price: float
    subtotal: float


class OrderResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    client_codigo: str
    items: list[OrderItemResponse]
    value: float
    address_snapshot: str
    status: str
    payment_method: str | None = None
    delivery_driver_codigo: str | None = None
    created_at: datetime


class OrderStatusHistoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    from_status: str | None = None
    to_status: str
    created_at: datetime
