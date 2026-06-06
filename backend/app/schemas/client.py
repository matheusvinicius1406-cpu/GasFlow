from pydantic import BaseModel
from typing import Optional


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


class ClientResponse(BaseModel):
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