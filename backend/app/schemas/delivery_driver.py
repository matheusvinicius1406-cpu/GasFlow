from datetime import datetime

from pydantic import BaseModel


class DeliveryDriverCreate(BaseModel):
    nome: str
    telefone: str
    placa: str | None = None


class DeliveryDriverResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    telefone: str
    placa: str | None = None
    ativo: bool
    created_at: datetime