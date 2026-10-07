"""Gate D20 (spec §10 / ADR-0008) — a métrica de concordância tem teste.

O gate é o que decide se a Fase 3 fecha, e as duas rodadas reais mostraram por
que precisa de teste:

1. a **unidade** do limite (`concordancia` é 0-100 e `_CONCORDANCIA_MINIMA` é
   fração — o bug que aprovou com 35%);
2. **abstenção não é concordância** (dois `None` não provam acordo; rua em que
   só um lado tem passe não entra na régua);
3. **falha de rede não é falta de dado do OSM** (o veredito usa a cobertura
   sobre as ruas respondidas);
4. a régua agora é o **conjunto de cruzamentos** (a antiga — par na grade
   1/25/50/75/99 — tinha teto de 38,7% na amostra real, medido e registrado no
   ADR-0008; os pontos da grade seguem no relatório como diagnóstico).

Os casos usam oito ruas sintéticas com a mesma forma da amostra real: IBGE
respondendo seis, Overpass três (folga de cobertura), uma rua com nome só em
diferente grafia, uma com cruzamento que só o OSM enxerga e uma sem dado.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "metrica_concordancia_entre_ruas.py"


def _carregar_gate():
    spec = importlib.util.spec_from_file_location("metrica_gate_d20", _SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


gate = _carregar_gate()

# Ruas da amostra (o gate só usa nome/lat/lng delas para reportar divergência).
_RUAS = [{"nome_logradouro": f"RUA TESTE {i:02d}", "lat": -1.3 - i * 0.001, "lng": -48.47} for i in range(8)]

# Cruzamentos da rua comum: quatro nomes, números fora da grade (1/25/50/75/99
# fica sem par dos dois lados -> abstenção, que o diagnostico segue contando).
_NOMES_IBGE = ("RUA A", "RUA B", "RUA C", "RUA D")


def _itens(*nomes: str) -> List[Dict[str, Any]]:
    return [{"nome": nome, "numero": 10 * (i + 1)} for i, nome in enumerate(nomes)]


def _passe(intersecoes: Optional[List[Dict[str, Any]]], motivo: str = "ok") -> Dict[str, Any]:
    return {"passe": SimpleNamespace(intersecoes=intersecoes or []), "motivo": motivo}


def _cenario(*, so_grafia: bool = False, indisponivel_em: int = -1, divergentes: int = 0):
    """8 ruas: IBGE responde 6 (75%), Overpass 3 (37.5% -> folga de 2x)."""
    ibge = [_passe(_itens(*_NOMES_IBGE)) for _ in _RUAS[:6]]
    ibge += [_passe([], "menos_de_duas_intersecoes") for _ in _RUAS[6:]]

    nomes_rua0 = ["RUA A", "rua B", "RUA C", "rua D"] if so_grafia else list(_NOMES_IBGE)
    nomes_rua1 = list(_NOMES_IBGE[: 4 - divergentes]) + [f"RUA X{i}" for i in range(divergentes)]
    overpass = [
        _passe(_itens(*nomes_rua0)),
        _passe(_itens(*nomes_rua1)),
        _passe(_itens(*_NOMES_IBGE)),
    ]
    for i in range(3, 8):
        motivo = "overpass_indisponivel" if i == indisponivel_em else "rua_sem_geometry_no_osm"
        overpass.append(_passe([], motivo))
    return ibge, overpass


def test_limite_de_concordancia_e_aplicado_na_unidade_certa():
    """O bug que aprovou 35%: fração comparada contra pontos percentuais."""
    ibge, overpass = _cenario(divergentes=4)  # 8 de 12 cruzamentos = 66.7%
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    assert relatorio["concordancia_cruzamentos"] == 66.7
    assert "REPROVADO" in relatorio["veredito"]
    assert "66.7%" in relatorio["veredito"]
    # A régua é a fração da spec (70%), lida como 70 pontos no relatório.
    assert gate._CONCORDANCIA_MINIMA * 100 == 70.0


def test_cruzamento_que_só_o_overpass_enxerga_conta_como_divergencia():
    """Um nome só do OSM derruba a concordância - não é dado que se ignora."""
    ibge, overpass = _cenario(divergentes=2)  # 10 de 12 = 83.3%
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    assert relatorio["cruzamentos_overpass"] == 12
    assert relatorio["cruzamentos_comuns"] == 10
    assert relatorio["concordancia_cruzamentos"] == 83.3
    assert relatorio["divergencias_cruzamentos"][0]["so_overpass"] == ["RUA X0", "RUA X1"]


def test_rua_sem_passe_de_um_lado_fica_fora_da_regua():
    """Só um lado respondeu: a rua não está no interseccional e não entra na régua.

    Ela também não pode virar "concordância" - dois conjuntos onde um não
    existe não provam acordo. Os pontos da grade dela saem do denominador.
    """
    ibge, overpass = _cenario()
    # Rua extra em que só o OSM tem passe (IBGE triagem) - 4 cruzamentos.
    ibge.append(_passe([], "sem_face"))
    overpass.append(_passe(_itens("RUA Q", "RUA R", "RUA S", "RUA T")))
    ruas = _RUAS + [{"nome_logradouro": "RUA TESTE 08", "lat": -1.35, "lng": -48.47}]
    relatorio = gate._comparar(ruas, ibge, overpass)

    assert relatorio["interseccional"] == 3
    assert relatorio["cruzamentos_overpass"] == 12  # 4 da rua extra nao contam
    assert relatorio["concordancia_cruzamentos"] == 100.0


def test_abstacao_na_grade_continua_fora_do_denominador():
    """Diagnostico dos pontos da grade: dois None nao viram comparacao."""
    ibge, overpass = _cenario(so_grafia=True)
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    # 3 ruas x 5 numeros: o par (20,30) so cerca o 25 -> 3 comparaveis, 12 abstidos.
    assert relatorio["pontos_comparaveis"] == 3
    assert relatorio["pontos_abstidos"] == 12
    assert relatorio["interseccional"] == 3


def test_normalizado_casa_grafia_diferente_e_cru_fica_ao_lado():
    ibge, overpass = _cenario(so_grafia=True)  # RUA A/B/C/D vs RUA A/rua B/RUA C/rua D
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    assert relatorio["concordancia_cruzamentos_cru"] == 83.3  # 10 de 12 no texto cru
    assert relatorio["concordancia_cruzamentos"] == 100.0  # 12 de 12 normalizado
    assert relatorio["veredito"].startswith("APROVADO")
    assert "concordancia de cruzamentos 100.0%" in relatorio["veredito"]


def test_poucos_cruzamentos_nao_vira_percentual_citavel():
    """Piso de evidencia: 100% sobre dois nomes nao fecha a fase."""
    ibge = [_passe(_itens("RUA A", "RUA B"))] + [_passe([], "sem_face") for _ in _RUAS[1:]]
    overpass = [_passe(_itens("RUA A", "RUA B"))] + [_passe([], "rua_sem_geometry_no_osm") for _ in _RUAS[1:]]
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    assert relatorio["concordancia_cruzamentos"] == 100.0
    assert "piso de" in relatorio["veredito"]
    assert "REPROVADO" in relatorio["veredito"]


def test_falha_de_rede_sai_da_cobertura_do_overpass():
    """504 não é "OSM sem dado": a folga é medida sobre as ruas respondidas."""
    ibge, overpass = _cenario(indisponivel_em=7)
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    assert relatorio["motivos_overpass"]["overpass_indisponivel"] == 1
    assert relatorio["overpass_respondidas"] == 7
    # 37.5% sobre as 8 ruas (contando a indisponivel) e 42.9% sobre as 7 respondidas.
    assert relatorio["cobertura_overpass"] == 37.5
    assert relatorio["cobertura_overpass_respondidas"] == 42.9
    # O veredito cita o numero conservador (o maior), que e o mais duro.
    assert "vs 42.9%" in relatorio["veredito"]


def test_sem_sobreposicao_o_gate_reprova():
    """Zero casos em comum nunca pode virar APROVADO (spec D20)."""
    ibge = [_passe(_itens(*_NOMES_IBGE)) for _ in _RUAS]
    overpass = [_passe([], "rua_sem_geometry_no_osm") for _ in _RUAS]
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    assert relatorio["interseccional"] == 0
    assert relatorio["veredito"] == "REPROVADO: nenhum caso em comum para comparar"


def test_sem_folga_de_cobertura_reprova():
    """Cobertura empatada: o CNEFE não ganhou com folga, a Fase 3 não fecha."""
    ibge = [_passe(_itens(*_NOMES_IBGE)) for _ in _RUAS]
    overpass = [_passe(_itens(*_NOMES_IBGE)) for _ in _RUAS]
    relatorio = gate._comparar(_RUAS, ibge, overpass)

    assert relatorio["cobertura_ibge"] == relatorio["cobertura_overpass_respondidas"]
    assert "sem folga" in relatorio["veredito"]
