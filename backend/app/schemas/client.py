from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ClientCreate(BaseModel):
    nome: str
    telefone: str
    telefone_secundario: Optional[str] = None

    rua: str
    numero: str
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    bairro: str

    observacoes: Optional[str] = None


class ClientUpdate(BaseModel):
    nome: str
    telefone: str
    telefone_secundario: Optional[str] = None

    rua: str
    numero: str
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    bairro: str

    observacoes: Optional[str] = None


class ClientResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str

    nome: str
    telefone: str
    telefone_secundario: Optional[str] = None

    rua: str
    numero: str
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    bairro: str

    observacoes: Optional[str] = None

    ativo: bool
    created_at: datetime
    updated_at: datetime