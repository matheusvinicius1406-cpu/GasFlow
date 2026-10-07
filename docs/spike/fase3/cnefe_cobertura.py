"""Spike Fase 3 - leitura do CNEFE/IBGE 2022 de Belem e medicao de cobertura.

Uso: python spike_cnefe.py /tmp/cnefe_spike/1501402_BELEM.csv

Responde, com numeros:
  1. total de enderecos e % com coordenada
  2. % com numero de porta numerico
  3. quantos logradouros tem >= 2 numeros com coordenada (ancoras CNEFE)
  4. cobertura das 5 ruas do spike da Fase 2
"""

import csv
import sys
import unicodedata
from collections import defaultdict

ALVO = [
    "ivan leao",
    "berredos",
    "andradas",
    "augusto montenegro",
    "8 de maio",
    "pedro miranda",
    "humaita",
    "dois de dezembro",
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def main(path: str) -> None:
    total = 0
    com_coord = 0
    geo_ok = 0
    com_numero = 0
    num_numerico = 0
    ruas = defaultdict(int)  # logradouro normalizado -> numeros com coord
    ruas_total = defaultdict(int)
    alvo_stats = defaultdict(lambda: {"total": 0, "num": 0, "coord": 0, "nums": set()})
    nvgeo = defaultdict(int)

    with open(path, encoding="latin-1", newline="") as fh:
        reader = csv.reader(fh, delimiter=";")
        header = next(reader)
        idx = {name: i for i, name in enumerate(header)}
        i_nome = idx["NOM_SEGLOGR"]
        i_tit = idx["NOM_TITULO_SEGLOGR"]
        i_tipo = idx["NOM_TIPO_SEGLOGR"]
        i_num = idx["NUM_ENDERECO"]
        i_lat = idx["LATITUDE"]
        i_lng = idx["LONGITUDE"]
        i_nv = idx["NV_GEO_COORD"]

        for row in reader:
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            total += 1
            lat = row[i_lat].strip()
            lng = row[i_lng].strip()
            nv = row[i_nv].strip()
            nvgeo[nv] += 1
            tem_coord = bool(lat) and bool(lng)
            if tem_coord:
                com_coord += 1
            if nv in ("1", "2"):
                geo_ok += 1
            num = row[i_num].strip()
            # Nome canonico do logradouro = tipo + titulo + nome ("Passagem Ivan Leao")
            rua = norm(" ".join([row[i_tipo], row[i_tit], row[i_nome]]))
            if num:
                com_numero += 1
                if num.isdigit():
                    num_numerico += 1
            if rua:
                ruas_total[rua] += 1
                if num.isdigit() and tem_coord:
                    ruas[rua] += 1
            if rua in ALVO:
                st = alvo_stats[rua]
                st["total"] += 1
                if tem_coord:
                    st["coord"] += 1
                if num:
                    st["num"] += 1
                if num.isdigit() and tem_coord:
                    st["nums"].add((num, lat, lng))

    def pct(a: int, b: int) -> str:
        return f"{100.0 * a / b:.1f}%" if b else "n/a"

    print("=== CNEFE Belem (Censo 2022) ===")
    print(f"total enderecos            : {total}")
    print(f"com lat/lng                : {com_coord} ({pct(com_coord, total)})")
    print(f"NV_GEO_COORD in 1|2        : {geo_ok} ({pct(geo_ok, total)})")
    print(f"com NUM_ENDERECO           : {com_numero} ({pct(com_numero, total)})")
    print(f"  ... numerico puro        : {num_numerico} ({pct(num_numerico, total)})")
    print(f"NV_GEO_COORD distribuicao  : {dict(sorted(nvgeo.items()))}")

    logradouros = [r for r in ruas_total if r]
    com2 = [r for r in logradouros if ruas.get(r, 0) >= 2]
    com10 = [r for r in logradouros if ruas.get(r, 0) >= 10]
    print()
    print("=== Cobertura por logradouro (ancoras CNEFE) ===")
    print(f"logradouros distintos      : {len(logradouros)}")
    print(
        f"com >= 2 numeros + coord   : {len(com2)} ({pct(len(com2), len(logradouros))})"
    )
    print(
        f"com >= 10 numeros + coord  : {len(com10)} ({pct(len(com10), len(logradouros))})"
    )
    densos = sorted(ruas.items(), key=lambda kv: -kv[1])[:10]
    print("top 10 mais densos (numeros/c coord):")
    for nome, qtd in densos:
        print(f"   {qtd:6d}  {nome}")

    print()
    print("=== Ruas do spike Fase 2 (match por substring) ===")
    for termo in ALVO:
        st = alvo_stats.get(termo)
        if st and st["total"]:
            n = len(st["nums"])
            print(
                f"  {termo:20s} registros={st['total']:5d} com_num={st['num']:5d} "
                f"c/coord={st['coord']:5d} ancoras_num+coord={n}"
            )
        else:
            hits = [(k, v) for k, v in ruas_total.items() if termo in k]
            print(f"  {termo:20s} substrings={len(hits)} (top por ancoras):")
            hits.sort(key=lambda kv: -ruas.get(kv[0], 0))
            for k, v in hits[:3]:
                print(f"        ~ {k}: {ruas.get(k, 0)} ancoras / {v} registros")


if __name__ == "__main__":
    main(sys.argv[1])
