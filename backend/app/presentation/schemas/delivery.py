"""
DeliveryDriver Schemas — Schemas Pydantic para request/response da API de entregadores.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DeliveryDriverCreate(BaseModel):
    nome: str
    telefone: str
    placa: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class DeliveryDriverResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    telefone: str
    placa: Optional[str] = None
    ativo: bool
    username: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
