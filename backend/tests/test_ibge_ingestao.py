"""Fase 3, etapas 1-2 (spec §7) — ingestão CNEFE e Faces de Logradouro.

Os dois scripts de carga precisam de teste com fixture pequena antes de rodar
sobre a base real (Belém: 618.075 linhas de CNEFE, 48.159 faces, ~97 MB fora
do repositório). Aqui se trava o que a etapa promete:

- **idempotência** (rodar N vezes deixa a mesma base, D18);
- **escopo por município** (linhas de outro município são ignoradas);
- **deduplicação** por `uq_cnefe_endereco_chave` (o mesmo endereço aparece
  mais de uma vez no CSV do IBGE);
- **nunca inventar**: número não numérico vira `num_endereco = None`;
- **normalização do nome** (`chave_logradouro` com tipo, `chave_nome` sem —
  D27) e **coordenada com vírgula decimal** (publicação real do IBGE);
- **nós de cruzamento**: extremidades compartilhadas por logradouros
  diferentes viram duas linhas de `logradouro_no` na mesma coordenada (D16);
- **GeoJSON em [lng, lat]** convertido para `[lat, lng]` com 6 casas.

Os scripts usam `DATABASE_URL` lida no import, então o módulo é carregado por
`importlib` com a variável apontando para um SQLite temporário do `tmp_path`.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.infrastructure.repositories.ibge_model import (
    CnefeEnderecoModel,
    LogradouroFaceModel,
    LogradouroNoModel,
)

_MUN = "1501402"  # Belém (D11)
_OUTRO = "1500103"
_SETOR = "150140260000001"
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

_CNEFE_COLUNAS = [
    "COD_MUNICIPIO",
    "COD_UNICO_ENDERECO",
    "COD_SETOR",
    "NUM_QUADRA",
    "NUM_FACE",
    "NUM_ENDERECO",
    "NOM_TIPO_SEGLOGR",
    "NOM_TITULO_SEGLOGR",
    "NOM_SEGLOGR",
    "LATITUDE",
    "LONGITUDE",
    "CEP",
    "NV_GEO_COORD",
]

# Linhas do CSV: endereço único, endereço repetido no arquivo (mesmo
# COD_UNICO_ENDERECO), número não numérico, coordenada com vírgula e um
# endereço de OUTRO município que precisa ser ignorado.
_CNEFE_LINHAS = [
    dict(
        COD_MUNICIPIO=_MUN,
        COD_UNICO_ENDERECO="E1",
        COD_SETOR=_SETOR,
        NUM_QUADRA="001",
        NUM_FACE="001",
        NUM_ENDERECO="45",
        NOM_TIPO_SEGLOGR="PASSAGEM",
        NOM_TITULO_SEGLOGR="IVAN LEÃO",
        NOM_SEGLOGR="TESTE IBGE",
        LATITUDE="-1.3062",
        LONGITUDE="-48.473",
        CEP="66610000",
        NV_GEO_COORD="1",
    ),
    # Repetição do mesmo endereço (Belém: 618.075 linhas → 601.192 únicas).
    dict(
        COD_MUNICIPIO=_MUN,
        COD_UNICO_ENDERECO="E1",
        COD_SETOR=_SETOR,
        NUM_QUADRA="001",
        NUM_FACE="001",
        NUM_ENDERECO="45",
        NOM_TIPO_SEGLOGR="PASSAGEM",
        NOM_TITULO_SEGLOGR="IVAN LEÃO",
        NOM_SEGLOGR="TESTE IBGE",
        LATITUDE="-1.3062",
        LONGITUDE="-48.473",
        CEP="66610000",
        NV_GEO_COORD="1",
    ),
    # "s/n": número não numérico nunca vira âncora.
    dict(
        COD_MUNICIPIO=_MUN,
        COD_UNICO_ENDERECO="E2",
        COD_SETOR=_SETOR,
        NUM_QUADRA="001",
        NUM_FACE="002",
        NUM_ENDERECO="s/n",
        NOM_TIPO_SEGLOGR="PASSAGEM",
        NOM_TITULO_SEGLOGR="IVAN LEÃO",
        NOM_SEGLOGR="TESTE IBGE",
        LATITUDE="-1,3063",  # vírgula decimal (publicação real)
        LONGITUDE="-48,473",
        CEP="66610001",
        NV_GEO_COORD="2",
    ),
    # Outro município: fora do escopo.
    dict(
        COD_MUNICIPIO=_OUTRO,
        COD_UNICO_ENDERECO="E4",
        COD_SETOR=_OUTRO + "60000001",
        NUM_QUADRA="001",
        NUM_FACE="001",
        NUM_ENDERECO="10",
        NOM_TIPO_SEGLOGR="RUA",
        NOM_TITULO_SEGLOGR="",
        NOM_SEGLOGR="FORA DO ESCOPO",
        LATITUDE="-1.4",
        LONGITUDE="-48.5",
        CEP="",
        NV_GEO_COORD="1",
    ),
]


class BancoTemporario:
    """SQLite temporário do teste + acesso aos scripts de ingestão."""

    def __init__(self, engine, carregar):
        self.engine = engine
        self.carregar = carregar

    def contar(self, sql: str, **params) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(text(sql), params).scalar_one())


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    """Banco temporário + scripts carregados apontando para ele."""
    caminho = tmp_path / "ibge.db"
    url = f"sqlite:///{caminho.as_posix()}"
    engine = create_engine(url)
    for tabela in (CnefeEnderecoModel.__table__, LogradouroFaceModel.__table__, LogradouroNoModel.__table__):
        tabela.create(bind=engine)

    # O script lê DATABASE_URL no import e o `load_dotenv()` do próprio script
    # não sobrescreve variável já presente, então o env vence o `.env`.
    monkeypatch.setenv("DATABASE_URL", url)

    def carregar(nome: str):
        spec = importlib.util.spec_from_file_location(f"ingestao_{nome}", _SCRIPTS / f"{nome}.py")
        modulo = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(modulo)
        return modulo

    yield BancoTemporario(engine=engine, carregar=carregar)
    engine.dispose()


def _escrever_cnefe(caminho: Path, linhas: list[dict], *, em_zip=False) -> str:
    csv_path = caminho / "cnefe.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=_CNEFE_COLUNAS, delimiter=";")
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow(linha)
    if not em_zip:
        return str(csv_path)
    zip_path = caminho / "cnefe.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(csv_path, arcname="1501402_BELEM.csv")
    return str(zip_path)


def _feature(props: dict, coords: list, tipo: str = "LineString") -> dict:
    return {"type": "Feature", "properties": props, "geometry": {"type": tipo, "coordinates": coords}}


def _geojson_faces(caminho: Path) -> str:
    """Recorte mínimo com a estrutura medida em Belém (D16).

    Duas ruas compartilhando o mesmo nó (= cruzamento), uma face sem nome,
    uma geometria que não é LineString e um registro de outro município.
    """
    features = [
        _feature(
            {
                "CD_SETOR": _SETOR,
                "NM_LOG": "TESTE IBGE",
                "NM_TIP_LOG": "PASSAGEM",
                "NM_TIT_LOG": "IVAN LEÃO",
                "CD_QUADRA": "001",
                "CD_FACE": "001",
                "TOT_RES": "10",
                "TOT_GERAL": "12",
            },
            [[-48.473, -1.3062], [-48.473, -1.3066]],  # [lng, lat]
        ),
        _feature(
            {
                "CD_SETOR": _SETOR,
                "NM_LOG": "TRANSVERSAL",
                "NM_TIP_LOG": "TRAVESSA",
                "NM_TIT_LOG": "",
                "CD_QUADRA": "001",
                "CD_FACE": "002",
                "TOT_RES": "4",
                "TOT_GERAL": "4",
            },
            [[-48.473, -1.3066], [-48.472, -1.3066]],  # nó (-1.3066, -48.473) em comum
        ),
        # Sem nome (19,6% em Belém): não vira logradouro nem cruzamento.
        _feature(
            {"CD_SETOR": _SETOR, "NM_LOG": "   ", "NM_TIP_LOG": "RUA", "NM_TIT_LOG": ""},
            [[-48.471, -1.3062], [-48.471, -1.3063]],
        ),
        # Geometria que não é LineString: descartada.
        _feature(
            {"CD_SETOR": _SETOR, "NM_LOG": "PRACA", "NM_TIP_LOG": "PRACA", "NM_TIT_LOG": ""},
            [[-48.47, -1.306], [-48.47, -1.3061], [-48.471, -1.3061]],
            tipo="Polygon",
        ),
        # Outro município.
        _feature(
            {"CD_SETOR": _OUTRO + "60000001", "NM_LOG": "FORA", "NM_TIP_LOG": "RUA", "NM_TIT_LOG": ""},
            [[-48.5, -1.4], [-48.51, -1.41]],
        ),
    ]
    destino = caminho / "faces.geojson"
    destino.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return str(destino)


class TestIngestaoCnefe:
    def test_importa_normaliza_e_escopo(self, banco, tmp_path):
        caminho = _escrever_cnefe(tmp_path, _CNEFE_LINHAS)
        modulo = banco.carregar("import_ibge_cnefe")

        total = modulo.importar(caminho, _MUN)

        # E1 repetido no arquivo deduplica; E4 (outro município) não entra.
        assert total == 2
        assert banco.contar("SELECT COUNT(*) FROM cnefe_endereco") == 2
        assert banco.contar("SELECT COUNT(*) FROM cnefe_endereco WHERE cod_municipio = :m", m=_OUTRO) == 0

        with banco.engine.connect() as conn:
            e1 = conn.execute(text("SELECT * FROM cnefe_endereco WHERE cod_unico_endereco = 'E1'")).mappings().one()
            e2 = conn.execute(text("SELECT * FROM cnefe_endereco WHERE cod_unico_endereco = 'E2'")).mappings().one()

        assert e1["num_endereco"] == 45
        assert e1["num_quadra"] == 1 and e1["num_face"] == 1, "zfill normalizado para inteiro (D17)"
        # chave_logradouro COM tipo, chave_nome SEM tipo (D27).
        assert e1["chave_logradouro"] == "passagem ivan leao teste ibge"
        assert e1["chave_nome"] == "ivan leao teste ibge"
        assert e1["nome_logradouro"] == "PASSAGEM IVAN LEÃO TESTE IBGE"
        assert e1["lat"] == pytest.approx(-1.3062)
        assert e1["nv_geo_coord"] == "1"

        assert e2["num_endereco"] is None, '"s/n" nunca vira âncora'
        assert e2["lat"] == pytest.approx(-1.3063), "vírgula decimal convertida"
        assert e2["lng"] == pytest.approx(-48.473)

    def test_e_idempotente(self, banco, tmp_path):
        caminho = _escrever_cnefe(tmp_path, _CNEFE_LINHAS)
        modulo = banco.carregar("import_ibge_cnefe")

        primeira = modulo.importar(caminho, _MUN)
        segunda = modulo.importar(caminho, _MUN)

        assert primeira == segunda == 2
        assert banco.contar("SELECT COUNT(*) FROM cnefe_endereco") == 2, "DELETE + INSERT não acumula"

    def test_aceita_zip(self, banco, tmp_path):
        caminho = _escrever_cnefe(tmp_path, _CNEFE_LINHAS, em_zip=True)
        modulo = banco.carregar("import_ibge_cnefe")

        assert modulo.importar(caminho, _MUN) == 2

    def test_reprocessar_nao_duplica(self, banco, tmp_path):
        modulo = banco.carregar("import_ibge_cnefe")
        modulo.importar(_escrever_cnefe(tmp_path, _CNEFE_LINHAS), _MUN)

        # Arquivo novo, mesma base: o DELETE do município zera o escopo.
        novas = [dict(linha, NUM_ENDERECO="99") for linha in _CNEFE_LINHAS if linha["COD_MUNICIPIO"] == _MUN][:1]
        modulo.importar(_escrever_cnefe(tmp_path, novas), _MUN)

        assert banco.contar("SELECT COUNT(*) FROM cnefe_endereco") == 1
        assert banco.contar("SELECT COUNT(*) FROM cnefe_endereco WHERE num_endereco = 99") == 1


class TestIngestaoFaces:
    def test_importa_faces_e_nos(self, banco, tmp_path):
        caminho = _geojson_faces(tmp_path)
        modulo = banco.carregar("import_ibge_faces")

        n_faces, n_nos = modulo.importar(caminho, _MUN)

        assert n_faces == 2, "só as duas faces com nome e LineString do município"
        assert banco.contar("SELECT COUNT(*) FROM logradouro_face WHERE cod_municipio = :m", m=_OUTRO) == 0

        with banco.engine.connect() as conn:
            principal = (
                conn.execute(
                    text("SELECT * FROM logradouro_face WHERE chave_logradouro = :chave"),
                    {"chave": "passagem ivan leao teste ibge"},
                )
                .mappings()
                .one()
            )
            # Cruzamento (D16): o nó (-1.3066, -48.473) é extremo das DUAS ruas.
            cruzamentos = conn.execute(
                text(
                    "SELECT node_lat, node_lng, chave_logradouro FROM logradouro_no "
                    "WHERE node_lat = :lat AND node_lng = :lng"
                ),
                {"lat": -1.3066, "lng": -48.473},
            ).fetchall()

        geom = json.loads(principal["geom"])
        assert geom == [[-1.3062, -48.473], [-1.3066, -48.473]], "GeoJSON [lng,lat] vira [lat,lng] com 6 casas"
        assert principal["chave_logradouro"] == "passagem ivan leao teste ibge"
        assert principal["cod_quadra"] == 1 and principal["cod_face"] == 1
        assert principal["tot_res"] == 10

        assert len(cruzamentos) == 2, "mesma coordenada, logradouros diferentes = cruzamento"
        assert len({linha[2] for linha in cruzamentos}) == 2

        # 4 linhas (2 extremidades por face, a compartilhada uma por rua) em
        # 3 coordenadas distintas: o ON CONFLICT deduplica só repetição de
        # (coordenada, logradouro) — vizinhas da mesma via dividem extremidade.
        assert n_nos == 4 == banco.contar("SELECT COUNT(*) FROM logradouro_no")
        assert banco.contar("SELECT COUNT(DISTINCT node_lat || ',' || node_lng) FROM logradouro_no") == 3

    def test_e_idempotente(self, banco, tmp_path):
        caminho = _geojson_faces(tmp_path)
        modulo = banco.carregar("import_ibge_faces")

        primeira = modulo.importar(caminho, _MUN)
        segunda = modulo.importar(caminho, _MUN)

        assert primeira == segunda
        assert banco.contar("SELECT COUNT(*) FROM logradouro_face") == primeira[0]
        assert banco.contar("SELECT COUNT(*) FROM logradouro_no") == primeira[1]

    def test_zip_estadual_carrega_so_o_municipio_alvo(self, banco, tmp_path):
        """Zip estadual: um JSON por município — só o `<cod>_*.json` entra."""
        recorte = json.loads(Path(_geojson_faces(tmp_path)).read_text(encoding="utf-8"))
        outros = {
            "type": "FeatureCollection",
            "features": [
                _feature(
                    {"CD_SETOR": _OUTRO + "60000001", "NM_LOG": "OUTRA CIDADE", "NM_TIP_LOG": "RUA"},
                    [[-48.5, -1.4], [-48.51, -1.41]],
                )
            ],
        }
        zip_path = tmp_path / "faces_pa.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"{_MUN}_BELEM.json", json.dumps(recorte))
            zf.writestr(f"{_OUTRO}_ABAETETUBA.json", json.dumps(outros))

        modulo = banco.carregar("import_ibge_faces")
        n_faces, _ = modulo.importar(str(zip_path), _MUN)

        assert n_faces == 2, "o arquivo de outro município não é sequer carregado"
        assert banco.contar("SELECT COUNT(*) FROM logradouro_face") == 2
