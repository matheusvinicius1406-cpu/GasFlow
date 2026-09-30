"""Provider Overpass — "entre ruas" por passe próprio (etapa 6, D14).

**`intersecoes` é o único produto.** Este módulo não devolve lat/lng/cep e não
toca `geocode_status`: ele lê o `lat/lng` já cacheado do logradouro (D14) e
devolve, ou a lista no contrato congelado
``[{"nome": str, "numero": int}]``, ou ``[]``.

``[]`` **não é erro** — é a triagem (D2): rua sem dado no OSM, rua com menos de
duas âncoras e falha de rede terminam todas aqui, e é assim de propósito. Quem
grava é o passe da etapa 8, que faz UPDATE **só** da coluna `intersecoes`.

Três decisões tiradas do spike (§8.0, números no ADR-0004) e materializadas
como código, não como comentário:

1. **Três queries separadas** (§8.2 combinada devolve 504 no Overpass público).
2. **bbox em vez de `around` na 2ª e 3ª query** — `around:R,LAT,LNG` é um
   círculo em volta de UM ponto e cobre só 2R de rua; as âncoras e os cruzamentos
   precisam do logradouro INTEIRO.
3. **Cruzamento é quem compartilha coordenada com o logradouro**, não quem está
   simplesmente por perto: rua paralela a 40 m não é cruzamento e entraria na
   lista com um número inventado por projeção.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.core.texto import normalizar
from app.infrastructure.geocoding.axis import (
    estimar_numero,
    juntar_segmentos,
    projetar_no_eixo,
)
from app.infrastructure.geocoding.http_provider import RateLimitedHttp

logger = logging.getLogger("gasflow.geocoding.overpass")

# Achar a via a partir do ponto cacheado: o geocode devolveu o ponto DO logradouro,
# então um círculo generoso resolve — é só para achar a via, não para medir nada.
_RAIO_ACHAR_RUA_M = 400
_METROS_POR_GRAU_LAT = 110574.0
_METROS_POR_GRAU_LNG = 111320.0
# Tolerância do deslocamento perpendicular da âncora (§8.3.1). Virou constante
# explícita porque o spike mediu inversões de número com 40 m (§8.8.4): é
# parâmetro com teste, não número escondido no corpo do laço.
TOLERANCIA_EIXO_M = 40.0


@dataclass
class PasseIntersecoes:
    """Resultado de um passe de UMA rua.

    Só `intersecoes` é gravado no cache. O resto existe para a métrica da
    §8.5/§8.8.5 — sem os contadores, "entre ruas" seria opinião.
    """

    intersecoes: List[Dict[str, Any]] = field(default_factory=list)
    encontrou_rua: bool = False
    ancoras: int = 0
    cruzamentos: int = 0
    # Fração 0..1 da polilinha coberta pela faixa [1ª âncora, última âncora].
    cobertura_eixo: float = 0.0
    # Quantas âncoras quebram a monotonía da numeração ao longo do eixo.
    inversoes_numero: int = 0
    # Motivo de ter terminado vazio (dado de diagnóstico, nunca gravado).
    motivo: str = ""


class OverpassProvider(RateLimitedHttp):
    """POST no Overpass reusando rate limit, retry, backoff e breaker da base."""

    name = "overpass"

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        tolerancia_eixo_m: float = TOLERANCIA_EIXO_M,
        **kwargs: Any,
    ):
        kwargs.setdefault("timeout_s", settings.overpass_timeout_s)
        kwargs.setdefault("rate_limit_s", settings.overpass_rate_limit_s)
        kwargs.setdefault("max_attempts", settings.overpass_max_attempts)
        kwargs.setdefault("user_agent", settings.geocoding_user_agent)
        super().__init__(
            (base_url or settings.overpass_base_url).rstrip("/"),
            **kwargs,
        )
        self._tolerancia = float(tolerancia_eixo_m)

    # ── API ──────────────────────────────────────────────

    def buscar_intersecoes(self, rua: str, lat: Any, lng: Any) -> PasseIntersecoes:
        """Passe de uma rua. Nunca levanta: falha de rede vira lista vazia (D2)."""
        res = PasseIntersecoes()
        if not settings.overpass_enabled:
            res.motivo = "overpass_desligado"
            return res

        nome = normalizar(rua)
        if not nome:
            res.motivo = "rua_vazia"
            return res
        try:
            ponto = (float(lat), float(lng))
        except (TypeError, ValueError):
            res.motivo = "coordenada_invalida"
            return res

        try:
            return self._passe(nome, ponto, res)
        except Exception:  # nada aqui pode derrubar o passe de 10.000 ruas
            logger.warning("overpass.passe_falhou", extra={"rua": rua}, exc_info=True)
            return PasseIntersecoes(motivo="falha_inesperada")

    # ── Fluxo ────────────────────────────────────────────

    def _passe(self, nome: str, ponto: Tuple[float, float], res: PasseIntersecoes) -> PasseIntersecoes:
        candidatas = self._logradouros_proximos(ponto)
        if candidatas is None:
            res.motivo = "overpass_indisponivel"
            return res

        eixo, ids_rua = self._montar_eixo(nome, candidatas)
        if eixo is None:
            # Rua não está no OSM perto do ponto cacheado: triagem, não erro.
            res.motivo = "rua_sem_geometry_no_osm"
            return res
        res.encontrou_rua = True

        caixa = _bbox(eixo, self._raio_cruzamentos())

        vias = self._vias_na_caixa(caixa)
        if vias is None:
            res.motivo = "overpass_indisponivel"
            return res
        nos = self._nos_na_caixa(caixa)
        if nos is None:
            res.motivo = "overpass_indisponivel"
            return res

        return self._conta(eixo, ids_rua, vias, nos, res)

    @staticmethod
    def _raio_cruzamentos() -> float:
        return float(settings.entre_ruas_radius_m or 150)

    def _conta(
        self,
        eixo: List[Tuple[float, float]],
        ids_rua: set,
        vias: List[dict],
        nos: List[dict],
        res: PasseIntersecoes,
    ) -> PasseIntersecoes:
        # ── âncoras ───────────────────────────────────────
        ancoras: List[Tuple[float, int]] = []
        for no in nos:
            numero = _inteiro((no.get("tags") or {}).get("addr:housenumber"))
            if numero is None:
                continue
            projetado = projetar_no_eixo(eixo, (no.get("lat"), no.get("lon")))
            if projetado is None:
                continue
            posicao, perpendicular = projetado
            # Nó que projeta fora do eixo é casa da via vizinha, não âncora nossa.
            if perpendicular > self._tolerancia:
                continue
            ancoras.append((posicao, numero))

        if len(ancoras) < 2:
            # §8.3.3: menos de duas âncoras não dá reta para interpolar.
            res.ancoras = len(ancoras)
            res.motivo = "poucas_ancoras"
            return res

        res.ancoras = len(ancoras)
        ancoras.sort()
        res.cobertura_eixo = round(ancoras[-1][0] - ancoras[0][0], 4)
        res.inversoes_numero = sum(1 for (_, a), (_, b) in zip(ancoras, ancoras[1:]) if b < a)

        # ── cruzamentos ───────────────────────────────────
        pontos_rua = set(eixo)
        por_nome: Dict[str, List[float]] = {}
        for via in vias:
            if via.get("id") in ids_rua:
                continue
            nome_via = (via.get("tags") or {}).get("name")
            if not nome_via or not str(nome_via).strip():
                continue
            geom = via.get("geometry") or []
            # Compartilha NÓ com o logradouro ⇒ é cruzamento de verdade.
            # Só "estar por perto" não conta: rua paralela entraria na lista.
            compartilhados = [(g.get("lat"), g.get("lon")) for g in geom if (g.get("lat"), g.get("lon")) in pontos_rua]
            if not compartilhados:
                continue
            for ponto_cruz in compartilhados:
                projetado = projetar_no_eixo(eixo, ponto_cruz)
                if projetado is None:
                    continue
                por_nome.setdefault(str(nome_via).strip(), []).append(projetado[0])

        res.cruzamentos = len(por_nome)
        if res.cruzamentos < 2:
            res.motivo = "poucos_cruzamentos"
            return res

        # ── contrato ──────────────────────────────────────
        intersecoes: List[Dict[str, Any]] = []
        for nome_via, posicoes in por_nome.items():
            for posicao in posicoes:
                numero = estimar_numero(posicao, ancoras)
                if numero is None:
                    continue  # fora da faixa das âncoras ⇒ fora da lista (D2)
                intersecoes.append({"nome": nome_via, "numero": int(numero)})
                break  # um item por via: dedup por nome (§8.8.3)
        intersecoes.sort(key=lambda item: item["numero"])

        if len(intersecoes) < 2:
            # §8.3.6
            res.intersecoes = []
            res.motivo = "menos_de_duas_intersecoes"
            return res

        res.intersecoes = intersecoes
        res.motivo = "ok"
        return res

    # ── Queries (três, separadas — §8.8.1) ───────────────

    def _logradouros_proximos(self, ponto: Tuple[float, float]) -> Optional[List[dict]]:
        """1) vias nomeadas num círculo em volta do ponto cacheado."""
        query = '[out:json][timeout:%d];way(around:%d,%.7f,%.7f)["highway"]["name"];out geom;' % (
            int(self._timeout),
            _RAIO_ACHAR_RUA_M,
            ponto[0],
            ponto[1],
        )
        return self._elementos(query, "way")

    def _vias_na_caixa(self, caixa: str) -> Optional[List[dict]]:
        """2) todas as vias nomeadas na bbox do logradouro inteiro."""
        query = '[out:json][timeout:%d];way["highway"]["name"](%s);out geom;' % (int(self._timeout), caixa)
        return self._elementos(query, "way")

    def _nos_na_caixa(self, caixa: str) -> Optional[List[dict]]:
        """3) nós de número de casa na bbox do logradouro inteiro — as âncoras."""
        query = '[out:json][timeout:%d];node["addr:housenumber"](%s);out body;' % (int(self._timeout), caixa)
        return self._elementos(query, "node")

    def _elementos(self, query: str, tipo: str) -> Optional[List[dict]]:
        payload = self._post_json({"data": query})
        if not isinstance(payload, dict):
            return None
        base = str((payload.get("osm3s") or {}).get("timestamp_osm_base") or "")
        if not base.startswith("20"):
            # Instância sem dado planetário (medido no spike: osm.ch devolve
            # "117272"). Aceitar isto como dado seria gravar lixo por semana.
            logger.warning("overpass.timestamp_estranho", extra={"timestamp": base})
            return None
        elementos = payload.get("elements")
        if not isinstance(elementos, list):
            return None
        return [e for e in elementos if isinstance(e, dict) and e.get("type") == tipo]

    # ── Eixo ─────────────────────────────────────────────

    def _montar_eixo(self, nome: str, candidatas: Sequence[dict]) -> Tuple[Optional[List[Tuple[float, float]]], set]:
        """Escolhe as ways do logradouro entre as candidatas e costura o eixo.

        O nome é comparado **normalizado** (minúsculas e sem acento): o contato
        traz "Passagem Ivan Leao" e o OSM traz "Passagem Ivan Leão". Casa
        exata vence contenção, e entre iguais vence o nome mais longo — é o
        que impede "rua" de casar com qualquer logradouro da cidade.
        """
        candidatos: List[Tuple[int, int, str, int, List[Tuple[float, float]]]] = []
        for via in candidatas:
            nome_via = normalizar((via.get("tags") or {}).get("name"))
            if not nome_via:
                continue
            caminho = [(g["lat"], g["lon"]) for g in (via.get("geometry") or []) if "lat" in g and "lon" in g]
            if len(caminho) < 2:
                continue
            if nome_via == nome:
                exato = 1
            elif nome in nome_via or nome_via in nome:
                exato = 0  # "berredos" dentro de "travessa dos berredos"
            else:
                continue
            candidatos.append((exato, len(nome_via), nome_via, int(via.get("id")), caminho))

        if not candidatos:
            return None, set()

        # Sort decrescente: exato primeiro, depois o nome mais longo.
        candidatos.sort(key=lambda c: (c[0], c[1]), reverse=True)
        alvo = candidatos[0][2]
        escolhidos = {via_id: caminho for _exato, _tam, nv, via_id, caminho in candidatos if nv == alvo}
        if not escolhidos:  # pragma: no cover — `alvo` veio de `candidatos`
            return None, set()

        eixo = juntar_segmentos(list(escolhidos.values()))
        if len(eixo) < 2:
            return None, set()
        return eixo, set(escolhidos)


# ── Utilitários puros ────────────────────────────────────


def _inteiro(valor: Any) -> Optional[int]:
    """`addr:housenumber` → int. Irrecuperável ⇒ `None` (nunca arredondar)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    if not digitos:
        return None
    numero = int(digitos)
    return numero if numero > 0 else None


def _bbox(pontos: Sequence[Tuple[float, float]], margem_m: float) -> str:
    """`"sul,leste,norte,oeste"` em graus, com margem em metros (§8.2 bbox)."""
    lats = [float(p[0]) for p in pontos]
    lngs = [float(p[1]) for p in pontos]
    lat_medio = sum(lats) / len(lats)
    dlat = margem_m / _METROS_POR_GRAU_LAT
    dlng = margem_m / max(1.0, _METROS_POR_GRAU_LNG * math.cos(math.radians(lat_medio)))
    return f"{min(lats) - dlat:.7f},{min(lngs) - dlng:.7f},{max(lats) + dlat:.7f},{max(lngs) + dlng:.7f}"
