from datetime import datetime

from pydantic import BaseModel


class CompanyCreate(BaseModel):
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    responsavel: str | None = None
    plano: str = "FREE"


class CompanyResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    responsavel: str | None = None
    plano: str
    ativo: bool
    created_at: datetime
    updated_at: datetime
