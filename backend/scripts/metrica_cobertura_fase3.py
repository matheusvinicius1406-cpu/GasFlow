"""Métricas locais da Fase 3 (spec §10) sobre o banco ingerido.

O gate D20 (`metrica_concordancia_entre_ruas.py`) mede concordância e
cobertura em AMOSTRA — rede cara. As outras métricas do §10 são de
CONTAGEM e saem da população inteira (`_import_test.db`, Belém):

  1. % de ruas com >=2 âncoras CNEFE          (piso de viabilidade)
  2. % de ruas com >=2 cruzamentos de face    (piso de topologia)
  3. % de ruas com `entre` preenchido         (só com --amostra: passe local)
  4. % do eixo coberto pelas âncoras          (só com --amostra: passe local)
  5. % de endereços casados com face (D17)    (junção setor+quadra+face)

`âncora` = número numérico + coordenada (mesma definição do spike
`docs/spike/fase3/cnefe_cobertura.py`). `cruzamento` = nó com >=2 ruas
diferentes, como no spike — mas lido de `logradouro_no`, que é o que o
produto materializa (só extremidades de face entram na tabela).

Itens 3 e 4 saem do `IbgeEntreRuasProvider` sobre a MESMA amostra semeada
do D20 (mesmo seed => as mesmas ruas), em segundos, sem rede.

Uso:
    python scripts/metrica_cobertura_fase3.py --db sqlite:///./_import_test.db
    python scripts/metrica_cobertura_fase3.py --amostra 100 --seed 42
    python scripts/metrica_cobertura_fase3.py --json metricas.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

load_dotenv()

COD_MUNICIPIO_PADRAO = "1501402"  # Belém (D11)
_CASAS = 6  # mesma chave de nó do import (0,11 m)

_SQL_ANCORAS = """
    SELECT COUNT(*)                                            AS total,
           SUM(CASE WHEN num_endereco > 0
                     AND lat IS NOT NULL AND lng IS NOT NULL
                    THEN 1 ELSE 0 END)                         AS ancoras
      FROM cnefe_endereco
     WHERE cod_municipio = :cod
"""

_SQL_RUAS_ANCORAS = """
    SELECT chave_logradouro, COUNT(*) AS n
      FROM cnefe_endereco
     WHERE cod_municipio = :cod
       AND num_endereco > 0
       AND lat IS NOT NULL
       AND lng IS NOT NULL
     GROUP BY chave_logradouro
"""

_SQL_CASADOS = """
    SELECT COUNT(*)
      FROM cnefe_endereco c
      JOIN logradouro_face f
        ON f.cod_municipio = c.cod_municipio
       AND f.cod_setor     = c.cod_setor
       AND f.cod_quadra    = c.num_quadra
       AND f.cod_face      = c.num_face
     WHERE c.cod_municipio = :cod
"""

_SQL_NOS = """
    SELECT node_lat, node_lng, chave_logradouro
      FROM logradouro_no
     WHERE cod_municipio = :cod
"""

_SQL_FACES = """
    SELECT chave_logradouro, geom
      FROM logradouro_face
     WHERE cod_municipio = :cod
       AND geom IS NOT NULL
"""

_SQL_CANDIDATAS = """
    SELECT nome_logradouro,
           AVG(lat) AS lat,
           AVG(lng) AS lng
      FROM cnefe_endereco
     WHERE cod_municipio = :cod
       AND num_endereco > 0
       AND lat IS NOT NULL
       AND lng IS NOT NULL
     GROUP BY chave_logradouro, nome_logradouro
    HAVING COUNT(*) >= 2
"""


def _pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 1) if b else 0.0


def _topologia(engine, cod: str) -> Dict[str, Any]:
    """Nós, cruzamentos e faces/ruas com dois extremos cruzados."""
    with engine.connect() as conn:
        nos = conn.execute(text(_SQL_NOS), {"cod": cod}).fetchall()
        faces = conn.execute(text(_SQL_FACES), {"cod": cod}).mappings().all()

    # nó -> ruas que o tocam (chave do nó = 6 casas, igual ao import)
    por_no: Dict[Tuple[float, float], set] = {}
    for lat, lng, chave in nos:
        por_no.setdefault((round(lat, _CASAS), round(lng, _CASAS)), set()).add(chave)
    cruzamentos = {k for k, ruas in por_no.items() if len(ruas) >= 2}

    faces_com_2 = 0
    por_rua_cruz: Dict[str, set] = {}
    for row in faces:
        geom = row["geom"]
        # `text()` cru devolve a coluna JSON como string; o model devolve list.
        if isinstance(geom, str):
            try:
                geom = json.loads(geom)
            except ValueError:
                continue
        if not isinstance(geom, list) or len(geom) < 2:
            continue
        extremidades = (
            (round(float(geom[0][0]), _CASAS), round(float(geom[0][1]), _CASAS)),
            (round(float(geom[-1][0]), _CASAS), round(float(geom[-1][1]), _CASAS)),
        )
        toca = [e for e in extremidades if e in cruzamentos]
        for e in toca:
            por_rua_cruz.setdefault(row["chave_logradouro"], set()).add(e)
        if len(toca) == 2:
            faces_com_2 += 1

    ruas = {row["chave_logradouro"] for row in faces}
    ruas_2_cruz = sum(1 for rua in ruas if len(por_rua_cruz.get(rua, ())) >= 2)
    return {
        "faces": len(faces),
        "nos_distintos": len(por_no),
        "nos_cruzamento": len(cruzamentos),
        "faces_com_2_extremos_cruzados": faces_com_2,
        "faces_com_2_extremos_cruzados_pct": _pct(faces_com_2, len(faces)),
        "ruas_faces": len(ruas),
        "ruas_com_2_cruzamentos": ruas_2_cruz,
        "ruas_com_2_cruzamentos_pct": _pct(ruas_2_cruz, len(ruas)),
    }


def _passe_local(engine, cod: str, amostra: int, seed: int) -> Optional[Dict[str, Any]]:
    """Passe do provider IBGE na amostra semeada (sem rede, segundos)."""
    if amostra <= 0:
        return None
    from sqlalchemy.orm import sessionmaker

    from app.infrastructure.geocoding.ibge_provider import IbgeEntreRuasProvider

    with engine.connect() as conn:
        linhas = conn.execute(text(_SQL_CANDIDATAS), {"cod": cod}).mappings().all()
    if not linhas:
        return None
    ruas = [{"nome_logradouro": r["nome_logradouro"], "lat": float(r["lat"]), "lng": float(r["lng"])} for r in linhas]
    random.Random(seed).shuffle(ruas)
    ruas = ruas[: min(amostra, len(ruas))]

    db = sessionmaker(bind=engine)()
    provedor = IbgeEntreRuasProvider(db)
    t0 = time.monotonic()
    motivos: Dict[str, int] = {}
    eixo: List[float] = []
    com_entre = 0
    for rua in ruas:
        passe = provedor.buscar_intersecoes(rua["nome_logradouro"])
        motivos[passe.motivo] = motivos.get(passe.motivo, 0) + 1
        if passe.motivo == "ok":
            com_entre += 1
            eixo.append(float(passe.cobertura_eixo))
    db.close()
    return {
        "amostra": len(ruas),
        "seed": seed,
        "tempo_s": round(time.monotonic() - t0, 1),
        "ruas_com_entre": com_entre,
        "ruas_com_entre_pct": _pct(com_entre, len(ruas)),
        "cobertura_eixo_media": round(sum(eixo) / len(eixo), 3) if eixo else 0.0,
        "motivos": dict(sorted(motivos.items(), key=lambda kv: -kv[1])),
    }


def medir(db_url: str, cod: str, amostra: int, seed: int) -> Dict[str, Any]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            ancoras = conn.execute(text(_SQL_ANCORAS), {"cod": cod}).mappings().one()
            ruas_rows = conn.execute(text(_SQL_RUAS_ANCORAS), {"cod": cod}).fetchall()
            casados = int(conn.execute(text(_SQL_CASADOS), {"cod": cod}).scalar_one())

        total = int(ancoras["total"])
        n_ancoras = int(ancoras["ancoras"] or 0)
        com_2 = sum(1 for _chave, n in ruas_rows if int(n) >= 2)

        relatorio: Dict[str, Any] = {
            "municipio": cod,
            "enderecos": total,
            "enderecos_ancora": n_ancoras,
            "enderecos_ancora_pct": _pct(n_ancoras, total),
            "ruas_com_ancora": len(ruas_rows),
            "ruas_com_2_ancoras": com_2,
            "ruas_com_2_ancoras_pct": _pct(com_2, len(ruas_rows)),
            "enderecos_casados_face": casados,
            "enderecos_casados_face_pct": _pct(casados, total),
        }
        relatorio.update(_topologia(engine, cod))
        passe = _passe_local(engine, cod, amostra, seed)
        if passe is not None:
            relatorio["passe_local"] = passe
        return relatorio
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Metricas locais da Fase 3 (§10) sobre o banco ingerido")
    parser.add_argument("--db", default=os.getenv("DATABASE_URL", "sqlite:///./_import_test.db"))
    parser.add_argument("--cod-municipio", default=COD_MUNICIPIO_PADRAO)
    parser.add_argument("--amostra", type=int, default=0, help="passe local do provider (0 = so contagem)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", dest="arquivo", help="grava o relatorio em JSON")
    args = parser.parse_args()

    from app.core.config import settings  # noqa: F401  (valida as env)

    relatorio = medir(args.db, args.cod_municipio, args.amostra, args.seed)

    print(f"== Metricas locais Fase 3 - municipio {args.cod_municipio} ==")
    for chave in sorted(relatorio):
        valor = relatorio[chave]
        if chave == "passe_local":
            print("  passe_local:")
            for sub in sorted(valor):
                print(f"    {sub:<32}: {valor[sub]}")
        else:
            print(f"  {chave:<32}: {valor}")

    if args.arquivo:
        with open(args.arquivo, "w", encoding="utf-8") as fh:
            json.dump(relatorio, fh, ensure_ascii=False, indent=2)
        print(f"\nrelatorio gravado em {args.arquivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
