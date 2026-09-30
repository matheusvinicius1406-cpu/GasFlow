"""Job persistido do renomeador de contatos — Fase 2, etapa 8.

O renomeador em lote não cabe num request só: o nginx corta em 30 s
(`frontend/nginx.conf`) e o geocode frio paga ~1 s/rua (política do Nominatim
público, ADR-0004). O padrão do repo para isso é **bounded-batch**: o cliente
cria o job, chama `process` repetidamente e cada chamada fica abaixo do
timeout.

A tabela guarda o **cursor keyset** (último item processado) — é o que torna o
job retomável sem reprocessar: o banco não é apagado durante o passe, então
`codigo > cursor` (GEOCODE/APPLY) e `id > cursor` (OVERPASS) são estáveis.

`regra` guarda o dict serializável do renomeador (APPLY); `filtro`, a seleção
(`search`/`bairro`/`status`); `metrica`, os números do passe Overpass (§8.5).
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base

# Tipos aceitos (espelham os jobs do §5/§8).
TIPO_GEOCODE = "GEOCODE"
TIPO_OVERPASS = "OVERPASS"
TIPO_APPLY = "APPLY"

# Ciclo de vida: PENDENTE → PROCESSANDO → CONCLUIDO | FALHOU.
STATUS_PENDENTE = "PENDENTE"
STATUS_PROCESSANDO = "PROCESSANDO"
STATUS_CONCLUIDO = "CONCLUIDO"
STATUS_FALHOU = "FALHOU"


class ContactJobModel(Base):
    __tablename__ = "contact_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDENTE, nullable=False, index=True)
    # Cursor keyset: último `codigo` (GEOCODE/APPLY) ou `id` (OVERPASS) visto.
    cursor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    regra: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    filtro: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alterados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Métrica do passe Overpass (§8.5/§8.8.5) — % de âncoras/cruzamentos.
    metrica: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    erro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
