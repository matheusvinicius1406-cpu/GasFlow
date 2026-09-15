"""
Product Schemas — Schemas Pydantic para request/response da API de produtos.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ProductCreate(BaseModel):
    nome: str
    tipo: str
    preco: float
    estoque: int = 0
    cartao_habilitado: bool = False
    preco_cartao_1x: Optional[float] = None
    preco_cartao_2x: Optional[float] = None


class ProductUpdate(BaseModel):
    nome: Optional[str] = None
    tipo: Optional[str] = None
    preco: Optional[float] = None
    estoque: Optional[int] = None
    ativo: Optional[bool] = None
    cartao_habilitado: Optional[bool] = None
    preco_cartao_1x: Optional[float] = None
    preco_cartao_2x: Optional[float] = None


class ProductResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    tipo: str
    preco: float
    estoque: int
    ativo: bool
    cartao_habilitado: bool = False
    preco_cartao_1x: Optional[float] = None
    preco_cartao_2x: Optional[float] = None
    created_at: datetime
    updated_at: datetime
