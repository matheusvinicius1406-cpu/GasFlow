"""Fase 2 §7/§14 — GeocodingService: cache por rua, resiliência e "entre ruas".

Cobre o que o §14 exige para a etapa 5:
- hit/miss/timeout/retry (``httpx.MockTransport``);
- cache reusado;
- **1 requisição por RUA** para N contatos (D12);
- "entre" por número a partir das interseções cacheadas;
- falha do provedor não derruba o lote (D3).
"""

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.contacts.geocoding import (
    STATUS_NAO_ENCONTRADO,
    STATUS_OK,
    STATUS_PENDENTE,
    GeocodingService,
    chave_do_contato,
    chave_rua,
    escolher_entre_ruas,
    normalize_endereco,
)
from app.domain.client.entity import Client
from app.domain.delivery.routing import GeocodeResult, GeocodingProvider, MockGeocodingProvider
from app.infrastructure.database.base import Base
from app.infrastructure.geocoding.axis import estimar_numero
from app.infrastructure.geocoding.nominatim_provider import NominatimProvider
from app.infrastructure.routing.circuit_breaker import CircuitBreaker
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel

import app.infrastructure.repositories.settings_model  # noqa: F401
import app.infrastructure.repositories.geocode_cache_model  # noqa: F401


# ═══════════════════════════════════════════════════════════
# Fakes / helpers
# ═══════════════════════════════════════════════════════════


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _cliente(codigo="000001", rua="berredos", numero="145", bairro="Centro", cidade=None, uf=None, cep=None) -> Client:
    return Client(
        codigo=codigo,
        nome="Contato",
        telefone=f"1190000{codigo}",
        rua=rua,
        numero=numero,
        bairro=bairro,
        cidade=cidade,
        uf=uf,
        cep=cep,
    )


class _ProviderQueExplode(GeocodingProvider):
    name = "explode"

    def geocode_street(self, rua, bairro="", cidade="", uf=""):
        raise RuntimeError("provedor caiu")


class _ViaCepFake:
    def __init__(self, cep):
        self.cep = cep
        self.chamadas = 0

    def buscar_cep(self, uf, cidade, rua):
        self.chamadas += 1
        return self.cep


class _Relogio:
    """Relógio controlado — prova o rate limit sem dormir de verdade."""

    def __init__(self, agora=0.0):
        self.agora = agora

    def __call__(self):
        return self.agora

    def avancar(self, segundos):
        self.agora += segundos


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ═══════════════════════════════════════════════════════════
# 1. Chave do cache (D12)
# ═══════════════════════════════════════════════════════════


class TestChaveRua:
    def test_normaliza_acento_caixa_e_pontuacao(self):
        assert normalize_endereco("Rua São João, 145-A") == "rua sao joao 145 a"
        # Mesma rua escrita diferente → MESMA chave (é o ponto do cache).
        assert chave_rua("Rua São João") == chave_rua("RUA SAO JOAO ")
        assert chave_rua("Rua São João") == chave_rua("rua  são   joão")

    def test_ruas_diferentes_tem_chaves_diferentes(self):
        assert chave_rua("berredos", "Centro", "São Paulo", "SP") != chave_rua("berredos", "Centro", "Osasco", "SP")

    def test_chave_e_sha256_hex(self):
        chave = chave_rua("berredos")
        assert len(chave) == 64
        assert all(c in "0123456789abcdef" for c in chave)


# ═══════════════════════════════════════════════════════════
# 2. "Entre ruas" por número (D12)
# ═══════════════════════════════════════════════════════════


class TestEscolherEntreRuas:
    intersecoes = [
        {"nome": "Rua A", "numero": 100},
        {"nome": "Rua B", "numero": 200},
        {"nome": "Rua C", "numero": 300},
    ]

    def test_pega_as_duas_que_cercam_o_numero(self):
        assert escolher_entre_ruas(self.intersecoes, "145") == "Rua A e Rua B"
        assert escolher_entre_ruas(self.intersecoes, "250") == "Rua B e Rua C"

    def test_mesma_rua_pares_diferentes_por_numero(self):
        # O ponto do D12: o par NÃO é do logradouro, é do trecho.
        assert escolher_entre_ruas(self.intersecoes, "150") != escolher_entre_ruas(self.intersecoes, "290")

    def test_numero_fora_da_faixa_nao_inventa(self):
        assert escolher_entre_ruas(self.intersecoes, "50") is None
        assert escolher_entre_ruas(self.intersecoes, "999") is None

    def test_sem_intersecoes_ou_sem_numero_devolve_none(self):
        assert escolher_entre_ruas([], "145") is None
        assert escolher_entre_ruas([{"nome": "Rua A", "numero": 100}], "145") is None
        assert escolher_entre_ruas(self.intersecoes, "S/N") is None
        assert escolher_entre_ruas(self.intersecoes, None) is None

    def test_numero_com_sufixo_e_lido(self):
        assert escolher_entre_ruas(self.intersecoes, "145-A") == "Rua A e Rua B"


class TestContratoIntersecoes:
    """Contrato CONGELADO da etapa 6: ``[{"nome": str, "numero": int}]``.

    Se este teste precisar mudar, a etapa 6 mudou o contrato — e o cache já
    gravado passou a mentir.
    """

    def test_item_malformado_e_ignorado_sem_derrubar_a_derivacao(self):
        intersecoes = [
            {"nome": "Rua A", "numero": 100},
            {"nome": "", "numero": 120},  # sem nome
            {"nome": "Rua C", "numero": "sem número"},  # numero não numérico
            {"nome": "Rua D", "numero": None},
            "lixo",  # não é dict
            {"nome": "Rua B", "numero": 200},
        ]
        # As únicas utilizáveis cercam 145 — o resto não pode virar exceção.
        assert escolher_entre_ruas(intersecoes, 145) == "Rua A e Rua B"

    def test_numero_como_string_numerica_e_aceito(self):
        # O cache é JSON: uma coluna editada à mão pode ter deixado string.
        intersecoes = [{"nome": "Rua A", "numero": "100"}, {"nome": "Rua B", "numero": "200"}]
        assert escolher_entre_ruas(intersecoes, 145) == "Rua A e Rua B"

    def test_sem_numero_no_cruzamento_nao_ha_derivacao(self):
        # É o caso majoritário do OSM-BR: cruzamento sem número não entra na
        # lista em vez de entrar com nulo (§18 / ADR-0004).
        assert escolher_entre_ruas([{"nome": "Rua A"}, {"nome": "Rua B"}], 145) is None


class TestInterpolacaoDeAncoras:
    """Plano da etapa 6 para o caso majoritário: estimar `numero` por âncoras."""

    def test_interpola_linearmente_entre_duas_ancoras(self):
        ancoras = [(0.0, 100), (1.0, 500)]
        assert estimar_numero(0.5, ancoras) == 300
        assert estimar_numero(0.0, ancoras) == 100
        assert estimar_numero(1.0, ancoras) == 500

    def test_usa_o_trecho_de_ancoras_que_contem_a_posicao(self):
        ancoras = [(0.0, 100), (0.5, 300), (1.0, 500)]
        assert estimar_numero(0.25, ancoras) == 200
        assert estimar_numero(0.75, ancoras) == 400

    def test_fora_da_faixa_coberta_devolve_none(self):
        # Extrapolar número de casa seria chute — o cruzamento sai da lista.
        assert estimar_numero(1.4, [(0.0, 100), (1.0, 500)]) is None
        assert estimar_numero(-0.1, [(0.0, 100), (1.0, 500)]) is None

    def test_menos_de_duas_ancoras_distintas_devolve_none(self):
        assert estimar_numero(0.5, []) is None
        assert estimar_numero(0.5, [(0.5, 100)]) is None
        # Duas âncoras no MESMO ponto não definem reta.
        assert estimar_numero(0.5, [(0.5, 100), (0.5, 200)]) is None

    def test_ancoras_desordenadas_sao_ordenadas(self):
        assert estimar_numero(0.5, [(1.0, 500), (0.0, 100)]) == 300

    def test_posicao_invalida_devolve_none(self):
        assert estimar_numero(None, [(0.0, 100), (1.0, 500)]) is None
        assert estimar_numero([], [(0.0, 100), (1.0, 500)]) is None

    def test_ancora_quebrada_e_ignorada_sem_levantar(self):
        # Âncora é dado: `None`/texto no meio não pode derrubar a estimativa.
        assert estimar_numero(0.5, [(None, 100), (1.0, 500)]) is None
        assert estimar_numero(0.5, [("x", 100), (1.0, 500)]) is None
        assert estimar_numero(0.5, [(0.0, 100), (1.0, "cinquenta")]) is None
        # Com uma âncora boa sobrando ainda dá para estimar.
        assert estimar_numero(0.5, [(None, 999), (0.0, 100), (1.0, 500)]) == 300


# ═══════════════════════════════════════════════════════════
# 3. Cache-first / resiliência
# ═══════════════════════════════════════════════════════════


class TestGeocodingServiceCache:
    def test_uma_requisicao_por_rua_para_muitos_contatos(self, db):
        provider = MockGeocodingProvider()
        svc = GeocodingService(db, provider=provider)

        for i in range(5):
            cliente = _cliente(codigo=f"{i + 1:06d}", numero=str(100 + i))
            assert svc.geocodificar_cliente(cliente) == STATUS_OK

        assert provider.chamadas == 1  # 5 contatos, 1 rua → 1 requisição (D12)

    def test_cache_reusado_em_chamadas_seguintes(self, db):
        provider = MockGeocodingProvider()
        svc = GeocodingService(db, provider=provider)

        svc.geocodificar_cliente(_cliente())
        cliente = _cliente(codigo="000002")
        svc.geocodificar_cliente(cliente)

        assert provider.chamadas == 1
        assert cliente.lat is not None and cliente.lng is not None

    def test_ruas_diferentes_custam_requisicoes_diferentes(self, db):
        provider = MockGeocodingProvider()
        svc = GeocodingService(db, provider=provider)

        svc.geocodificar_cliente(_cliente(rua="berredos"))
        svc.geocodificar_cliente(_cliente(codigo="000002", rua="das flores"))

        assert provider.chamadas == 2

    def test_negativo_e_cacheado_sem_reconsultar(self, db):
        provider = MockGeocodingProvider(encontrado=False)  # logradouro não achado
        svc = GeocodingService(db, provider=provider)

        assert svc.geocodificar_cliente(_cliente()) == STATUS_NAO_ENCONTRADO
        assert svc.geocodificar_cliente(_cliente(codigo="000002")) == STATUS_NAO_ENCONTRADO

        assert provider.chamadas == 1  # o "não achei" também é cacheado
        linha = db.query(GeocodeCacheModel).one()
        assert linha.lat is None

    def test_falha_do_provedor_nao_derruba_o_lote(self, db):
        svc = GeocodingService(db, provider=_ProviderQueExplode())

        cliente = _cliente()
        assert svc.geocodificar_cliente(cliente) == STATUS_PENDENTE
        assert cliente.geocode_status == STATUS_PENDENTE
        # Falha transitória NÃO é cacheada — a próxima tentativa pode dar certo.
        assert db.query(GeocodeCacheModel).count() == 0

    def test_rua_a_definir_vai_para_pendente_sem_requisicao(self, db):
        provider = MockGeocodingProvider()
        svc = GeocodingService(db, provider=provider)

        cliente = _cliente(rua="A definir")
        assert svc.geocodificar_cliente(cliente) == STATUS_PENDENTE
        assert provider.chamadas == 0

    def test_geocodificar_nao_sobrescreve_dado_do_crm(self, db):
        svc = GeocodingService(db, provider=MockGeocodingProvider())

        cliente = _cliente(cep="11111-111", cidade="Osasco", uf="SP")
        svc.geocodificar_cliente(cliente)

        assert cliente.cep == "11111-111"  # CEP já preenchido vence
        assert cliente.cidade == "Osasco"

    def test_desligado_por_env_nao_consulta(self, db, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "geocoding_enabled", False)
        provider = MockGeocodingProvider()
        svc = GeocodingService(db, provider=provider)

        assert svc.geocodificar_cliente(_cliente()) == STATUS_PENDENTE
        assert provider.chamadas == 0

    def test_cidade_default_das_settings_entra_na_chave(self, db):
        from app.application.settings.settings_service import SettingsService

        settings_svc = SettingsService(db)
        settings_svc.seed_defaults()
        settings_svc.update("contacts.default_city", "Osasco")
        settings_svc.update("contacts.default_uf", "SP")

        provider = MockGeocodingProvider()
        svc = GeocodingService(db, provider=provider)
        cliente = _cliente()  # sem cidade/uf no contato
        svc.geocodificar_cliente(cliente)

        assert cliente.cidade == "Osasco"
        # A chave saiu com a cidade default (não com vazio).
        assert db.query(GeocodeCacheModel).one().chave == chave_rua("berredos", "Centro", "Osasco", "SP")

    def test_seed_traz_cidade_e_uf_do_cliente(self, db):
        """Pendência §12.1 (REV. 7 §17.1): cidade/UF do cliente no seed.

        Sem isto a guarda "só com cidade/uf" do ViaCEP nunca deixa a chamada
        passar em produção — os testes provavam o código com cidade/uf
        injetados, não o comportamento real.
        """
        from app.application.settings.settings_service import SettingsService

        settings_svc = SettingsService(db)
        settings_svc.seed_defaults()

        assert settings_svc.get_value("contacts.default_city") == "Belém"
        assert settings_svc.get_value("contacts.default_uf") == "PA"

        svc = GeocodingService(db, provider=MockGeocodingProvider())
        assert svc.default_city() == "Belém"
        assert svc.default_uf() == "PA"

        # Contato sem cidade/UF (caso real do .vcf) herda o default ANTES da
        # chave — é isso que fecha o cache e deixa o ViaCEP ser consultado.
        cliente = _cliente()
        svc.geocodificar_cliente(cliente)
        assert db.query(GeocodeCacheModel).one().chave == chave_rua("berredos", "Centro", "Belém", "PA")

    def test_entre_ruas_sai_do_cache_sem_requisicao(self, db):
        provider = MockGeocodingProvider()
        svc = GeocodingService(db, provider=provider)
        db.add(
            GeocodeCacheModel(
                chave=chave_rua("berredos", "Centro", "Osasco", "SP"),
                lat=-23.5,
                lng=-46.6,
                rua="berredos",
                bairro="Centro",
                cidade="Osasco",
                uf="SP",
                intersecoes=[{"nome": "Rua A", "numero": 100}, {"nome": "Rua B", "numero": 200}],
            )
        )
        db.commit()

        cliente = _cliente(numero="145", cidade="Osasco", uf="SP")
        assert svc.entre_ruas_do_contato(cliente) == "Rua A e Rua B"
        assert provider.chamadas == 0  # derivado do cache, não consultado

    def test_entre_ruas_sem_cache_devolve_none(self, db):
        svc = GeocodingService(db, provider=MockGeocodingProvider())
        assert svc.entre_ruas_do_contato(_cliente()) is None


# ═══════════════════════════════════════════════════════════
# 4. CEP — OSM primeiro, ViaCEP como fallback
# ═══════════════════════════════════════════════════════════


class TestCep:
    def test_viacep_so_entra_quando_o_osm_nao_traz_postcode(self, db):
        provider = MockGeocodingProvider(GeocodeResult(lat=1.0, lng=2.0, cep=""))
        viacep = _ViaCepFake("00000-000")
        svc = GeocodingService(db, provider=provider, viacep=viacep)

        resultado, status = svc.get_or_geocode("berredos", "Centro", "Osasco", "SP")

        assert status == STATUS_OK
        assert resultado.cep == "00000-000"
        assert viacep.chamadas == 1

    def test_postcode_do_osm_dispensa_o_viacep(self, db):
        provider = MockGeocodingProvider(GeocodeResult(lat=1.0, lng=2.0, cep="06233-000"))
        viacep = _ViaCepFake("00000-000")
        svc = GeocodingService(db, provider=provider, viacep=viacep)

        resultado, _ = svc.get_or_geocode("berredos", "Centro", "Osasco", "SP")

        assert resultado.cep == "06233-000"
        assert viacep.chamadas == 0

    def test_viacep_sem_cidade_uf_nao_e_consultado(self, db):
        provider = MockGeocodingProvider(GeocodeResult(lat=1.0, lng=2.0, cep=""))
        viacep = _ViaCepFake("00000-000")
        svc = GeocodingService(db, provider=provider, viacep=viacep)

        resultado, _ = svc.get_or_geocode("berredos")

        assert resultado.cep == ""
        assert viacep.chamadas == 0


# ═══════════════════════════════════════════════════════════
# 5. Provedor HTTP real com httpx.MockTransport
# ═══════════════════════════════════════════════════════════


def _nominatim_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json=[
            {
                "lat": "-23.5505",
                "lon": "-46.6333",
                "address": {
                    "road": "Rua Berredos",
                    "suburb": "Centro",
                    "city": "Osasco",
                    "state_code": "SP",
                    "postcode": "06233-000",
                },
            }
        ],
    )


class TestNominatimProvider:
    def _provider(self, handler, **kwargs):
        return NominatimProvider(
            "https://geo.example",
            client=_transport(handler),
            sleeper=lambda _s: None,
            rate_limit_s=0,
            **kwargs,
        )

    def test_hit_estrutura_logradouro_e_cep(self):
        provider = self._provider(_nominatim_ok)

        resultado = provider.geocode_street("berredos", "Centro", "Osasco", "SP")

        assert resultado is not None
        assert resultado.lat == pytest.approx(-23.5505)
        assert resultado.lng == pytest.approx(-46.6333)
        assert resultado.rua == "Rua Berredos"
        assert resultado.cidade == "Osasco"
        assert resultado.uf == "SP"
        assert resultado.cep == "06233-000"
        # Nominatim não devolve cruzamentos: fica vazio de propósito (etapa 6).
        assert resultado.intersecoes == []

    def test_envia_user_agent_do_app(self):
        capturado = {}

        def handler(request):
            capturado["ua"] = request.headers.get("User-Agent")
            return _nominatim_ok(request)

        self._provider(handler, user_agent="GasFlow/9.9 (teste)").geocode_street("berredos")

        assert capturado["ua"] == "GasFlow/9.9 (teste)"

    def test_timeout_repete_ate_o_limite(self):
        tentativas = {"n": 0}

        def handler(request):
            tentativas["n"] += 1
            raise httpx.TimeoutException("timeout", request=request)

        provider = self._provider(handler, max_attempts=3)

        assert provider.geocode_street("berredos") is None
        assert tentativas["n"] == 3  # retry com backoff esgotou as tentativas

    def test_erro_4xx_nao_repete(self):
        tentativas = {"n": 0}

        def handler(request):
            tentativas["n"] += 1
            return httpx.Response(404, json={"error": "not found"})

        provider = self._provider(handler, max_attempts=3)

        assert provider.geocode_street("berredos") is None
        assert tentativas["n"] == 1  # 4xx é definitivo: repetir não conserta

    def test_falha_temporaria_e_recuperada_no_retry(self):
        tentativas = {"n": 0}

        def handler(request):
            tentativas["n"] += 1
            if tentativas["n"] == 1:
                return httpx.Response(503, json={"error": "indisponível"})
            return _nominatim_ok(request)

        provider = self._provider(handler, max_attempts=3)

        resultado = provider.geocode_street("berredos")

        assert resultado is not None
        assert tentativas["n"] == 2  # 503 é transitório: repetiu e deu certo

    def test_resposta_vazia_devolve_none(self):
        provider = self._provider(lambda request: httpx.Response(200, json=[]))
        assert provider.geocode_street("rua inexistente") is None

    def test_breaker_para_de_pagar_timeout_depois_de_n_falhas(self):
        tentativas = {"n": 0}

        def handler(request):
            tentativas["n"] += 1
            raise httpx.TimeoutException("timeout", request=request)

        provider = self._provider(handler, max_attempts=1)

        for _ in range(3):  # limiar do breaker
            assert provider.geocode_street("berredos") is None

        antes = tentativas["n"]
        assert provider.geocode_street("berredos") is None
        # Breaker aberto: nem tentou — o ponto é não pagar o timeout de novo.
        assert tentativas["n"] == antes

    def test_sucesso_zera_as_falhas_do_breaker(self):
        modo = {"falha": True}

        def handler(request):
            if modo["falha"]:
                raise httpx.TimeoutException("timeout", request=request)
            return _nominatim_ok(request)

        provider = NominatimProvider(
            "https://geo.example",
            client=_transport(handler),
            sleeper=lambda _s: None,
            rate_limit_s=0,
            max_attempts=1,
            breaker=CircuitBreaker(2, 60),
        )

        assert provider.geocode_street("berredos") is None  # falha 1
        modo["falha"] = False
        assert provider.geocode_street("berredos") is not None  # zera o contador
        modo["falha"] = True
        assert provider.geocode_street("berredos") is None  # falha 1 de novo

        # Não abriu: se o sucesso não tivesse zerado, aqui já seria a 2ª falha.
        assert provider._breaker.is_open is False

    def test_rate_limit_espera_o_intervalo_minimo(self):
        dormidas = []
        relogio = _Relogio(100.0)
        provider = NominatimProvider(
            "https://geo.example",
            client=_transport(_nominatim_ok),
            sleeper=dormidas.append,
            clock=relogio,
            rate_limit_s=1.0,
        )

        provider.geocode_street("berredos")
        relogio.avancar(0.25)
        provider.geocode_street("das flores")

        assert dormidas == [pytest.approx(0.75)]


# ══════════════════════════════════════════════════════
# 8. Resolvedor do "entre" em lote — o par que chega ao nome (D12)
# ══════════════════════════════════════════════════════


def _cache(db, rua="berredos", bairro="Centro", cidade="Osasco", uf="SP", intersecoes=None, lat=-23.5):
    """Linha do cache para a rua pedida (por padrão, com duas interseções)."""
    db.add(
        GeocodeCacheModel(
            chave=chave_rua(rua, bairro, cidade, uf),
            lat=lat,
            lng=-46.6,
            rua=rua,
            bairro=bairro,
            cidade=cidade,
            uf=uf,
            intersecoes=intersecoes if intersecoes is not None else _intersecoes(),
        )
    )
    db.commit()


def _intersecoes():
    return [{"nome": "Rua A", "numero": 100}, {"nome": "Rua B", "numero": 200}]


class TestChaveDoContato:
    """A chave (D12) usada para achar o cache do logradouro do contato."""

    def test_defaults_entram_quando_o_contato_nao_traz_cidade_uf(self):
        assert chave_do_contato(_cliente(), "Belém", "PA") == chave_rua("berredos", "Centro", "Belém", "PA")

    def test_cidade_propria_do_contato_vence_o_default(self):
        cliente = _cliente(cidade="Osasco", uf="SP")
        assert chave_do_contato(cliente, "Belém", "PA") == chave_rua("berredos", "Centro", "Osasco", "SP")

    @pytest.mark.parametrize("rua", ["", "   ", "A definir", "a definir"])
    def test_placeholder_de_logradouro_nao_tem_chave(self, rua):
        assert chave_do_contato(_cliente(rua=rua)) is None


class TestIntersecoesDaChave:
    def test_sem_linha_no_cache_devolve_vazio(self, db):
        assert GeocodingService(db).intersecoes_da_chave("chave-que-nao-existe") == []

    def test_coluna_com_dict_nao_vira_lista_de_chaves(self, db):
        """JSON como dict (coluna editada à mão) não pode virar interseção."""
        chave = chave_rua("berredos", "Centro", "Osasco", "SP")
        db.add(GeocodeCacheModel(chave=chave, lat=-23.5, lng=-46.6, rua="berredos", intersecoes={"nome": "Rua A"}))
        db.commit()

        assert GeocodingService(db).intersecoes_da_chave(chave) == []


class TestResolverEntreRuas:
    """Varredura em lote: 1 leitura por RUA e par por número do contato (D12)."""

    def test_memoiza_uma_leitura_por_rua(self, db):
        _cache(db, rua="berredos")
        _cache(db, rua="das flores", intersecoes=[{"nome": "Rua C", "numero": 10}, {"nome": "Rua D", "numero": 90}])
        resolver = GeocodingService(db).resolvedor_entre_ruas()

        for numero in ("110", "145", "190"):
            assert resolver.do_contato(_cliente(numero=numero, cidade="Osasco", uf="SP")) == "Rua A e Rua B"
        resolver.do_contato(_cliente(rua="das flores", numero="50", cidade="Osasco", uf="SP"))

        # 4 contatos, 2 ruas → 2 leituras de cache (não 4).
        assert resolver.leituras == 2

    def test_par_muda_com_o_numero_do_mesmo_logradouro(self, db):
        _cache(
            db,
            intersecoes=[
                {"nome": "Rua A", "numero": 100},
                {"nome": "Rua B", "numero": 200},
                {"nome": "Rua C", "numero": 300},
            ],
        )
        resolver = GeocodingService(db).resolvedor_entre_ruas()

        assert resolver.do_contato(_cliente(numero="150", cidade="Osasco", uf="SP")) == "Rua A e Rua B"
        assert resolver.do_contato(_cliente(numero="250", cidade="Osasco", uf="SP")) == "Rua B e Rua C"
        assert resolver.leituras == 1  # mesma rua, um cache

    @pytest.mark.parametrize("numero", ["50", "S/N", None, ""])
    def test_numero_sem_par_que_o_cerque_devolve_none(self, db, numero):
        _cache(db)
        resolver = GeocodingService(db).resolvedor_entre_ruas()

        assert resolver.do_contato(_cliente(numero=numero, cidade="Osasco", uf="SP")) is None

    def test_rua_sem_cache_nao_chama_o_provedor(self, db):
        provider = MockGeocodingProvider()
        resolver = GeocodingService(db, provider=provider).resolvedor_entre_ruas()

        assert resolver.do_contato(_cliente(cidade="Osasco", uf="SP")) is None
        assert provider.chamadas == 0  # derivar é ler cache, nunca consultar

    def test_placeholder_de_logradouro_nem_le_o_cache(self, db):
        resolver = GeocodingService(db).resolvedor_entre_ruas()

        assert resolver.do_contato(_cliente(rua="A definir")) is None
        assert resolver.leituras == 0

    def test_defaults_de_cidade_uf_valem_na_varredura(self, db):
        """Contato sem cidade/UF só acha o cache porque o default entra na chave."""
        from app.application.settings.settings_service import SettingsService

        settings_svc = SettingsService(db)
        settings_svc.seed_defaults()
        settings_svc.update("contacts.default_city", "Osasco")
        settings_svc.update("contacts.default_uf", "SP")
        _cache(db, cidade="Osasco", uf="SP")

        resolver = GeocodingService(db).resolvedor_entre_ruas()
        assert resolver.do_contato(_cliente(numero="145")) == "Rua A e Rua B"
