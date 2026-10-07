"""Importa as Faces de Logradouro 2022 (IBGE) para `logradouro_face` + `logradouro_no`.

Fonte: https://ftp.ibge.gov.br/Geociencias/Territorio/Contagem_Imoveis/
GeoJSON de faces — cada feature é um segmento de fachada com o nome do
logradouro e a polilinha. É o que substitui a way do OSM (ADR-0008): de sai o
**eixo** (polilinha costurada) e o **cruzamento** (nó compartilhado com outra
rua, D16), sem Overpass.

Duas decisões tiradas do dado real, não de suposição:

1. **`geom` guarda a polilinha inteira** (até 104 pontos), não o par de
   extremidades: 22% das faces têm 3+ pontos e guardar só p1/p2 projetaria por
   uma corda, estourando a tolerância de 40 m de `axis.projetar_no_eixo`.
2. **Face sem nome é descartada** (19,6% em Belém — medido): sem `NM_LOG` ela
   não dá para atribuir a logradouro nenhum, nem custa nome no contrato.
   Descartar economiza 19,6% do disco e evita nó órfão.

RAM: o GeoJSON é carregado com `json.load` (stdlib — sem dependência nova).
O arquivo de Belém tem 20 MB; é o preço de não puxar `ijson`.

Idempotente: `DELETE` das duas tabelas do município na mesma transação antes
do INSERT; `ON CONFLICT DO NOTHING` deduplica os nós — faces vizinhas de uma
mesma rua dividem a extremidade, e isso vira UMA linha em `logradouro_no`.

Escopo: Belém por default (D11). O filtro é o prefixo de `CD_SETOR`
(`150140205000001P`), então o GeoJSON estadual inteiro também serve.

Uso:
    python scripts/import_ibge_faces.py data/ibge/faces_1501402.geojson
    python scripts/import_ibge_faces.py --cod-municipio 1501402 faces_pa.zip
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.texto import normalizar  # noqa: E402

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")

COD_MUNICIPIO_PADRAO = "1501402"  # Belém (D11)
_LOTE = 2000
# Chave de coincidência de nó: igual ao spike, 6 casas (~0,11 m).
_CASAS = 6

_COLUNAS_FACE = (
    "cod_municipio",
    "cod_setor",
    "cod_quadra",
    "cod_face",
    "chave_logradouro",
    "nome_logradouro",
    "geom",
    "tot_res",
    "tot_geral",
)
_COLUNAS_NO = ("cod_municipio", "node_lat", "node_lng", "chave_logradouro", "nome_logradouro")


def _features_de(dados, origem: str) -> list:
    if not isinstance(dados, dict) or dados.get("type") != "FeatureCollection":
        raise SystemExit(f"não é uma FeatureCollection: {origem}")
    return dados.get("features") or []


def _carregar_features(caminho: str, cod_municipio: str) -> list:
    """FeatureCollection do município, carregando **só o arquivo dele**.

    O zip estadual traz **um JSON por município** (144 em `faces_pa.zip`), então
    selecionar pelo nome `<cod>_...` é o que segura a RAM: Belém são 20 MB; o
    Pará inteiro seria ~200 MB de uma vez. Nome fora do padrão ⇒ todos os
    arquivos, e o filtro de `CD_SETOR` resolve.
    """
    if not os.path.isfile(caminho):
        raise SystemExit(f"arquivo não encontrado: {caminho}")

    if not zipfile.is_zipfile(caminho):
        with open(caminho, "r", encoding="utf-8") as fh:
            return _features_de(json.load(fh), caminho)

    zf = zipfile.ZipFile(caminho)
    try:
        nomes = [n for n in zf.namelist() if n.lower().endswith((".geojson", ".json")) and not n.endswith("/")]
        if not nomes:
            raise SystemExit(f"zip sem .geojson/.json: {caminho}")
        alvos = [n for n in nomes if os.path.basename(n).startswith(cod_municipio + "_")]
        if not alvos:
            alvos = nomes
        features: list = []
        for nome in alvos:
            with zf.open(nome) as fh:
                features.extend(_features_de(json.load(fh), caminho))
        return features
    finally:
        zf.close()


def _inteiro(valor) -> int | None:
    """`"001"` → 1; `None`/lixo → None (nunca inventar)."""
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def _nome_canonico(tipo, titulo, nome: str) -> str:
    partes = [str(p).strip() for p in (tipo, titulo, nome) if p and str(p).strip()]
    return " ".join(partes)


def importar(caminho: str, cod_municipio: str) -> tuple[int, int]:
    features = _carregar_features(caminho, cod_municipio)

    faces: list[dict] = []
    nos: list[dict] = []
    sem_nome = 0
    sem_geom = 0
    outro_municipio = 0

    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        cod_setor = str(props.get("CD_SETOR") or "").strip()
        if not cod_setor.startswith(cod_municipio):
            outro_municipio += 1
            continue

        nome_bruto = props.get("NM_LOG")
        if nome_bruto is None or not str(nome_bruto).strip():
            # 19,6% em Belém: sem nome não vira logradouro nem cruzamento.
            sem_nome += 1
            continue

        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "LineString":
            sem_geom += 1
            continue
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            sem_geom += 1
            continue

        # GeoJSON é [lng, lat]; axis.projetar_no_eixo espera (lat, lng).
        geom: list[list[float]] = []
        for par in coords:
            try:
                lng, lat = float(par[0]), float(par[1])
            except (TypeError, ValueError, IndexError):
                geom = []
                break
            geom.append([round(lat, _CASAS), round(lng, _CASAS)])
        if len(geom) < 2:
            sem_geom += 1
            continue

        tipo = props.get("NM_TIP_LOG")
        titulo = props.get("NM_TIT_LOG")
        nome = str(nome_bruto).strip()
        canonico = _nome_canonico(tipo, titulo, nome)
        chave = normalizar(canonico)
        if not chave:
            sem_nome += 1
            continue

        faces.append(
            {
                "cod_municipio": cod_municipio,
                "cod_setor": cod_setor,
                "cod_quadra": _inteiro(props.get("CD_QUADRA")),
                "cod_face": _inteiro(props.get("CD_FACE")),
                "chave_logradouro": chave,
                "nome_logradouro": canonico,
                # `text()` cru não passa pelo tipo JSON do SQLAlchemy, então a
                # lista vira string aqui — é exatamente o que o tipo grava em
                # SQLite (TEXT) e o que ele devolve ao ler via model.
                "geom": json.dumps(geom),
                "tot_res": _inteiro(props.get("TOT_RES")),
                "tot_geral": _inteiro(props.get("TOT_GERAL")),
            }
        )

        # Extremidades = nós. Vizinhas da mesma rua dividem a extremidade e o
        # UNIQUE + ON CONFLICT colapsa na mesma linha.
        for lat, lng in (geom[0], geom[-1]):
            nos.append(
                {
                    "cod_municipio": cod_municipio,
                    "node_lat": lat,
                    "node_lng": lng,
                    "chave_logradouro": chave,
                    "nome_logradouro": canonico,
                }
            )

    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM logradouro_face WHERE cod_municipio = :cod"), {"cod": cod_municipio})
        conn.execute(text("DELETE FROM logradouro_no WHERE cod_municipio = :cod"), {"cod": cod_municipio})

        for tabela, colunas, dados in (
            ("logradouro_face", _COLUNAS_FACE, faces),
            ("logradouro_no", _COLUNAS_NO, nos),
        ):
            for inicio in range(0, len(dados), _LOTE):
                lote = dados[inicio : inicio + _LOTE]
                sql = (
                    f"INSERT INTO {tabela} ({', '.join(colunas)}) "
                    f"VALUES ({', '.join(':' + c for c in colunas)}) "
                    "ON CONFLICT DO NOTHING"
                )
                conn.execute(text(sql), lote)

        n_faces = conn.execute(
            text("SELECT COUNT(*) FROM logradouro_face WHERE cod_municipio = :cod"),
            {"cod": cod_municipio},
        ).scalar_one()
        n_nos = conn.execute(
            text("SELECT COUNT(*) FROM logradouro_no WHERE cod_municipio = :cod"),
            {"cod": cod_municipio},
        ).scalar_one()
        n_ruas = conn.execute(
            text("SELECT COUNT(DISTINCT chave_logradouro) FROM logradouro_face WHERE cod_municipio = :cod"),
            {"cod": cod_municipio},
        ).scalar_one()
    engine.dispose()

    print(f"municipio            : {cod_municipio}")
    print(f"features lidas       : {len(features)}")
    print(f"faces no banco       : {n_faces}")
    print(f"nos no banco         : {n_nos}")
    print(f"ruas distintas       : {n_ruas}")
    print(f"descartadas sem nome : {sem_nome}")
    print(f"descartadas sem geom : {sem_geom}")
    print(f"outro municipio      : {outro_municipio}")
    return n_faces, n_nos


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa as Faces de Logradouro para logradouro_face/no")
    parser.add_argument("caminho", help=".geojson/.json ou .zip das Faces")
    parser.add_argument(
        "--cod-municipio",
        default=COD_MUNICIPIO_PADRAO,
        help=f"código IBGE (default: {COD_MUNICIPIO_PADRAO} = Belém)",
    )
    args = parser.parse_args()

    inicio = time.monotonic()
    importar(args.caminho, args.cod_municipio)
    print(f"tempo               : {time.monotonic() - inicio:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
