from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel

OrderStatus = Literal[
    "PENDING",
    "CONFIRMED",
    "PREPARING",
    "DELIVERING",
    "DELIVERED",
    "CANCELLED",
]


class OrderCreate(BaseModel):
    client_codigo: str
    product: str
    quantity: int = 1
    payment_method: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class AssignDriverRequest(BaseModel):
    delivery_driver_codigo: str


class OrderResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    client_codigo: str
    product: str
    quantity: int
    value: float
    address_snapshot: str
    status: str
    payment_method: Optional[str] = None
    delivery_driver_codigo: Optional[str] = None
    created_at: datetime