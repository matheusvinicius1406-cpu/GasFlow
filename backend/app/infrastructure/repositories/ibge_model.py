"""Dados oficiais do IBGE — CNEFE + Faces de Logradouro (Fase 3, ADR-0008).

Duas fontes do Censo 2022 resolvem o que o OSM não tem em Belém:

- **CNEFE** dá ``número ↔ coordenada`` — a âncora de numeração que o
  ``addr:housenumber`` do OSM não cobre (Rodovia Augusto Montenegro: **0** no
  OSM, **8.668** no CNEFE — spike do ADR-0008).
- **Faces de Logradouro** dá o ``segmento entre dois nós`` — de onde sai o
  cruzamento, sem query no Overpass.

Global, **sem ``tenant_id``**, como o ``geocode_cache``: é dado público de
estatística oficial, o mesmo para todos os tenants.

``chave_logradouro`` e ``chave_nome`` guardam a forma **normalizada**
(``app.core.texto.normalizar``), não o hash: o hash viraria dependência de
``application`` (inversão de dependência) e o texto legível serve de debug.
``chave_nome`` fica sem o tipo (``RUA``/``TRAVESSA``) para casar
``"Ivan Leão"`` (cache) contra ``"Passagem Ivan Leão"`` (CNEFE) nas duas
direções — D27.

``num_quadra``/``num_face`` são **Integer** nos dois lados: o CNEFE grava
``"3"`` e as Faces ``"001"``, e guardar inteiro resolve o ``zfill(3)`` do
D17 na hora da junção, não na hora da query.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class CnefeEnderecoModel(Base):
    """Um endereço do CNEFE (uma linha do CSV municipal)."""

    __tablename__ = "cnefe_endereco"
    __table_args__ = (
        # Idempotência da ingestão: re-rodar o script não duplica (D18).
        UniqueConstraint("cod_municipio", "cod_unico_endereco", name="uq_cnefe_endereco_chave"),
        # Onde o provider procura as âncoras de UMA rua.
        Index("ix_cnefe_endereco_municipio_logradouro", "cod_municipio", "chave_logradouro"),
        # Junção com as Faces (D17) — feita na ingestão/auditoria.
        Index("ix_cnefe_endereco_face", "cod_setor", "num_quadra", "num_face"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cod_municipio: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    cod_unico_endereco: Mapped[str] = mapped_column(String(30), nullable=False)
    cod_setor: Mapped[str] = mapped_column(String(20), nullable=False)
    # Zero-padding normalizado para inteiro (D17) — casa com CD_QUADRA/CD_FACE.
    num_quadra: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_face: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # `None` quando o número não é numérico (ex.: "s/n") — nunca vira âncora.
    num_endereco: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chave_logradouro: Mapped[str] = mapped_column(String(128), nullable=False)
    chave_nome: Mapped[str] = mapped_column(String(128), nullable=False)
    nome_logradouro: Mapped[str] = mapped_column(String(160), nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cep: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    # Qualidade da coordenada do IBGE (1 = porta). O filtro é teste, não achismo.
    nv_geo_coord: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)


class LogradouroFaceModel(Base):
    """Um segmento de logradouro — o "face" do IBGE.

    ``geom`` guarda a polilinha COMPLETA ``[[lat, lng], ...]``, arredondada a 6
    casas: é o que ``axis.juntar_segmentos`` costura para virar o eixo e o que
    ``axis.projetar_no_eixo`` projeta. Medido na ingestão, **22% das faces têm
    mais de 2 pontos** (até 104), então um par de extremidades sozinho teria
    jogado fora a forma de 10.460 faces e projetado por uma corda.

    As extremidades ``geom[0]``/``geom[-1]`` é que definem o cruzamento: nó
    compartilhado com face de OUTRA rua = cruzamento (D16) — materializado em
    ``logradouro_no``.
    """

    __tablename__ = "logradouro_face"
    __table_args__ = (
        Index("ix_logradouro_face_municipio_logradouro", "cod_municipio", "chave_logradouro"),
        Index("ix_logradouro_face_face", "cod_setor", "cod_quadra", "cod_face"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cod_municipio: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    cod_setor: Mapped[str] = mapped_column(String(20), nullable=False)
    cod_quadra: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cod_face: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chave_logradouro: Mapped[str] = mapped_column(String(128), nullable=False)
    # Pode ser vazia: 19,6% das faces de Belém não têm nome (medido).
    nome_logradouro: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    # Polilinha [[lat, lng], ...] (JSON) — sem PostGIS, sem coluna geométrica.
    geom: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tot_res: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tot_geral: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class LogradouroNoModel(Base):
    """Extremo de uma face, já arredondado — a chave de coincidência de nó.

    Dois nós de logradouros DIFERENTES com a mesma coordenada = cruzamento
    (D16). Arredondado a 6 casas no import, igual ao spike.
    """

    __tablename__ = "logradouro_no"
    __table_args__ = (
        UniqueConstraint(
            "cod_municipio",
            "node_lat",
            "node_lng",
            "chave_logradouro",
            name="uq_logradouro_no",
        ),
        Index("ix_logradouro_no_municipio_logradouro", "cod_municipio", "chave_logradouro"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cod_municipio: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    node_lat: Mapped[float] = mapped_column(Float, nullable=False)
    node_lng: Mapped[float] = mapped_column(Float, nullable=False)
    chave_logradouro: Mapped[str] = mapped_column(String(128), nullable=False)
    nome_logradouro: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
