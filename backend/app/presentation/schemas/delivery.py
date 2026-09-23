"""
DeliveryDriver Schemas — Schemas Pydantic para request/response da API de entregadores.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DeliveryDriverCreate(BaseModel):
    nome: str
    telefone: str
    placa: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class DeliveryDriverUpdate(BaseModel):
    """Campos editáveis do entregador — atualização parcial.

    `codigo` **não** entra: é a identidade gravada em `delivery_records`,
    `driver_locations` e no histórico de posições. Trocá-lo orfanaria o rastro
    do entregador, então é imutável.

    `extra="forbid"` faz o campo indevido (ex.: `codigo` no corpo) virar **422**
    em vez de ser ignorado em silêncio — o mesmo cuidado que faltava no request
    antigo, que aceitava `vehicle_type` e descartava.
    """

    model_config = {"extra": "forbid"}

    nome: Optional[str] = Field(None, min_length=1)
    telefone: Optional[str] = Field(None, min_length=1)
    placa: Optional[str] = None
    document: Optional[str] = None
    vehicle_id: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(AVAILABLE|BUSY|PAUSED|OFFLINE|INACTIVE|DISABLED)$")


class CreateDriverResponse(BaseModel):
    """Contrato do cadastro canônico de entregador.

    Vive aqui, e não na rota, porque **dois** entrypoints devolvem isto:
    `POST /admin/drivers` (canônico) e `POST /delivery/drivers` (alias) — que
    precisam ter o mesmo efeito e a mesma resposta para não voltarem a
    divergir. A senha temporária existe apenas nesta resposta.
    """

    driver_id: str
    username: str
    temporary_password: str


class DeliveryDriverResponse(BaseModel):
    model_config = {"from_attributes": True}

    codigo: str
    nome: str
    telefone: str
    placa: Optional[str] = None
    document: Optional[str] = None
    vehicle_id: Optional[str] = None
    ativo: bool
    username: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
