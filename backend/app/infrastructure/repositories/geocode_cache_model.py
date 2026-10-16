"""Cache de geocoding por RUA — ADR-0004 (Fase 2 §6/§7).

Global, sem `tenant_id`: é dado público do OSM — o mesmo logradouro tem as
mesmas coordenadas para todos os tenants (a chave é o hash normalizado de
`rua|bairro|cidade|uf`).

`intersecoes` guarda as vias que cruzam o logradouro com o número de casa do
cruzamento (JSON). O "entre A e B" **não** é gravado pronto: ele é derivado por
contato em `application/contacts/geocoding.py`, porque depende do número
(ADR-0004/D12).

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class GeocodeCacheModel(Base):
    __tablename__ = "geocode_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chave: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rua: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bairro: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cidade: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    uf: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    cep: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # `none_as_null=True`: sem isto o SQLAlchemy grava `None` como JSON `null`
    # (a string), e o passe Overpass (etapa 8) — que seleciona
    # `intersecoes IS NULL` como "rua ainda não processada" — nunca casaria.
    # Com a flag, `None` vira SQL NULL de verdade e a coluna é o marcador.
    intersecoes: Mapped[Optional[Any]] = mapped_column(JSON(none_as_null=True), nullable=True)
    # Quem preencheu `intersecoes` (D23/Fase 3): `ibge` | `overpass` | NULL.
    # `provider` acima é o provedor do GEOCODE (lat/lng) e nunca muda por
    # causa do passe — são duas origens diferentes e a triagem separa as duas.
    # Gravado junto de `intersecoes` no mesmo UPDATE (§8.4 revisado).
    intersecoes_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    criado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
