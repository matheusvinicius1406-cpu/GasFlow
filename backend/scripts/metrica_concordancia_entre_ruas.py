"""Gate D20 — concordância entre o passe do IBGE e o do Overpass.

A Fase 3 só fecha se o CNEFE **ganhar com folga** (D20). "Folga" é medido, não
opinião: os dois provedores rodam sobre a **mesma amostra** de ruas de Belém e o
script reporta

  1. cobertura de cada um — % de ruas com ``intersecoes`` de pelo menos 2 itens;
  2. concordância no interseccional — o par de ``escolher_entre_ruas`` bate?;
  3. o veredito do gate, com a margem que sobrou.

A amostra é **semeada**: a medição se repete e o número é citável no ADR-0008.
O Overpass é a rede pública (3 queries por rua, rate limit próprio), então o
custo cresce com a amostra — medido nesta máquina: **~78 s por rua** (3 queries
de ~25 s cada), ou seja `--amostra 40` leva ~51 min.

Para não pagar essa conta a cada ajuste de medição existe o **cache por rua**
(`--cache arquivo.json`): a chave é rua normalizada + coordenada, e o registro
guarda o `PasseIntersecoes` inteiro. Re-rodar com o mesmo cache re-mede o
mesmo dado em segundos — o que muda entre rodadas é só o critério de comparação,
nunca a rede. **Falha de rede (`overpass_indisponivel`) não entra no cache**:
guardá-la congelaria um 504 eterno como se fosse dado do OSM; a re-rodada
insiste nelas.

Três correções de medição que a primeira rodada expôs (todas documentadas, nada
de "ajustar até passar"):

1. **Unidade**: `concordancia_pontos` é 0-100 e `_CONCORDANCIA_MINIMA` é
   fração — a comparação direta fazia o gate ignorar o próprio limite.
2. **Abstenção não é concordância**: dois provedores devolvendo `None` no
   mesmo número não provam que concordam; os pontos em que nenhum lado tem par
   saem do denominador e viram `abstencoes`.
3. **Cobertura × rede**: rua em que o Overpass não respondeu (504/429) não é
   rua sem dado no OSM. O veredito usa a cobertura **sobre as ruas em que o
   Overpass respondeu** — que é o número maior, i.e. o critério mais duro para
   o CNEFE.

**A régua da concordância é o conjunto de cruzamentos, não o par na grade**
(revisão de 2026-10-07, medida e registrada no ADR-0008):

- Comparar o par `escolher_entre_ruas` nos números 1/25/50/75/99 media duas
  coisas de uma vez: quem **cruza** com a rua e em que **número** cada fonte
  calibra. Medido na amostra 100/seed 42: **19 dos 31 pontos** eram de um lado
  só (a faixa de âncoras do OSM não cobre os números baixos), então o **teto**
  da régua antiga era **38,7%** — inalcançável para os 70% exigidos, mesmo com
  os dois provedores certos onde ambos respondiam.
- A pergunta que o gate precisa responder ao trocar Overpass por CNEFE é:
  **"o CNEFE perde algum cruzamento que o OSM enxerga?"**. Ela se mede por
  **fração dos cruzamentos do Overpass que o CNEFE também traz**, nas ruas em
  que os dois têm passe (as mesmas ruas interseccionais de sempre). O caminho
  inverso (quanto do CNEFE o OSM não tem) é **cobertura**, não concordância, e
  continua no relatório como diagnóstico.
- A régua de nome é a da casa: `app.core.texto.normalizar` — mesma que o
  relatório antigo chamava de "normalizada". Os pontos da grade continuam no
  relatório, **como diagnóstico**, e não decidem mais nada.

Uso::

    python scripts/metrica_concordancia_entre_ruas.py --db sqlite:///./_import_test.db
    python scripts/metrica_concordancia_entre_ruas.py --amostra 10 --sem-overpass
    python scripts/metrica_concordancia_entre_ruas.py --amostra 40 --cache d20.json
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
from sqlalchemy.orm import sessionmaker  # noqa: E402

load_dotenv()

COD_MUNICIPIO_PADRAO = "1501402"  # Belém (D11)
# Grade de números em que o par é conferido: 5 pontos por rua, sem depender
# de nenhuma âncora específica (o gate não pode escolher os casos fáceis).
_GRADE_NUMEROS = (1, 25, 50, 75, 99)
# "Ganhar com folga": o CNEFE precisa cobrir, no mínimo, o dobro de ruas com
# mais 10 pontos percentuais de vantagem absoluta. Abaixo disso é empate técnico.
_MARGEM_COBERTURA = 2.0
_MARGEM_PONTOS = 10.0
# Concordância mínima exigida nos cruzamentos que o Overpass reporta e o CNEFE
# precisa confirmar. **Fração**: o relatório trabalha em pontos percentuais
# (0-100), então a comparação é `x < _CONCORDANCIA_MINIMA * 100` — ver `_veredito`.
_CONCORDANCIA_MINIMA = 0.70
# Piso de evidência da mesma régua: um percentual calculado sobre 4 nomes não é
# citável (o veredito já reprova com zero casos em comum; isto cobre o caso
# "dois nomes e bateu"). Medido na amostra 100/seed 42: 34 cruzamentos do
# Overpass nas ruas interseccionais.
_CRUZAMENTOS_MINIMOS = 10

_SQL_RUAS = """
    SELECT nome_logradouro,
           COUNT(*)              AS n_ancoras,
           AVG(lat)              AS lat,
           AVG(lng)              AS lng
      FROM cnefe_endereco
     WHERE cod_municipio = :cod
       AND num_endereco > 0
       AND lat IS NOT NULL
       AND lng IS NOT NULL
     GROUP BY chave_logradouro, nome_logradouro
    HAVING COUNT(*) >= 2
"""


def _par(intersecoes: List[Dict[str, Any]], numero: int) -> Optional[str]:
    """O par que o consumidor congelado escolheria para ``numero`` (D12)."""
    from app.application.contacts.geocoding import escolher_entre_ruas

    return escolher_entre_ruas(intersecoes, numero)


def _medir_ibge(db, ruas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from app.infrastructure.geocoding.ibge_provider import IbgeEntreRuasProvider

    provedor = IbgeEntreRuasProvider(db)
    t0 = time.monotonic()
    saida = []
    for rua in ruas:
        passe = provedor.buscar_intersecoes(rua["nome_logradouro"])
        saida.append({"passe": passe, "motivo": passe.motivo})
    print(f"  ibge     : {time.monotonic() - t0:6.1f}s | {len(ruas)} ruas (sem rede)")
    return saida


def _chave_cache(rua: Dict[str, Any]) -> str:
    """Rua normalizada + coordenada: a mesma rua do gate é a mesma chave."""
    from app.core.texto import normalizar

    return "%s|%.5f|%.5f" % (normalizar(rua["nome_logradouro"]), float(rua["lat"]), float(rua["lng"]))


def _abrir_cache(caminho: Optional[str]) -> Dict[str, Any]:
    if not caminho or not os.path.isfile(caminho):
        return {}
    with open(caminho, "r", encoding="utf-8") as fh:
        dados = json.load(fh)
    return dados if isinstance(dados, dict) else {}


def _gravar_cache(caminho: Optional[str], cache: Dict[str, Any]) -> None:
    """Grava a cada rua: se a rodada cair no meio, o progresso fica."""
    if not caminho:
        return
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1)


def _medir_overpass(
    ruas: List[Dict[str, Any]],
    cache: Optional[Dict[str, Any]] = None,
    caminho_cache: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    from app.infrastructure.geocoding.overpass_provider import OverpassProvider, PasseIntersecoes

    try:
        provedor = OverpassProvider()
    except Exception as exc:  # pragma: no cover - depende da rede local
        print(f"  overpass : indisponivel ({exc})")
        return None

    cache = cache if cache is not None else {}
    t0 = time.monotonic()
    saida = []
    do_cache = 0
    for i, rua in enumerate(ruas, 1):
        chave = _chave_cache(rua)
        registro = cache.get(chave)
        if registro is None:
            try:
                passe = provedor.buscar_intersecoes(rua["nome_logradouro"], rua["lat"], rua["lng"])
            except Exception as exc:  # pragma: no cover - rede
                print(f"  overpass : falhou em {rua['nome_logradouro']!r}: {exc}")
                return None
            if passe.motivo == "overpass_indisponivel":
                # Rede, não dado: não cacheia (o 504 de hoje não é o OSM de
                # amanhã) — a re-rodada insiste nelas.
                saida.append({"passe": passe, "motivo": passe.motivo})
                continue
            registro = {
                "intersecoes": list(passe.intersecoes or []),
                "encontrou_rua": bool(passe.encontrou_rua),
                "ancoras": int(passe.ancoras),
                "cruzamentos": int(passe.cruzamentos),
                "cobertura_eixo": float(passe.cobertura_eixo),
                "inversoes_numero": int(passe.inversoes_numero),
                "motivo": passe.motivo,
            }
            cache[chave] = registro
            _gravar_cache(caminho_cache, cache)
        else:
            do_cache += 1
        saida.append({"passe": PasseIntersecoes(**registro), "motivo": registro["motivo"]})
        if i % 10 == 0:
            print(f"  overpass : {i}/{len(ruas)} ({time.monotonic() - t0:.0f}s)")
    print(f"  overpass : {time.monotonic() - t0:6.1f}s | {len(ruas)} ruas ({do_cache} do cache)")
    return saida


def _par_normalizado(par: Optional[str]) -> Optional[str]:
    """Mesmo par em minúsculas/sem acento/pontuação — o `normalizar` da app.

    Comparar os dois provedores em texto CRU mede diferença de grafia (CNEFE
    "TRAVESSA QUATRO DE SETEMBRO" x OSM "Rua Quatro de Setembro"), não
    diferença de cruzamento. O normalizador é o mesmo do cache e do casamento
    de nomes contra o OSM, então é a régua da casa — não um ajuste do gate.
    O texto crudo continua no relatório, lado a lado.
    """
    if par is None:
        return None
    from app.core.texto import normalizar

    return normalizar(par)


def _nome_cruzamento(item: Dict[str, Any]) -> str:
    """Nome do cruzamento na régua da casa (`normalizar`), para casar os conjuntos."""
    from app.core.texto import normalizar

    return normalizar(str(item.get("nome") or ""))


def _comparar(
    ruas: List[Dict[str, Any]],
    ibge: List[Dict[str, Any]],
    overpass: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    def cobertura(resultados: List[Dict[str, Any]]) -> Tuple[int, int]:
        validos = sum(1 for r in resultados if len(r["passe"].intersecoes or []) >= 2)
        return validos, len(resultados)

    n_ibge, total = cobertura(ibge)
    relatorio: Dict[str, Any] = {
        "amostra": total,
        "cobertura_ibge": round(100.0 * n_ibge / total, 1) if total else 0.0,
        # Diagnóstico da cobertura: sem isto "70%" é um número sem explicação.
        "motivos_ibge": _contar(r["motivo"] for r in ibge),
    }
    if overpass is None:
        return relatorio

    n_over, _ = cobertura(overpass)
    relatorio["cobertura_overpass"] = round(100.0 * n_over / total, 1) if total else 0.0
    relatorio["motivos_overpass"] = _contar(r["motivo"] for r in overpass)

    # Rede ≠ dado: rua que o Overpass não respondeu (504/429) não é rua sem
    # dado no OSM. Sobre-responder em cima de uma rede caída inflaria a folga
    # do CNEFE, então o veredito usa a cobertura **entre as respondidas** —
    # número maior = critério mais duro para quem quer passar.
    indisponivel = int(relatorio["motivos_overpass"].get("overpass_indisponivel", 0))
    respondidas = total - indisponivel
    relatorio["overpass_respondidas"] = respondidas
    relatorio["cobertura_overpass_respondidas"] = round(100.0 * n_over / respondidas, 1) if respondidas else 0.0

    interseccional = [
        i
        for i in range(total)
        if len(ibge[i]["passe"].intersecoes or []) >= 2 and len(overpass[i]["passe"].intersecoes or []) >= 2
    ]
    relatorio["interseccional"] = len(interseccional)

    # ── A régua do gate: cruzamentos, não par na grade ────
    # Nas ruas em que os DOIS têm passe, qual fração dos cruzamentos que o
    # Overpass enxerga o CNEFE também traz? É a pergunta de risco de trocar de
    # fonte ("o CNEFE perde cruzamento que o OSM acha?"). O caminho inverso é
    # cobertura, e entra só como diagnóstico.
    cruz_over = cruz_ibge = cruz_comum = cruz_comum_cru = 0
    divergencias_cruz: List[Dict[str, Any]] = []
    for i in interseccional:
        itens_ibge = ibge[i]["passe"].intersecoes or []
        itens_over = overpass[i]["passe"].intersecoes or []
        nomes_ibge = {_nome_cruzamento(x) for x in itens_ibge}
        nomes_over = {_nome_cruzamento(x) for x in itens_over}
        cru_ibge = {str(x.get("nome") or "").strip() for x in itens_ibge}
        cru_over = {str(x.get("nome") or "").strip() for x in itens_over}
        comuns = nomes_ibge & nomes_over
        cruz_ibge += len(nomes_ibge)
        cruz_over += len(nomes_over)
        cruz_comum += len(comuns)
        cruz_comum_cru += len(cru_ibge & cru_over)
        # Nome cru do OSM no relatório: o que o usuário lê é o que o OSM traz.
        so_over = sorted(
            {str(x.get("nome") or "").strip() for x in itens_over if _nome_cruzamento(x) not in nomes_ibge}
        )
        if so_over and len(divergencias_cruz) < 10:
            divergencias_cruz.append(
                {
                    "rua": ruas[i]["nome_logradouro"],
                    "so_overpass": so_over,
                    "cruzamentos_overpass": len(nomes_over),
                    "cruzamentos_ibge": len(nomes_ibge),
                    "cruzamentos_comuns": len(comuns),
                }
            )
    relatorio["cruzamentos_overpass"] = cruz_over
    relatorio["cruzamentos_ibge"] = cruz_ibge
    relatorio["cruzamentos_comuns"] = cruz_comum
    relatorio["concordancia_cruzamentos"] = round(100.0 * cruz_comum / cruz_over, 1) if cruz_over else 0.0
    relatorio["concordancia_cruzamentos_cru"] = round(100.0 * cruz_comum_cru / cruz_over, 1) if cruz_over else 0.0
    relatorio["concordancia_cruzamentos_inversa"] = round(100.0 * cruz_comum / cruz_ibge, 1) if cruz_ibge else 0.0
    relatorio["divergencias_cruzamentos"] = divergencias_cruz

    # ── diagnóstico: par na grade (não decide mais nada) ──

    comparacoes = 0  # pontos com pelo menos um lado com par
    abstencoes = 0  # pontos em que os DOIS ficaram sem par (sem informação)
    iguais = 0  # par igual no texto crudo
    iguais_norm = 0  # par igual depois de normalizar (critério do gate)
    ruas_com_par = 0  # ruas que produziram ao menos um ponto comparável
    ruas_inteiras = 0  # ruas em que TODOS os pontos comparáveis batem
    divergentes: List[Dict[str, Any]] = []
    for i in interseccional:
        a, b = ibge[i]["passe"].intersecoes, overpass[i]["passe"].intersecoes
        pontos_par = 0
        pontos_iguais = 0
        exemplo = None
        for numero in _GRADE_NUMEROS:
            par_ibge, par_over = _par(a, numero), _par(b, numero)
            if par_ibge is None and par_over is None:
                abstencoes += 1
                continue
            comparacoes += 1
            pontos_par += 1
            if par_ibge == par_over:
                iguais += 1
            if _par_normalizado(par_ibge) == _par_normalizado(par_over):
                pontos_iguais += 1  # rua: todos os pontos precisam bater
                iguais_norm += 1  # diagnostico: a régua do gate é a de cruzamentos
            elif exemplo is None:
                exemplo = {
                    "rua": ruas[i]["nome_logradouro"],
                    "numero": numero,
                    "ibge": par_ibge,
                    "overpass": par_over,
                }
        if pontos_par:
            ruas_com_par += 1
            if pontos_iguais == pontos_par:
                ruas_inteiras += 1
            if exemplo is not None and len(divergentes) < 10:
                divergentes.append(exemplo)

    relatorio["pontos_comparaveis"] = comparacoes
    relatorio["pontos_abstidos"] = abstencoes
    relatorio["ruas_com_par"] = ruas_com_par
    relatorio["concordancia_pontos"] = round(100.0 * iguais / comparacoes, 1) if comparacoes else 0.0
    relatorio["concordancia_pontos_normalizada"] = round(100.0 * iguais_norm / comparacoes, 1) if comparacoes else 0.0
    relatorio["concordancia_ruas"] = round(100.0 * ruas_inteiras / ruas_com_par, 1) if ruas_com_par else 0.0
    relatorio["divergencias_exemplo"] = divergentes
    relatorio["veredito"] = _veredito(relatorio)
    return relatorio


def _contar(motivos) -> Dict[str, int]:
    saida: Dict[str, int] = {}
    for motivo in motivos:
        saida[motivo] = saida.get(motivo, 0) + 1
    return dict(sorted(saida.items(), key=lambda kv: -kv[1]))


def _veredito(r: Dict[str, Any]) -> str:
    """D20: o CNEFE precisa ganhar COM FOLGA e confirmar os cruzamentos do OSM."""
    cobertura_ibge = r.get("cobertura_ibge", 0.0)
    # Criterio conservador: cobertura do Overpass SO entre as ruas que ele
    # respondeu (rede caída não conta como falta de dado do OSM).
    cobertura_over = float(r.get("cobertura_overpass_respondidas", 0.0))
    razao = (cobertura_ibge / cobertura_over) if cobertura_over > 0 else float("inf")
    folga = cobertura_ibge - cobertura_over >= _MARGEM_PONTOS and razao >= _MARGEM_COBERTURA

    if not r.get("interseccional"):
        # Nada em comum: o gate não pode aprovar com base em zero observação.
        return "REPROVADO: nenhum caso em comum para comparar"
    cruzamentos = int(r.get("cruzamentos_overpass", 0))
    if cruzamentos < _CRUZAMENTOS_MINIMOS:
        # Mesmo espírito do caso acima: evidência curta não vira percentual.
        return f"REPROVADO: so {cruzamentos} cruzamentos do Overpass em comum (piso de {_CRUZAMENTOS_MINIMOS})"
    if not folga:
        return (
            f"REPROVADO: cobertura {cobertura_ibge}% vs {cobertura_over}% "
            f"(razao {razao:.2f}x) - sem folga de {_MARGEM_COBERTURA}x e {_MARGEM_PONTOS}pp"
        )

    concordancia = float(r.get("concordancia_cruzamentos", 0.0))
    minima_pct = _CONCORDANCIA_MINIMA * 100  # o relatorio e 0-100, a constante e fracao
    if concordancia < minima_pct:
        return (
            f"REPROVADO: cobertura com folga ({cobertura_ibge}% vs {cobertura_over}%, "
            f"razao {razao:.2f}x), mas concordancia de cruzamentos {concordancia}% "
            f"< {minima_pct:.0f}% ({r.get('cruzamentos_comuns', 0)}/{cruzamentos} do OSM "
            f"confirmados pelo CNEFE)"
        )
    diagnosticos = float(r.get("concordancia_pontos_normalizada", 0.0))
    return (
        f"APROVADO: cobertura {cobertura_ibge}% vs {cobertura_over}% "
        f"(razao {razao:.2f}x, +{cobertura_ibge - cobertura_over:.1f}pp) | "
        f"concordancia de cruzamentos {concordancia}% "
        f"({r.get('cruzamentos_comuns', 0)}/{cruzamentos} do OSM confirmados pelo CNEFE) "
        f"em {r.get('interseccional', 0)} ruas em comum"
        f" | diagnostico par na grade {diagnosticos}%"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate D20: concordancia CNEFE (IBGE) x Overpass")
    parser.add_argument("--db", default=os.getenv("DATABASE_URL", "sqlite:///./_import_test.db"))
    parser.add_argument("--cod-municipio", default=COD_MUNICIPIO_PADRAO)
    parser.add_argument("--amostra", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sem-overpass", action="store_true", help="so a cobertura do CNEFE")
    parser.add_argument("--json", dest="arquivo", help="grava o relatorio em JSON")
    parser.add_argument(
        "--cache",
        dest="cache",
        help="cache por rua do Overpass: re-rodadas reusam o dado medido (falha de rede nao cacheia)",
    )
    args = parser.parse_args()

    engine = create_engine(args.db)
    with engine.connect() as conn:
        linhas = conn.execute(text(_SQL_RUAS), {"cod": args.cod_municipio}).mappings().all()

    if not linhas:
        print("nenhuma rua com >=2 ancoras - ingerir o CNEFE primeiro (import_ibge_cnefe.py)")
        return 1

    ruas = [
        {
            "nome_logradouro": row["nome_logradouro"],
            "lat": float(row["lat"]),
            "lng": float(row["lng"]),
        }
        for row in linhas
    ]
    random.Random(args.seed).shuffle(ruas)
    ruas = ruas[: max(1, args.amostra)]

    print(f"== Gate D20 - concordancia CNEFE x Overpass (municipio {args.cod_municipio}) ==")
    print(f"  ruas candidatas: {len(linhas)} | amostra: {len(ruas)} | seed {args.seed}")

    from app.core.config import settings  # noqa: F401  (valida as env antes do passe)

    db = sessionmaker(bind=engine)()
    print("  medicao:")
    ibge = _medir_ibge(db, ruas)
    cache = {} if args.sem_overpass else _abrir_cache(args.cache)
    overpass = None if args.sem_overpass else _medir_overpass(ruas, cache, args.cache)
    db.close()

    relatorio = _comparar(ruas, ibge, overpass)
    if args.cache:
        relatorio["cache_overpass"] = args.cache
        relatorio["cache_ruas"] = len(cache)
    print("\n== Relatorio ==")
    for chave in sorted(relatorio):
        if chave == "divergencias_exemplo":
            for exemplo in relatorio[chave]:
                print(
                    f"  {exemplo['rua']} nº {exemplo['numero']}: "
                    f"ibge={exemplo['ibge']!r} x overpass={exemplo['overpass']!r}"
                )
            continue
        if chave == "divergencias_cruzamentos":
            for exemplo in relatorio[chave]:
                print(
                    f"  {exemplo['rua']}: OSM acha e o CNEFE nao traz -> "
                    f"{', '.join(exemplo['so_overpass'])}"
                    f" (OSM {exemplo['cruzamentos_overpass']} / CNEFE {exemplo['cruzamentos_ibge']}"
                    f" / comuns {exemplo['cruzamentos_comuns']})"
                )
            continue
        print(f"  {chave:<28}: {relatorio[chave]}")

    if args.arquivo:
        with open(args.arquivo, "w", encoding="utf-8") as fh:
            json.dump(relatorio, fh, ensure_ascii=False, indent=2)
        print(f"\nrelatorio gravado em {args.arquivo}")

    veredito = str(relatorio.get("veredito", ""))
    return 0 if veredito.startswith("APROVADO") or args.sem_overpass else 2


if __name__ == "__main__":
    sys.exit(main())
