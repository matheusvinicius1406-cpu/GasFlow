from pydantic import BaseModel
from typing import Optional


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
    codigo: str
    nome: str
    tipo: str
    preco: float
    estoque: int
    ativo: bool