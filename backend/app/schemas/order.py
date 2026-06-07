from pydantic import BaseModel
from typing import Optional


class OrderCreate(BaseModel):
    client_codigo: str
    product: str
    quantity: int = 1
    payment_method: Optional[str] = None


class OrderResponse(BaseModel):
    codigo: str
    client_codigo: str
    product: str
    quantity: int
    value: float
    address_snapshot: str
    status: str