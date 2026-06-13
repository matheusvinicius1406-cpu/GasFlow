from pydantic import BaseModel
from typing import Optional


class DeliveryDriverCreate(BaseModel):
    nome: str
    telefone: str
    placa: Optional[str] = None


class DeliveryDriverResponse(BaseModel):
    codigo: str
    nome: str
    telefone: str
    placa: Optional[str] = None
    ativo: bool