from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ProductCreate(BaseModel):
    nome: str
    tipo: str
    preco: float
    estoque: int = 0


class ProductUpdate(BaseModel):
    nome: Optional[str] = None
    tipo: Optional[str] = None
    preco: Optional[float] = None
    estoque: Optional[int] = None
    ativo: Optional[bool] = None


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