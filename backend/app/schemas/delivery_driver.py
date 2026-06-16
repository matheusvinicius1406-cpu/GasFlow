from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DeliveryDriverCreate(BaseModel):
    nome: str
    telefone: str
    placa: Optional[str] = None


class DeliveryDriverResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    telefone: str
    placa: Optional[str] = None
    ativo: bool
    created_at: datetime