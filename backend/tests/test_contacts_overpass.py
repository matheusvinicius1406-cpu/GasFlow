"""Fase 2 §8.6 — Provider Overpass: contrato, projeção e resiliência.

Cobre o que §8.6 pede para a etapa 6, com o Overpass falso por
`httpx.MockTransport` (zero rede):

- `intersecoes` no **contrato congelado**, ordenado, só com âncora real;
- `<2 âncoras ⇒ []` · `<2 interseções ⇒ []` · fora da faixa ⇒ fora;
- nó que projeta **fora do eixo** descartado (§8.3.1);
- nó cujo `addr:street` nomeia **outra via** descartado (D2, medido no D20);
- cruzamento que só **passa por perto** não entra (§8.8.2);
- dedup por nome (§8.8.3);
- **3 queries separadas** e bbox em vez de círculo (§8.8.1);
- `around:20000` nunca aparece — 20 km é cobertura, não raio de query (§17.1);
- timeout/4xx/breaker terminam em lista vazia, nunca em exceção (D2/D3).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import settings
from app.infrastructure.geocoding.axis import (
    estimar_numero,
    juntar_segmentos,
    projetar_no_eixo,
)
from app.infrastructure.geocoding.overpass_provider import (
    OverpassProvider,
    _bbox,
    _inteiro,
)

BASE = "https://overpass.test/api/interpreter"

# ── Mundo OSM falso ───────────────────────────────────────
# Logradouro de 4 segmentos (duas ways costuradas pelo nó (-1.003,-48.000)),
# eixo na vertical: lat cai, lng constante. 1 segmento ≈ 111 m.

RUA_ID_1, RUA_ID_2 = 100, 101
WAY_RUA_1 = {
    "type": "way",
    "id": RUA_ID_1,
    "tags": {"highway": "residential", "name": "Passagem Ivan Leão"},
    "geometry": [
        {"lat": -1.000, "lon": -48.000},
        {"lat": -1.001, "lon": -48.000},
        {"lat": -1.002, "lon": -48.000},
        {"lat": -1.003, "lon": -48.000},
    ],
}
WAY_RUA_2 = {
    "type": "way",
    "id": RUA_ID_2,
    "tags": {"highway": "residential", "name": "Passagem Ivan Leão"},
    "geometry": [
        {"lat": -1.003, "lon": -48.000},
        {"lat": -1.004, "lon": -48.000},
    ],
}
# Outra via perto, mas de OUTRO nome: candidata na query 1, nunca logradouro.
WAY_OUTRA = {
    "type": "way",
    "id": 900,
    "tags": {"highway": "residential", "name": "Rua Distantíssima"},
    "geometry": [{"lat": -1.000, "lon": -48.010}, {"lat": -1.001, "lon": -48.010}],
}

# Cruzamentos: compartilham NÓ com o logradouro.
WAY_A = {
    "type": "way",
    "id": 200,
    "tags": {"highway": "residential", "name": "Rua A"},
    "geometry": [{"lat": -1.001, "lon": -48.001}, {"lat": -1.001, "lon": -48.000}],
}
WAY_A_2 = {  # mesmo nome, outro id — tem que virar UMA entrada só
    "type": "way",
    "id": 204,
    "tags": {"highway": "residential", "name": "Rua A"},
    "geometry": [{"lat": -1.001, "lon": -48.000}, {"lat": -1.001, "lon": -47.999}],
}
WAY_B = {
    "type": "way",
    "id": 201,
    "tags": {"highway": "residential", "name": "Rua B"},
    "geometry": [{"lat": -1.002, "lon": -48.001}, {"lat": -1.002, "lon": -48.000}],
}
# Compartilha o nó da ponta (posição 0) — FORA da faixa das âncoras.
WAY_FORA = {
    "type": "way",
    "id": 202,
    "tags": {"highway": "residential", "name": "Rua Fora"},
    "geometry": [{"lat": -1.000, "lon": -48.001}, {"lat": -1.000, "lon": -48.000}],
}
# Passa a ~33 m do eixo sem compartilhar nó: NÃO é cruzamento (§8.8.2).
WAY_PERTO = {
    "type": "way",
    "id": 203,
    "tags": {"highway": "residential", "name": "Rua Perto"},
    "geometry": [{"lat": -1.001, "lon": -48.0003}, {"lat": -1.002, "lon": -48.0003}],
}

# Âncoras: posição 0.25 → 30 ; posição 0.50 → 70.
NO_ANC_1 = {"type": "node", "id": 1, "lat": -1.001, "lon": -48.000, "tags": {"addr:housenumber": "30"}}
NO_ANC_2 = {"type": "node", "id": 2, "lat": -1.002, "lon": -48.000, "tags": {"addr:housenumber": "70"}}
# ~55 m de deslocamento lateral: casa da via vizinha, tem que cair fora.
NO_FORA_EIXO = {
    "type": "node",
    "id": 3,
    "lat": -1.001,
    "lon": -48.0005,
    "tags": {"addr:housenumber": "999"},
}
# Não é número de casa.
NO_SEM_NUMERO = {"type": "node", "id": 4, "lat": -1.001, "lon": -48.000, "tags": {"addr:housenumber": "s/n"}}
# ~33 m do eixo (dentro da tolerância) mas declarando OUTRA rua no
# `addr:street`: casa da via vizinha. Medido no gate D20 (ADR-0008) — as 9
# âncoras aceitas de "Passagem Samuel Soares" declaravam todas
# "Rua dos Caripunas"/"Rua dos Pariquis": 2023..2371 numa rua que vai de 3 a 51.
NO_DE_OUTRA_RUA = {
    "type": "node",
    "id": 5,
    "lat": -1.0015,
    "lon": -48.0003,
    "tags": {"addr:housenumber": "9999", "addr:street": "Rua Distantíssima"},
}
# Declarando a NOSSA rua: continua entrando (a tolerância sozinha não basta).
NO_DA_RUA = {
    "type": "node",
    "id": 6,
    "lat": -1.0025,
    "lon": -48.000,
    "tags": {"addr:housenumber": "110", "addr:street": "Passagem Ivan Leao"},
}

_LOGRADOUROS = [WAY_RUA_1, WAY_RUA_2, WAY_OUTRA]
_VIAS = [WAY_RUA_1, WAY_RUA_2, WAY_A, WAY_A_2, WAY_B, WAY_FORA, WAY_PERTO]
_NOS = [NO_ANC_1, NO_ANC_2, NO_FORA_EIXO, NO_SEM_NUMERO]


def _extrair_query(item) -> str:
    """Aceita o `httpx.Request` do MockTransport ou a query já em texto."""
    if isinstance(item, httpx.Request):
        return parse_qs(item.content.decode("utf-8"))["data"][0]
    return str(item)


def _resposta(item, *, base: str = "2026-09-25T00:00:00Z") -> httpx.Response:
    """Router: cada uma das 3 queries devolve o seu pedaço do mundo falso."""
    query = _extrair_query(item)
    if "way(around:" in query:
        elementos = _LOGRADOUROS
    elif 'way["highway"]["name"](' in query:
        elementos = _VIAS
    elif 'node["addr:housenumber"](' in query:
        elementos = _NOS
    else:  # pragma: no cover — query fora do formato da §8.2
        raise AssertionError(f"query inesperada: {query}")
    return httpx.Response(200, json={"osm3s": {"timestamp_osm_base": base}, "elements": elementos})


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _provider(handler=_resposta, **kwargs):
    kwargs.setdefault("sleeper", lambda _s: None)
    kwargs.setdefault("rate_limit_s", 0)
    kwargs.setdefault("max_attempts", 2)
    kwargs.setdefault("timeout_s", 5)
    return OverpassProvider(BASE, client=_transport(handler), **kwargs)


def _queries(handler=_resposta):
    """Devolve (provider, lista das queries POSTadas)."""
    vistas: list[str] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        vistas.append(parse_qs(request.content.decode("utf-8"))["data"][0])
        return handler(request)

    return _provider(wrapped), vistas


def _resposta_com_nos(extras):
    """O mundo falso com nós extras na query de `addr:housenumber`."""

    def handler(request: httpx.Request) -> httpx.Response:
        corpo = _extrair_query(request)
        if 'node["addr:housenumber"](' in corpo:
            return httpx.Response(
                200,
                json={
                    "osm3s": {"timestamp_osm_base": "2026-09-25T00:00:00Z"},
                    "elements": _NOS + list(extras),
                },
            )
        return _resposta(request)

    return handler


# ═════════════════════════════════════════════════════════
# 1. Contrato congelado (§7 / §8.3)
# ═════════════════════════════════════════════════════════


class TestContratoDoPasse:
    def test_intersecoes_no_contrato_congelado_e_ordenadas(self):
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.motivo == "ok"
        assert res.intersecoes == [
            {"nome": "Rua A", "numero": 30},
            {"nome": "Rua B", "numero": 70},
        ]
        for item in res.intersecoes:
            assert set(item) == {"nome", "numero"}
            assert isinstance(item["nome"], str)
            assert isinstance(item["numero"], int)
        assert [i["numero"] for i in res.intersecoes] == sorted(i["numero"] for i in res.intersecoes)

    def test_cruzamento_fora_da_faixa_de_ancoras_fica_de_fora(self):
        # "Rua Fora" está na posição 0, e as âncoras cobrem só [0.25, 0.50].
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert "Rua Fora" not in [i["nome"] for i in res.intersecoes]
        # Achou o cruzamento, mas não deu para estimar número ⇒ fora da lista.
        assert res.cruzamentos == 3
        assert len(res.intersecoes) == 2

    def test_cruzamento_que_so_passa_perto_nao_entra(self):
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        # "Rua Perto" não compartilha nó com o logradouro: apesar de estar a
        # ~33 m do eixo, não é cruzamento — não conta nem vira item.
        assert "Rua Perto" not in {i["nome"] for i in res.intersecoes}
        assert res.cruzamentos == 3  # A, B e Fora — sem a Perto

    def test_dedup_por_nome_dois_segmentos_mesma_via(self):
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        nomes = [i["nome"] for i in res.intersecoes]
        assert nomes.count("Rua A") == 1

    def test_no_fora_do_eixo_nao_vira_ancora(self):
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        # 4 nós candidatos: 2 âncoras de verdade, 1 fora do eixo, 1 sem número.
        assert res.ancoras == 2
        assert "999" not in {str(i["numero"]) for i in res.intersecoes}

    def test_no_sem_numero_nao_vira_ancora(self):
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.ancoras == 2  # "s/n" não conta

    def test_no_de_outra_rua_nao_vira_ancora(self):
        """`addr:street` de outra via derruba a âncora mesmo dentro de 40 m."""
        res = _provider(_resposta_com_nos([NO_DE_OUTRA_RUA])).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.ancoras == 2  # o nó da paralela (9999) não entrou
        assert res.inversoes_numero == 0  # sem ele não há inversão na faixa
        assert res.intersecoes == [
            {"nome": "Rua A", "numero": 30},
            {"nome": "Rua B", "numero": 70},
        ]

    def test_no_com_addr_street_da_propria_rua_entra(self):
        """O filtro é por PERTENCIMENTO, não por suspeita: nó daqui continua."""
        res = _provider(_resposta_com_nos([NO_DA_RUA])).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.ancoras == 3
        assert res.intersecoes == [
            {"nome": "Rua A", "numero": 30},
            {"nome": "Rua B", "numero": 70},
        ]

    def test_cobertura_e_inversoes_sao_reportadas(self):
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        # Âncoras em 0.25 e 0.50, na ordem crescente de número: sem inversão.
        assert res.cobertura_eixo == pytest.approx(0.25, abs=1e-3)
        assert res.inversoes_numero == 0


# ═════════════════════════════════════════════════════════
# 2. Portões de vazio — D2: nada é inventado
# ═════════════════════════════════════════════════════════


class TestPortoesDeVazio:
    def test_menos_de_duas_ancoras_devolve_vazio(self):
        def sem_uma(request: httpx.Request) -> httpx.Response:
            corpo = parse_qs(request.content.decode("utf-8"))["data"][0]
            if 'node["addr:housenumber"](' in corpo:
                return httpx.Response(
                    200,
                    json={
                        "osm3s": {"timestamp_osm_base": "2026-09-25T00:00:00Z"},
                        "elements": [NO_ANC_1],
                    },
                )
            return _resposta(corpo)

        res = _provider(sem_uma).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.intersecoes == []
        assert res.motivo == "poucas_ancoras"
        assert res.encontrou_rua is True

    def test_menos_de_dois_cruzamentos_devolve_vazio(self):
        def so_um(request: httpx.Request) -> httpx.Response:
            corpo = _extrair_query(request)
            if 'way["highway"]["name"](' in corpo:
                return httpx.Response(
                    200,
                    json={
                        "osm3s": {"timestamp_osm_base": "2026-09-25T00:00:00Z"},
                        "elements": [WAY_RUA_1, WAY_A],
                    },
                )
            return _resposta(corpo)

        res = _provider(so_um).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.intersecoes == []
        assert res.motivo == "poucos_cruzamentos"
        assert res.cruzamentos == 1

    def test_menos_de_duas_intersecoes_com_numero_devolve_vazio(self):
        """2 cruzamentos achados, mas só 1 com número estimável ⇒ lista vazia."""

        def so_um_com_numero(request: httpx.Request) -> httpx.Response:
            corpo = _extrair_query(request)
            if 'way["highway"]["name"](' in corpo:
                # A (posição 0.25, dentro da faixa) e Fora (posição 0, fora).
                return httpx.Response(
                    200,
                    json={
                        "osm3s": {"timestamp_osm_base": "2026-09-25T00:00:00Z"},
                        "elements": [WAY_RUA_1, WAY_RUA_2, WAY_A, WAY_FORA],
                    },
                )
            return _resposta(corpo)

        res = _provider(so_um_com_numero).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.cruzamentos == 2
        assert res.intersecoes == []
        assert res.motivo == "menos_de_duas_intersecoes"

    def test_rua_ausente_do_osm_devolve_vazio_sem_levantar(self):
        res = _provider().buscar_intersecoes("Rua Que Nao Existe Nenhuma", -1.002, -48.000)

        assert res.intersecoes == []
        assert res.encontrou_rua is False
        assert res.motivo == "rua_sem_geometry_no_osm"

    def test_rua_vazia_devolve_vazio(self):
        res = _provider().buscar_intersecoes("   ", -1.002, -48.000)
        assert res.intersecoes == []
        assert res.motivo == "rua_vazia"

    def test_coordenada_invalida_devolve_vazio(self):
        res = _provider().buscar_intersecoes("Passagem Ivan Leao", "abc", None)
        assert res.intersecoes == []
        assert res.motivo == "coordenada_invalida"

    def test_overpass_desligado_devolve_vazio(self, monkeypatch):
        monkeypatch.setattr(settings, "overpass_enabled", False)
        chamadas = {"n": 0}

        def conta(request: httpx.Request) -> httpx.Response:
            chamadas["n"] += 1
            return _resposta(request)

        res = _provider(conta).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.intersecoes == []
        assert res.motivo == "overpass_desligado"
        assert chamadas["n"] == 0  # desligado nem sai daqui


# ═════════════════════════════════════════════════════════
# 3. Resiliência — D2/D3: falha termina em lista vazia
# ═════════════════════════════════════════════════════════


class TestResiliencia:
    def test_timeout_devolve_vazio_em_vez_de_levantar(self):
        def estoura(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("rede fora")

        res = _provider(estoura).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.intersecoes == []
        assert res.motivo == "overpass_indisponivel"

    def test_4xx_nao_repete_e_devolve_vazio(self):
        tentativas = {"n": 0}

        def bad(request: httpx.Request) -> httpx.Response:
            tentativas["n"] += 1
            return httpx.Response(400, text="erro de sintaxe na query")

        res = _provider(bad).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.intersecoes == []
        assert res.motivo == "overpass_indisponivel"
        # 4xx = serviço vivo, consulta errada: tenta 1x, não 2 (max_attempts=2).
        assert tentativas["n"] == 1

    def test_timestamp_estranho_e_descartado(self):
        """Instância sem dado planetário (osm.ch devolve "117272" — medido)."""

        def velho(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"osm3s": {"timestamp_osm_base": "117272"}, "elements": []},
            )

        res = _provider(velho).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert res.intersecoes == []
        assert res.motivo == "overpass_indisponivel"

    def test_reusa_o_breaker_do_osrm(self):
        """Breaker abre e a rua seguinte nem sai daqui (sem pagar timeout de novo)."""

        def estoura(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("rede fora")

        from app.infrastructure.routing.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=1, cooldown_s=60)
        kwargs = dict(
            client=_transport(estoura), sleeper=lambda _s: None, rate_limit_s=0, max_attempts=1, breaker=breaker
        )
        p = OverpassProvider(BASE, **kwargs)

        assert p.buscar_intersecoes("Rua Um", -1.002, -48.000).motivo == "overpass_indisponivel"
        # Aberto: nenhuma tentativa — o contador de breaker não volta a subir.
        chamadas = {"n": 0}

        def conta(request: httpx.Request) -> httpx.Response:
            chamadas["n"] += 1
            return _resposta(request)

        p2 = OverpassProvider(
            BASE, client=_transport(conta), sleeper=lambda _s: None, rate_limit_s=0, max_attempts=1, breaker=breaker
        )
        assert p2.buscar_intersecoes("Rua Dois", -1.002, -48.000).intersecoes == []
        assert chamadas["n"] == 0


# ═════════════════════════════════════════════════════════
# 4. Forma da query (§8.2 + §8.8)
# ═════════════════════════════════════════════════════════


class TestFormaDaQuery:
    def test_sao_três_queries_separadas(self):
        """§8.8.1: a query combinada devolve 504 no Overpass público."""
        p, vistas = _queries()

        p.buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert len(vistas) == 3
        assert sum(1 for q in vistas if "way(around:" in q) == 1
        assert sum(1 for q in vistas if 'way["highway"]["name"](' in q) == 1
        assert sum(1 for q in vistas if 'node["addr:housenumber"](' in q) == 1

    def test_segunda_e_terceira_query_usam_bbox_nao_circulo(self):
        """§8.8.2: `around:R,LAT,LNG` cobre só 2R de rua; precisa da rua inteira."""
        p, vistas = _queries()

        p.buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        for query in vistas[1:]:
            assert "around:" not in query
            assert "(-1." in query  # bbox (sul,leste,norte,oeste) em graus

    def test_20_km_de_cobertura_nunca_vira_raio_de_query(self):
        """§17.1/§8.8.6: `around:20000` é proibido — 20 km é cobertura, não query."""
        p, vistas = _queries()

        p.buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert vistas
        for query in vistas:
            # Raio de 5 dígitos começando por 2 = alguém confundiu cobertura
            # com query. Os raios legítimos são 400 (acha rua) e 150/80 (config).
            assert not re.search(r"around:\s*2\d{4}\b", query)
            assert not re.search(r"around:\s*\d{5,}\b", query)

    def test_envia_user_agent_identificando_a_aplicacao(self):
        capturado = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["ua"] = request.headers.get("User-Agent")
            return _resposta(parse_qs(request.content.decode("utf-8"))["data"][0])

        _provider(handler, user_agent="GasFlow/9.9 (teste)").buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert capturado["ua"] == "GasFlow/9.9 (teste)"

    def test_eh_post_com_a_query_no_corpo(self):
        visto = {}

        def handler(request: httpx.Request) -> httpx.Response:
            visto["metodo"] = request.method
            return _resposta(parse_qs(request.content.decode("utf-8"))["data"][0])

        _provider(handler).buscar_intersecoes("Passagem Ivan Leao", -1.002, -48.000)

        assert visto["metodo"] == "POST"


# ═════════════════════════════════════════════════════════
# 5. Geometria do eixo (§8.3.1)
# ═════════════════════════════════════════════════════════


class TestGeometriaDoEixo:
    def test_juntar_segmentos_costura_pelo_endpoint_compartilhado(self):
        eixo = juntar_segmentos(
            [
                [(-1.000, -48.000), (-1.001, -48.000), (-1.003, -48.000)],
                [(-1.003, -48.000), (-1.004, -48.000)],
            ]
        )

        assert eixo == [
            (-1.000, -48.000),
            (-1.001, -48.000),
            (-1.003, -48.000),
            (-1.004, -48.000),
        ]

    def test_juntar_segmentos_descarta_o_que_nao_encaixa(self):
        """Geometria desconectada é descartada, não jogada no fim (D2)."""
        eixo = juntar_segmentos(
            [
                [(-1.000, -48.000), (-1.001, -48.000)],
                [(-9.000, -40.000), (-9.001, -40.000)],  # outra cidade
            ]
        )

        assert eixo == [(-1.000, -48.000), (-1.001, -48.000)]

    def test_juntar_segmentos_vazio(self):
        assert juntar_segmentos([]) == []
        assert juntar_segmentos([[(-1.0, -48.0)]]) == []

    def test_projetar_no_eixo_devolve_posicao_e_deslocamento(self):
        eixo = [(-1.000, -48.000), (-1.002, -48.000)]

        posicao, perpendicular = projetar_no_eixo(eixo, (-1.001, -48.000))
        assert posicao == pytest.approx(0.5, abs=1e-3)
        assert perpendicular == pytest.approx(0.0, abs=1e-6)

    def test_projetar_no_eixo_mede_deslocamento_lateral(self):
        eixo = [(-1.000, -48.000), (-1.002, -48.000)]

        _, perpendicular = projetar_no_eixo(eixo, (-1.001, -48.0005))

        # 0.0005° de longitude no equador ≈ 55 m.
        assert perpendicular == pytest.approx(55, abs=5)

    def test_projetar_no_eixo_com_polilinha_degenerada(self):
        assert projetar_no_eixo([], (-1.0, -48.0)) is None
        assert projetar_no_eixo([(-1.0, -48.0)], (-1.0, -48.0)) is None
        assert projetar_no_eixo([(-1.0, -48.0), (-1.001, -48.0)], None) is None
        assert projetar_no_eixo([(-1.0, -48.0), (-1.0, -48.0)], (-1.0, -48.0)) is None

    def test_estimar_numero_fora_da_faixa_devolve_none(self):
        ancoras = [(0.25, 30), (0.50, 70)]

        assert estimar_numero(0.0, ancoras) is None  # antes da 1ª âncora
        assert estimar_numero(1.0, ancoras) is None  # depois da última
        assert estimar_numero(0.375, ancoras) == 50  # bem no meio

    def test_bbox_tem_margem_em_metros(self):
        sul, leste, norte, oeste = (float(x) for x in _bbox([(-1.0, -48.0)], 150).split(","))

        assert sul < -1.0 < norte
        assert leste < -48.0 < oeste
        # ~150 m de margem em latitude ⇒ ~0.00135°
        assert (norte - (-1.0)) * 110574 == pytest.approx(150, abs=5)

    @pytest.mark.parametrize(
        "valor,esperado",
        [
            ("145", 145),
            ("145-A", 145),
            (145, 145),
            ("s/n", None),
            ("", None),
            (None, None),
            (0, None),
            (-3, None),
            (True, None),
        ],
    )
    def test_inteiro_do_addr_housenumber(self, valor, esperado):
        assert _inteiro(valor) == esperado
