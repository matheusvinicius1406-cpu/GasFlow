from pydantic import BaseModel
from typing import Optional


class OrderCreate(BaseModel):
    client_codigo: str
    product: str
    quantity: int = 1
    payment_method: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: str


class AssignDriverRequest(BaseModel):
    delivery_driver_codigo: str


class OrderResponse(BaseModel):
    codigo: str
    client_codigo: str
    product: str
    quantity: int
    value: float
    address_snapshot: str
    status: str
    payment_method: Optional[str] = None
    delivery_driver_codigo: Optional[str] = None