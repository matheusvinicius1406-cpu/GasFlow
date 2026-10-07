"""Métricas locais da Fase 3 (spec §10) — teste com fixture pequena.

O script `scripts/metrica_cobertura_fase3.py` é o que alimenta o ADR-0008
com os números de população inteira (âncoras, cruzamentos, junção D17).
Aqui se trava cada definição contra uma base mínima montada na mão:

- `âncora` = número **> 0** + coordenada (número 0 não ancora);
- `cruzamento` = nó (extremidade de face, 6 casas) tocado por **>= 2 ruas**;
- `faces_com_2_extremos_cruzados` = os DOIS extremos da face são cruzamento;
- `ruas_com_2_cruzamentos` = a rua toca >= 2 nós de cruzamento;
- junção D17 = `(cod_setor, num_quadra, num_face)` — só casam as linhas
  cuja quadra/face existe na tabela de faces.

Fixture (três faces de três ruas, um "H"):

    rua C (face 3)          rua B (face 2)
        E1 ─────────────────── E2
                rua A (face 1)

E1 e E2 são tocados por 2 ruas => cruzamentos; a face 1 tem os DOIS
extremos cruzados; só a rua A toca 2 cruzamentos.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.infrastructure.repositories.ibge_model import (
    CnefeEnderecoModel,
    LogradouroFaceModel,
    LogradouroNoModel,
)

_MUN = "1501402"
_SETOR = "150140260000001"
_SETOR_C = "150140260000002"
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "metrica_cobertura_fase3.py"

_E1 = (-1.3062, -48.473)
_E2 = (-1.3066, -48.473)
_E3 = (-1.3070, -48.473)  # extremo só da rua C (não é cruzamento)


def _carregar_script():
    spec = importlib.util.spec_from_file_location("metrica_cobertura_fase3", _SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def _semear(engine) -> None:
    with engine.begin() as conn:
        # Rua A: 3 âncoras (>=2). Rua B: 1 âncora. Rua C: 1 linha de número 0
        # (não ancora) + 1 âncora real.
        linhas = [
            # (chave, nome, setor, quadra, face, numero, lat, lng)
            ("rua a", "RUA A", _SETOR, 1, 1, 45, -1.3062, -48.473),
            ("rua a", "RUA A", _SETOR, 1, 1, 50, -1.3063, -48.473),
            ("rua a", "RUA A", _SETOR, 1, 1, 55, -1.3064, -48.473),
            ("rua b", "RUA B", _SETOR, 2, 1, 10, -1.3065, -48.473),
            ("rua c", "RUA C", _SETOR_C, None, None, 0, -1.3070, -48.473),
            ("rua c", "RUA C", _SETOR_C, None, None, 7, -1.3071, -48.473),
        ]
        for chave, nome, setor, quadra, face, numero, lat, lng in linhas:
            conn.execute(
                CnefeEnderecoModel.__table__.insert(),
                {
                    "cod_municipio": _MUN,
                    "cod_unico_endereco": f"{chave}-{numero}",
                    "cod_setor": setor,
                    "num_quadra": quadra,
                    "num_face": face,
                    "num_endereco": numero,
                    "chave_logradouro": chave,
                    "chave_nome": chave,
                    "nome_logradouro": nome,
                    "lat": lat,
                    "lng": lng,
                },
            )

        faces = [
            # (chave, setor, quadra, face, geom)
            ("rua a", _SETOR, 1, 1, [_E1, _E2]),
            ("rua b", _SETOR, 2, 1, [_E2, (-1.3066, -48.474)]),
            ("rua c", _SETOR_C, None, None, [_E3, _E1]),
        ]
        for chave, setor, quadra, face, geom in faces:
            conn.execute(
                LogradouroFaceModel.__table__.insert(),
                {
                    "cod_municipio": _MUN,
                    "cod_setor": setor,
                    "cod_quadra": quadra,
                    "cod_face": face,
                    "chave_logradouro": chave,
                    "nome_logradouro": chave.upper(),
                    "geom": [list(p) for p in geom],
                },
            )
            for lat, lng in (geom[0], geom[-1]):
                conn.execute(
                    LogradouroNoModel.__table__.insert(),
                    {
                        "cod_municipio": _MUN,
                        "node_lat": lat,
                        "node_lng": lng,
                        "chave_logradouro": chave,
                        "nome_logradouro": chave.upper(),
                    },
                )


@pytest.fixture()
def relatorio(tmp_path):
    modulo = _carregar_script()
    caminho = tmp_path / "metricas.db"
    engine = create_engine(f"sqlite:///{caminho.as_posix()}")
    for tabela in (CnefeEnderecoModel.__table__, LogradouroFaceModel.__table__, LogradouroNoModel.__table__):
        tabela.create(bind=engine)
    _semear(engine)
    engine.dispose()
    # amostra=0: o passe local (provider) não roda aqui — é provider, não contagem.
    return modulo.medir(f"sqlite:///{caminho.as_posix()}", _MUN, amostra=0, seed=42)


def test_ancoras_contam_so_numero_positivo(relatorio):
    # 6 endereços; o de número 0 (rua C) não ancora.
    assert relatorio["enderecos"] == 6
    assert relatorio["enderecos_ancora"] == 5
    assert relatorio["enderecos_ancora_pct"] == 83.3


def test_ruas_com_duas_ancoras(relatorio):
    assert relatorio["ruas_com_ancora"] == 3
    assert relatorio["ruas_com_2_ancoras"] == 1, "só a rua A tem >=2 âncoras"
    assert relatorio["ruas_com_2_ancoras_pct"] == 33.3


def test_juncao_d17_so_casa_com_face_existente(relatorio):
    # Rua A (3) + rua B (1) casam; rua C tem quadra/face NULL e não casa.
    assert relatorio["enderecos_casados_face"] == 4
    assert relatorio["enderecos_casados_face_pct"] == 66.7


def test_cruzamentos_e_extremos(relatorio):
    assert relatorio["nos_distintos"] == 4
    assert relatorio["nos_cruzamento"] == 2, "E1 e E2 têm 2 ruas; E3 e o extremo de B não"

    assert relatorio["faces"] == 3
    assert relatorio["faces_com_2_extremos_cruzados"] == 1, "só a face da rua A"
    assert relatorio["faces_com_2_extremos_cruzados_pct"] == 33.3

    assert relatorio["ruas_faces"] == 3
    assert relatorio["ruas_com_2_cruzamentos"] == 1, "só a rua A toca E1 e E2"
    assert relatorio["ruas_com_2_cruzamentos_pct"] == 33.3


def test_sem_amostra_nao_roda_passe_local(relatorio):
    assert "passe_local" not in relatorio
