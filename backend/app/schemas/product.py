from datetime import datetime

from pydantic import BaseModel


class ProductCreate(BaseModel):
    nome: str
    tipo: str
    preco: float
    estoque: int = 0


class ProductUpdate(BaseModel):
    nome: str | None = None
    tipo: str | None = None
    preco: float | None = None
    estoque: int | None = None
    ativo: bool | None = None


class ProductResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    tipo: str
    preco: float
    estoque: int
    ativo: bool
    created_at: datetime
    updated_at: datetime