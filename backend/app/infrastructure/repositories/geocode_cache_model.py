"""Cache de geocoding por RUA — ADR-0004 (Fase 2 §6/§7).

Global, sem `tenant_id`: é dado público do OSM — o mesmo logradouro tem as
mesmas coordenadas para todos os tenants (a chave é o hash normalizado de
`rua|bairro|cidade|uf`).

`intersecoes` guarda as vias que cruzam o logradouro com o número de casa do
cruzamento (JSON). O "entre A e B" **não** é gravado pronto: ele é derivado por
contato em `application/contacts/geocoding.py`, porque depende do número
(ADR-0004/D12).
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from app.infrastructure.database.base import Base


class GeocodeCacheModel(Base):
    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True, index=True)
    chave = Column(String(64), nullable=False, unique=True, index=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    rua = Column(String, nullable=True)
    bairro = Column(String, nullable=True)
    cidade = Column(String, nullable=True)
    uf = Column(String(2), nullable=True)
    cep = Column(String(9), nullable=True)
    provider = Column(String(20), nullable=True)
    # `none_as_null=True`: sem isto o SQLAlchemy grava `None` como JSON `null`
    # (a string), e o passe Overpass (etapa 8) — que seleciona
    # `intersecoes IS NULL` como "rua ainda não processada" — nunca casaria.
    # Com a flag, `None` vira SQL NULL de verdade e a coluna é o marcador.
    intersecoes = Column(JSON(none_as_null=True), nullable=True)
    # Quem preencheu `intersecoes` (D23/Fase 3): `ibge` | `overpass` | NULL.
    # `provider` acima é o provedor do GEOCODE (lat/lng) e nunca muda por
    # causa do passe — são duas origens diferentes e a triagem separa as duas.
    # Gravado junto de `intersecoes` no mesmo UPDATE (§8.4 revisado).
    intersecoes_provider = Column(String(20), nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
