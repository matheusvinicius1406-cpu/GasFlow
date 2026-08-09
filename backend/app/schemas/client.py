from datetime import datetime

from pydantic import BaseModel


class ClientCreate(BaseModel):
    nome: str
    telefone: str
    telefone_secundario: str | None = None

    rua: str
    numero: str
    complemento: str | None = None
    referencia: str | None = None
    bairro: str

    observacoes: str | None = None


class ClientUpdate(BaseModel):
    nome: str
    telefone: str
    telefone_secundario: str | None = None

    rua: str
    numero: str
    complemento: str | None = None
    referencia: str | None = None
    bairro: str

    observacoes: str | None = None


class ClientResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str

    nome: str
    telefone: str
    telefone_secundario: str | None = None

    rua: str
    numero: str
    complemento: str | None = None
    referencia: str | None = None
    bairro: str

    observacoes: str | None = None

    ativo: bool
    created_at: datetime
    updated_at: datetime