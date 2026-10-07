"""Importa o CNEFE 2022 (IBGE) para a tabela `cnefe_endereco` — Fase 3, etapa 1.

Fonte: https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/
CSV municipal (delimiter `;`, latin-1 ou utf-8), com rua, número, CEP e
lat/lng — a âncora de numeração que o OSM não tem em Belém (ADR-0008).

Economia de RAM (o arquivo de Belém tem 618.075 linhas): o CSV é lido em
**streaming** e gravado em lotes por `executemany` — nunca materializa a base
inteira na memória. Transação única, então ou importa tudo ou nada.

Idempotente e deduplicante, por duas camadas:

1. `DELETE` do município dentro da mesma transação antes do INSERT — rodar N
   vezes deixa sempre a mesma base, nada acumula;
2. `ON CONFLICT DO NOTHING` sobre `uq_cnefe_endereco_chave` — deduplica
   **dentro do arquivo**. O CNEFE publica uma linha por (endereço × espécie):
   em Belém 618.075 linhas viram 601.192 endereços únicos, porque o mesmo
   endereço aparece mais de quando hospita dois estabelecimentos. Nos 16.843
   grupos duplicados as colunas de endereço (setor/quadra/face/número/lat/lng/
   CEP) são idênticas — só `COD_ESPECIE`/`DSC_ESTABELECIMENTO`/`COD_TIPO_ESECI`
   variam, e essas colunas **não** entram no modelo: geocodificar número ↔
   coordenada não precisa de espécie. Fica uma linha por endereço, que é o que
   a tabela e a constraint dizem ser.

`ON CONFLICT DO NOTHING` (não `INSERT OR IGNORE`): portável para SQLite e
PostgreSQL, e é o mesmo padrão do `rbac_seed`.

Escopo: **Belém por default** (D11: `default_city`/`default_uf`).
`--cod-municipio` muda o escopo; as linhas de OUTRO município do arquivo são
ignoradas, então dá para passar o ZIP do Pará inteiro sem poluir a base.

Uso:
    python scripts/import_ibge_cnefe.py data/ibge/1501402_BELEM.zip
    python scripts/import_ibge_cnefe.py --cod-municipio 1501402 arquivo.csv
"""

from __future__ import annotations

import argparse
import csv
import io
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

# Belém (D11): cidade/UF padrão do renomeador.
COD_MUNICIPIO_PADRAO = "1501402"
_LOTE = 5000

_COLUNAS = (
    "cod_municipio",
    "cod_unico_endereco",
    "cod_setor",
    "num_quadra",
    "num_face",
    "num_endereco",
    "chave_logradouro",
    "chave_nome",
    "nome_logradouro",
    "lat",
    "lng",
    "cep",
    "nv_geo_coord",
)


def _detectar_encoding(cabecalho: bytes) -> str:
    """utf-8 primeiro; latin-1 como fallback (o CNEFE é publicado nos dois)."""
    try:
        cabecalho.decode("utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "latin-1"


def _abrir_csv(caminho: str):
    """Abre `.csv` direto ou `.zip` contendo um CSV, já como texto."""
    if not os.path.isfile(caminho):
        raise SystemExit(f"arquivo não encontrado: {caminho}")
    if zipfile.is_zipfile(caminho):
        zf = zipfile.ZipFile(caminho)
        nomes = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not nomes:
            raise SystemExit(f"zip sem CSV: {caminho}")
        bruto = zf.open(nomes[0])
    else:
        bruto = open(caminho, "rb")

    cabecalho = bruto.readline()
    bruto.seek(0)
    encoding = _detectar_encoding(cabecalho)
    return io.TextIOWrapper(bruto, encoding=encoding, newline="")


def _inteiro(valor: str) -> int | None:
    """`"42"` → 42; qualquer coisa que não seja dígito → None (nunca inventar)."""
    texto = (valor or "").strip()
    return int(texto) if texto.isdigit() else None


def _float(valor: str) -> float | None:
    texto = (valor or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _nome_canonico(tipo: str, titulo: str, nome: str) -> str:
    return " ".join(p for p in ((tipo or "").strip(), (titulo or "").strip(), (nome or "").strip()) if p)


def importar(caminho: str, cod_municipio: str) -> int:
    fh = _abrir_csv(caminho)
    with fh:
        leitor = csv.reader(fh, delimiter=";")
        try:
            header = next(leitor)
        except StopIteration:
            raise SystemExit(f"CSV vazio: {caminho}") from None
        idx = {nome: i for i, nome in enumerate(header)}
        obrigatorios = ("COD_MUNICIPIO", "COD_SETOR", "NOM_SEGLOGR")
        faltando = [c for c in obrigatorios if c not in idx]
        if faltando:
            raise SystemExit(f"CSV sem as colunas {faltando} — arquivo errado?")

        def campo(row: list[str], nome: str, padrao: str = "") -> str:
            i = idx.get(nome)
            if i is None or i >= len(row):
                return padrao
            return row[i].strip()

        engine = create_engine(DATABASE_URL)
        submetidos = 0
        ignorados = 0
        sem_numero = 0
        lote: list[dict] = []

        def despejar(conn, destinos: list[dict]) -> None:
            if not destinos:
                return
            sql = (
                f"INSERT INTO cnefe_endereco ({', '.join(_COLUNAS)}) "
                f"VALUES ({', '.join(':' + c for c in _COLUNAS)}) "
                "ON CONFLICT DO NOTHING"
            )
            conn.execute(text(sql), destinos)

        # DELETE + INSERT na MESMA transação: idempotente e atômico.
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM cnefe_endereco WHERE cod_municipio = :cod"),
                {"cod": cod_municipio},
            )
            for row in leitor:
                if not row:
                    continue
                if campo(row, "COD_MUNICIPIO") != cod_municipio:
                    ignorados += 1
                    continue
                tipo = campo(row, "NOM_TIPO_SEGLOGR")
                titulo = campo(row, "NOM_TITULO_SEGLOGR")
                nome = campo(row, "NOM_SEGLOGR")
                canonico = _nome_canonico(tipo, titulo, nome)
                numero = _inteiro(campo(row, "NUM_ENDERECO"))
                if numero is None:
                    sem_numero += 1
                lote.append(
                    {
                        "cod_municipio": cod_municipio,
                        "cod_unico_endereco": campo(row, "COD_UNICO_ENDERECO"),
                        "cod_setor": campo(row, "COD_SETOR"),
                        "num_quadra": _inteiro(campo(row, "NUM_QUADRA")),
                        "num_face": _inteiro(campo(row, "NUM_FACE")),
                        "num_endereco": numero,
                        # `chave_logradouro` = nome COM tipo ("passagem ivan leao").
                        "chave_logradouro": normalizar(canonico),
                        # `chave_nome` = SEM tipo ("ivan leao") — casa o cache
                        # que veio sem o tipo do logradouro (D27).
                        "chave_nome": normalizar(_nome_canonico("", titulo, nome)),
                        "nome_logradouro": canonico,
                        "lat": _float(campo(row, "LATITUDE")),
                        "lng": _float(campo(row, "LONGITUDE")),
                        "cep": campo(row, "CEP"),
                        "nv_geo_coord": campo(row, "NV_GEO_COORD"),
                    }
                )
                if len(lote) >= _LOTE:
                    despejar(conn, lote)
                    submetidos += len(lote)
                    lote.clear()
            despejar(conn, lote)
            submetidos += len(lote)

            # Conta dentro da MESMA transação: com ON CONFLICT parte das
            # linhas é descartada por ser endereço repetido no arquivo.
            reais = conn.execute(
                text("SELECT COUNT(*) FROM cnefe_endereco WHERE cod_municipio = :cod"),
                {"cod": cod_municipio},
            ).scalar_one()
    engine.dispose()

    print(f"municipio         : {cod_municipio}")
    print(f"linhas do arquivo : {submetidos}")
    print(f"enderecos no banco: {reais}")
    print(f"deduplicadas      : {submetidos - reais}")
    print(f"ignorados (outro) : {ignorados}")
    print(f"sem numero valido : {sem_numero}")
    return reais


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa o CNEFE 2022 para cnefe_endereco")
    parser.add_argument("caminho", help=".csv ou .zip do CNEFE (municipal ou UF)")
    parser.add_argument(
        "--cod-municipio",
        default=COD_MUNICIPIO_PADRAO,
        help=f"código IBGE a importar (default: {COD_MUNICIPIO_PADRAO} = Belém)",
    )
    args = parser.parse_args()

    inicio = time.monotonic()
    importar(args.caminho, args.cod_municipio)
    print(f"tempo            : {time.monotonic() - inicio:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
