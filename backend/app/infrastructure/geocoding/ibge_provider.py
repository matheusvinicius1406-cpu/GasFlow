"""Provider IBGE — "entre ruas" por CNEFE + Faces de Logradouro (Fase 3).

Mesmo contrato do ``OverpassProvider`` (§8.1): devolve ``PasseIntersecoes`` com
``intersecoes`` no formato congelado ``[{"nome": str, "numero": int}]`` — ou
``[]``, que é triagem e não erro (D2). **Zero rede**: tudo é consulta local nas
tabelas ingeridas pelos scripts da etapa 1/2 (D14/D18).

``lat``/``lng`` entram por paridade de interface e são ignorados de propósito:
o Overpass precisa deles para achar a via numa busca espacial, e aqui a via é
identificada pelo nome normalizado — o mesmo eixo de dados do ``geocode_cache``.

Duas diferenças estruturais em relação ao Overpass, medidas na etapa 1/2 (não é
gosto, é dado):

- **Cada face tem seu próprio eixo.** ``juntar_segmentos`` não serve: faces do
  MESMO logradouro não compartilham extremidades (mínimo medido: 6,94 m), então
  a costura descartaria tudo. O número de casa é local à face — é assim que a
  numeração por quadra de Belém se comporta. Medido: encadear as 10 faces da
  Passagem Ivan Leão num eixo único dá uma rua de 641 m cuja numeração sai
  ``1149, 97, 813, 17, 58, 1720`` (não monotônica) e o "entre" erra.
- **A direção da numeração vem da própria face.** As âncoras são ordenadas pela
  posição projetada; se o número cai ao longo da geometria, ``geom[0]`` carrega
  o número ALTO. Trocar isso inverte o par do "entre".

Algoritmo (§6 da spec):

1. carrega as faces do logradouro (exato, ou por sufixo — D27);
2. por face, projeta as âncoras CNEFE (``NV_GEO_COORD ∈ {1,2}``, número > 0) e
   mantém só as que caem dentro da tolerância lateral;
3. menos de duas âncoras ⇒ a face não produz número (nunca inventa, D2);
4. emite o número de cada extremidade com o nome da via que cruza naquele nó
   (D16: nó compartilhado com face de OUTRA rua);
5. **deduplica por nome antes de ordenar (§8.8.3)** — a mesma via transversal
   aparece em várias faces e, sem dedup, ``escolher_entre_ruas`` empatava. O
   valor retido é o **menor**, que é o que reproduz o caso de aceite;
6. ordena por ``numero`` e mantém só o trecho entre a 1ª e a última âncora
   (§6.7); menos de dois itens ⇒ ``[]``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.core.texto import normalizar
from app.infrastructure.geocoding.axis import haversine_m, projetar_no_eixo
from app.infrastructure.geocoding.overpass_provider import (
    TOLERANCIA_EIXO_M,
    PasseIntersecoes,
)
from app.infrastructure.repositories.ibge_model import (
    CnefeEnderecoModel,
    LogradouroFaceModel,
    LogradouroNoModel,
)

logger = logging.getLogger("gasflow.geocoding.ibge")

# Mesma tolerância lateral da §8.3.1: âncora de via paralela não pode entrar.
_TOLERANCIA_M = TOLERANCIA_EIXO_M


class IbgeEntreRuasProvider:
    """`buscar_intersecoes` sobre as tabelas do IBGE, sem rede e sem chave."""

    name = "ibge"

    def __init__(self, db, *, cod_municipio: Optional[str] = None):
        self._db = db
        self._cod_municipio = str(cod_municipio or settings.ibge_cod_municipio)

    # ── API ──────────────────────────────────────────────

    def buscar_intersecoes(self, rua: str, lat: Any = None, lng: Any = None) -> PasseIntersecoes:
        """Passe de uma rua. Nunca levanta: sem dado é lista vazia (D2)."""
        res = PasseIntersecoes()
        chave = normalizar(rua)
        if not chave:
            res.motivo = "rua_vazia"
            return res

        faces = self._faces(chave)
        if not faces:
            res.motivo = "sem_face"
            return res
        res.encontrou_rua = True

        chaves_proprias = {f.chave_logradouro for f in faces}
        itens: List[Dict[str, Any]] = []
        ancoras_rua: List[int] = []
        cobertura_pond = 0.0
        comprimento_total = 0.0
        inversoes = 0
        cruzamentos: Dict[str, None] = {}

        for face in faces:
            geom = _geometria(face)
            if geom is None:
                continue
            ancoras = self._ancoras(face, geom)
            if len(ancoras) < 2:
                continue

            comprimento = _comprimento_m(geom)
            cobertura_pond += comprimento * (ancoras[-1][0] - ancoras[0][0])
            comprimento_total += comprimento
            inversoes += _inversoes(ancoras)
            ancoras_rua.extend(int(n) for _, n in ancoras)

            # Direção pela posição, não pela ordem de chegada do banco. Com a
            # âncora ordenada, `cresce` diz qual extremo é o de número baixo;
            # usar o primeiro/último no lugar do min/max inverte os extremos
            # numa face barulhenta.
            cresce = ancoras[-1][1] >= ancoras[0][1]
            menor = min(n for _, n in ancoras)
            maior = max(n for _, n in ancoras)
            numero_ini = menor if cresce else maior
            numero_fim = maior if cresce else menor

            for nome in self._nomes_cruzamento(geom[0], chaves_proprias):
                cruzamentos[nome] = None
                itens.append({"nome": nome, "numero": int(numero_ini)})
            for nome in self._nomes_cruzamento(geom[-1], chaves_proprias):
                cruzamentos[nome] = None
                itens.append({"nome": nome, "numero": int(numero_fim)})

        res.ancoras = len(ancoras_rua)
        res.cruzamentos = len(cruzamentos)
        res.cobertura_eixo = (cobertura_pond / comprimento_total) if comprimento_total > 0 else 0.0
        res.inversoes_numero = inversoes

        if not itens:
            res.motivo = "sem_ancora_util"
            return res

        # §8.8.3: dedup por NOME antes de ordenar; retém o menor número.
        por_nome: Dict[str, int] = {}
        for item in itens:
            nome, numero = item["nome"], item["numero"]
            if nome not in por_nome or numero < por_nome[nome]:
                por_nome[nome] = numero

        if ancoras_rua:
            # §6.7: manter só o trecho coberto pelas âncoras do logradouro.
            primeiro, ultimo = min(ancoras_rua), max(ancoras_rua)
            por_nome = {n: v for n, v in por_nome.items() if primeiro <= v <= ultimo}

        intersecoes: List[Dict[str, Any]] = [{"nome": n, "numero": v} for n, v in por_nome.items()]
        # Sem a anotação o literal unifica `nome`/`numero` em object e o sort
        # não aceita a chave; `int()` mantém a ordem real (int sobre int).
        intersecoes.sort(key=lambda item: int(item["numero"]))

        if len(intersecoes) < 2:
            res.motivo = "menos_de_duas_intersecoes"
            return res

        res.intersecoes = intersecoes
        res.motivo = "ok"
        return res

    # ── Consultas ────────────────────────────────────────

    def _faces(self, chave: str) -> List[LogradouroFaceModel]:
        """Faces do logradouro; D27 cai para o sufixo quando o cache guarda o
        nome sem o tipo ("Ivan Leão" contra "Passagem Ivan Leão").

        Duas ruas diferentes terminando no mesmo sufixo são ambiguidade ⇒ nada
        de misturar faces de ruas distintas (D2): devolve vazio e a rua triagem.
        """
        candidatos = (
            self._db.query(LogradouroFaceModel)
            .filter(
                LogradouroFaceModel.cod_municipio == self._cod_municipio,
                LogradouroFaceModel.chave_logradouro == chave,
            )
            .all()
        )
        if candidatos:
            return candidatos

        sufixo = f"% {chave}"
        candidatos = (
            self._db.query(LogradouroFaceModel)
            .filter(
                LogradouroFaceModel.cod_municipio == self._cod_municipio,
                LogradouroFaceModel.chave_logradouro.like(sufixo),
            )
            .all()
        )
        if len({f.chave_logradouro for f in candidatos}) > 1:
            logger.debug("IBGE: sufixo ambiguo para %r (%d ruas)", chave, len(candidatos))
            return []
        return candidatos

    def _ancoras(self, face: LogradouroFaceModel, geom: Sequence[Tuple[float, float]]) -> List[Tuple[float, int]]:
        """Âncoras da face em ``(posição 0..1, número)``, ordenadas por posição."""
        if face.cod_setor is None or face.cod_quadra is None or face.cod_face is None:
            return []
        linhas = (
            self._db.query(CnefeEnderecoModel.lat, CnefeEnderecoModel.lng, CnefeEnderecoModel.num_endereco)
            .filter(
                CnefeEnderecoModel.cod_municipio == self._cod_municipio,
                CnefeEnderecoModel.cod_setor == face.cod_setor,
                CnefeEnderecoModel.num_quadra == face.cod_quadra,
                CnefeEnderecoModel.num_face == face.cod_face,
                CnefeEnderecoModel.num_endereco > 0,
                CnefeEnderecoModel.lat.isnot(None),
                CnefeEnderecoModel.nv_geo_coord.in_(("1", "2")),
            )
            .all()
        )
        ancoras: List[Tuple[float, int]] = []
        for lat, lng, numero in linhas:
            projecao = projetar_no_eixo(geom, (lat, lng))
            if projecao is None:
                continue
            posicao, deslocamento = projecao
            if deslocamento > _TOLERANCIA_M:
                continue  # âncora de via paralela (§8.3.1)
            ancoras.append((float(posicao), int(numero)))
        ancoras.sort()

        # Duas âncoras na MESMA posição não definem direção: a segunda sai.
        distintas: List[Tuple[float, int]] = []
        for item in ancoras:
            if not distintas or item[0] != distintas[-1][0]:
                distintas.append(item)
        return distintas

    def _nomes_cruzamento(self, ponto: Sequence[float], chaves_proprias: set) -> List[str]:
        """Vias com nome que compartilham este nó com o logradouro (D16)."""
        linhas = (
            self._db.query(LogradouroNoModel.nome_logradouro)
            .filter(
                LogradouroNoModel.cod_municipio == self._cod_municipio,
                LogradouroNoModel.node_lat == ponto[0],
                LogradouroNoModel.node_lng == ponto[1],
            )
            .distinct()
            .all()
        )
        nomes: List[str] = []
        for (nome,) in linhas:
            chave_nome = normalizar(nome)
            if not chave_nome or chave_nome in chaves_proprias:
                continue
            nomes.append(str(nome).strip())
        return nomes


# ── Helpers de geometria ──────────────────────────────────


def _geometria(face: LogradouroFaceModel) -> Optional[List[Tuple[float, float]]]:
    bruto = face.geom or []
    pontos: List[Tuple[float, float]] = []
    for p in bruto:
        try:
            pontos.append((float(p[0]), float(p[1])))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    if len(pontos) < 2 or _comprimento_m(pontos) <= 0:
        return None
    return pontos


def _comprimento_m(geom: Sequence[Tuple[float, float]]) -> float:
    return sum(haversine_m(a, b) for a, b in zip(geom, geom[1:]))


def _inversoes(ancoras: Sequence[Tuple[float, int]]) -> int:
    """Âncoras que quebram a monotonia da face — métrica da §8.5, não filtro."""
    if len(ancoras) < 2:
        return 0
    direcao = 1 if ancoras[-1][1] >= ancoras[0][1] else -1
    total = 0
    for (_, anterior), (_, posterior) in zip(ancoras, ancoras[1:]):
        delta = posterior - anterior
        if delta and (1 if delta > 0 else -1) != direcao:
            total += 1
    return total
