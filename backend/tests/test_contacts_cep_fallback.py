"""Fase 2, etapa 9 — fallback de CEP (ViaCEP → BrasilAPI → PontoFato).

Cobre o que o catálogo de APIs recomendou e o que o `curl` provou no endereço de
aceite (CEP 66811-120):

- parsing dos dois provedores nas formas reais de resposta (`MockTransport`);
- cadeia com ordem fixa e tolerância a provedor fora do ar;
- **só entra quando o OSM não achou o logradouro** (D2);
- origem registrada no cache (`provider`), nunca mentindo que foi o OSM;
- desligável por env; nada de rede quando não há CEP.
"""

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.contacts.geocoding import (
    STATUS_NAO_ENCONTRADO,
    STATUS_OK,
    GeocodingService,
    chave_rua,
)
from app.core.config import settings
from app.domain.client.entity import Client
from app.domain.delivery.routing import GeocodeResult, MockGeocodingProvider
from app.infrastructure.database.base import Base
from app.infrastructure.geocoding.cep import (
    BrasilApiCepClient,
    CepFallback,
    EnderecoCep,
    PontoFatoCepClient,
    somente_digitos_cep,
)
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel

import app.infrastructure.repositories.settings_model  # noqa: F401
import app.infrastructure.repositories.geocode_cache_model  # noqa: F401


CEP_ACEITE = "66811-120"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _cliente(
    codigo="000001", rua="Passagem Ivan Leao", numero="45", bairro="Agulha", cidade="Belém", uf="PA", cep=None
):
    return Client(
        codigo=codigo,
        nome="Contato",
        telefone=f"9190000{codigo}",
        rua=rua,
        numero=numero,
        bairro=bairro,
        cidade=cidade,
        uf=uf,
        cep=cep,
    )


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


class _CepFake:
    """Fake da cadeia — determinístico e sem rede."""

    def __init__(self, endereco=None):
        self.endereco = endereco
        self.chamadas = 0
        self.ceps = []

    def buscar(self, cep):
        self.chamadas += 1
        self.ceps.append(cep)
        return self.endereco


class _ViaCepFake:
    def __init__(self, cep):
        self.cep = cep
        self.chamadas = 0

    def buscar_cep(self, uf, cidade, rua):
        self.chamadas += 1
        return self.cep


# ═══════════════════════════════════════════════════════════
# 1. Normalização do CEP
# ═══════════════════════════════════════════════════════════


class TestSomenteDigitosCep:
    def test_formata_e_limpa(self):
        assert somente_digitos_cep("66811-120") == "66811120"
        assert somente_digitos_cep("66.811-120") == "66811120"
        assert somente_digitos_cep(66811120) == "66811120"
        assert somente_digitos_cep(" 66811120 ") == "66811120"

    def test_invalido_vira_vazio(self):
        assert somente_digitos_cep("") == ""
        assert somente_digitos_cep(None) == ""
        assert somente_digitos_cep("123") == ""  # curto demais
        assert somente_digitos_cep("123456789") == ""  # longo demais


# ═══════════════════════════════════════════════════════════
# 2. Parsing dos provedores (resposta real, via MockTransport)
# ═══════════════════════════════════════════════════════════


def _brasilapi_ok(request: httpx.Request) -> httpx.Response:
    """Forma real do `/api/cep/v2/{cep}` (curlado no CEP de aceite)."""
    assert "/api/cep/v2/66811120" in str(request.url)
    return httpx.Response(
        200,
        json={
            "cep": "66811120",
            "state": "PA",
            "city": "Belém",
            "neighborhood": "Agulha (Icoaraci)",
            "street": "Passagem Ivan Leão",
            "service": "open-cep",
            "location": {
                "type": "Point",
                "coordinates": {"longitude": "-48.50444", "latitude": "-1.45583"},
            },
        },
    )


def _pontofato_ok(request: httpx.Request) -> httpx.Response:
    """Forma real do `/api/cep/{cep}` (curlado no CEP de aceite)."""
    assert "/api/cep/66811120" in str(request.url)
    return httpx.Response(
        200,
        json={
            "cep": "66811-120",
            "pontos": [
                {
                    "cep": "66811-120",
                    "logradouro": "ALAMEDA SEM DENOMINACAO",
                    "numero": "183",
                    "bairro": "AGULHA",
                    "cidade": "Belém",
                    "uf": "PA",
                    "lat": -1.304775909090909,
                    "lon": -48.47364909090909,
                }
            ],
        },
    )


class TestBrasilApiCepClient:
    def _client(self, handler):
        return BrasilApiCepClient(
            "https://brasilapi.example", client=_transport(handler), sleeper=lambda _s: None, rate_limit_s=0
        )

    def test_le_endereco_e_coordenada(self):
        endereco = self._client(_brasilapi_ok).buscar(CEP_ACEITE)

        assert endereco is not None
        assert endereco.provider == "brasilapi"
        assert endereco.rua == "Passagem Ivan Leão"
        assert endereco.bairro == "Agulha (Icoaraci)"
        assert endereco.cidade == "Belém"
        assert endereco.uf == "PA"
        assert endereco.lat == pytest.approx(-1.45583)
        assert endereco.lng == pytest.approx(-48.50444)
        assert endereco.tem_coordenada is True

    def test_cep_invalido_nao_consulta(self):
        tentativas = {"n": 0}

        def handler(request):
            tentativas["n"] += 1
            return _brasilapi_ok(request)

        assert self._client(handler).buscar("123") is None
        assert tentativas["n"] == 0

    def test_resposta_sem_coordenada_nao_vira_endereco_util(self):
        client = self._client(
            lambda request: httpx.Response(
                200,
                json={"cep": "66811120", "state": "PA", "city": "Belém", "street": "Passagem Ivan Leão"},
            )
        )
        endereco = client.buscar(CEP_ACEITE)
        assert endereco is not None
        assert endereco.tem_coordenada is False

    def test_http_error_devolve_none(self):
        client = self._client(lambda request: httpx.Response(500, json={"error": "boom"}))
        assert client.buscar(CEP_ACEITE) is None


class TestPontoFatoCepClient:
    def _client(self, handler):
        return PontoFatoCepClient(
            "https://pontofato.example", client=_transport(handler), sleeper=lambda _s: None, rate_limit_s=0
        )

    def test_le_o_primeiro_ponto_com_coordenada(self):
        endereco = self._client(_pontofato_ok).buscar(CEP_ACEITE)

        assert endereco is not None
        assert endereco.provider == "pontofato"
        assert endereco.cidade == "Belém"
        assert endereco.uf == "PA"
        assert endereco.lat == pytest.approx(-1.304775909090909)
        assert endereco.lng == pytest.approx(-48.47364909090909)

    def test_pula_ponto_sem_coordenada_e_usa_o_proximo(self):
        client = self._client(
            lambda request: httpx.Response(
                200,
                json={
                    "cep": "66811-120",
                    "pontos": [
                        {"logradouro": "SEM COORDENADA", "lat": None, "lon": None},
                        {"logradouro": "COM COORDENADA", "lat": -1.30, "lon": -48.47},
                    ],
                },
            )
        )
        endereco = client.buscar(CEP_ACEITE)
        assert endereco is not None
        assert endereco.rua == "COM COORDENADA"

    def test_sem_pontos_devolve_none(self):
        client = self._client(lambda request: httpx.Response(200, json={"cep": "66811-120", "pontos": []}))
        assert client.buscar(CEP_ACEITE) is None


# ═══════════════════════════════════════════════════════════
# 3. Cadeia — ordem e tolerância a falha
# ═══════════════════════════════════════════════════════════


class _ClienteFixo:
    """Cliente de CEP determinístico (devolve sempre o mesmo resultado)."""

    def __init__(self, resultado, nome="fixo"):
        self._resultado = resultado
        self.name = nome
        self.chamadas = 0

    def buscar(self, cep):
        self.chamadas += 1
        return self._resultado


class _ClienteFalho(_ClienteFixo):
    """Cliente que levanta na consulta — prova que a cadeia não quebra."""

    def __init__(self, nome="falho"):
        super().__init__(None, nome=nome)

    def buscar(self, cep):
        self.chamadas += 1
        raise RuntimeError("provedor fora do ar")


class TestCepFallback:
    def test_primeiro_provedor_com_coordenada_vence(self):
        primeiro = _ClienteFixo(EnderecoCep(cep="66811-120", lat=-1.45, lng=-48.50, provider="brasilapi"), "brasilapi")
        segundo = _ClienteFixo(EnderecoCep(cep="66811-120", lat=-1.30, lng=-48.47, provider="pontofato"), "pontofato")
        cadeia = CepFallback([primeiro, segundo])

        endereco = cadeia.buscar(CEP_ACEITE)

        assert endereco.provider == "brasilapi"
        assert segundo.chamadas == 0  # o 2º nem é consultado

    def test_provedor_fora_do_ar_cai_para_o_proximo(self):
        falho = _ClienteFalho("brasilapi")
        segundo = _ClienteFixo(EnderecoCep(cep="66811-120", lat=-1.30, lng=-48.47, provider="pontofato"), "pontofato")
        cadeia = CepFallback([falho, segundo])

        endereco = cadeia.buscar(CEP_ACEITE)

        assert endereco is not None
        assert endereco.provider == "pontofato"
        assert falho.chamadas == 1

    def test_resultado_sem_coordenada_nao_encerra_a_cadeia(self):
        sem_coord = _ClienteFixo(EnderecoCep(cep="66811-120", cidade="Belém", uf="PA"), "brasilapi")
        com_coord = _ClienteFixo(EnderecoCep(cep="66811-120", lat=-1.30, lng=-48.47, provider="pontofato"), "pontofato")
        cadeia = CepFallback([sem_coord, com_coord])

        assert cadeia.buscar(CEP_ACEITE).provider == "pontofato"

    def test_nenhum_provedor_com_coordenada_devolve_none(self):
        cadeia = CepFallback([_ClienteFixo(EnderecoCep(cep="66811-120"))])
        assert cadeia.buscar(CEP_ACEITE) is None

    def test_cep_invalido_nao_chama_nenhum_provedor(self):
        cliente = _ClienteFixo(EnderecoCep(cep="66811-120", lat=-1.0, lng=-1.0))
        assert CepFallback([cliente]).buscar("abc") is None
        assert cliente.chamadas == 0


# ═══════════════════════════════════════════════════════════
# 4. Integração com o GeocodingService (o ponto da etapa 9)
# ═══════════════════════════════════════════════════════════


_ENDERECO_ACEITE = EnderecoCep(
    cep=CEP_ACEITE,
    rua="Passagem Ivan Leão",
    bairro="Agulha (Icoaraci)",
    cidade="Belém",
    uf="PA",
    lat=-1.45583,
    lng=-48.50444,
    provider="brasilapi",
)


class TestGeocodingServiceCepFallback:
    def test_osm_nao_achou_mas_o_cep_resolve(self, db):
        provider = MockGeocodingProvider(encontrado=False)
        cadeia = _CepFake(_ENDERECO_ACEITE)
        svc = GeocodingService(db, provider=provider, cep_fallback=cadeia)

        resultado, status = svc.get_or_geocode("Passagem Ivan Leao", "Agulha", "Belém", "PA", cep_hint=CEP_ACEITE)

        assert status == STATUS_OK
        assert resultado.lat == pytest.approx(-1.45583)
        assert resultado.lng == pytest.approx(-48.50444)
        assert resultado.cep == CEP_ACEITE
        assert cadeia.chamadas == 1

    def test_origem_do_fallback_fica_gravada_no_cache(self, db):
        """O cache não pode dizer que o OSM respondeu o que veio do CEP."""
        svc = GeocodingService(
            db, provider=MockGeocodingProvider(encontrado=False), cep_fallback=_CepFake(_ENDERECO_ACEITE)
        )
        svc.get_or_geocode("Passagem Ivan Leao", "Agulha", "Belém", "PA", cep_hint=CEP_ACEITE)

        linha = db.query(GeocodeCacheModel).one()
        assert linha.provider == "brasilapi"
        assert linha.lat == pytest.approx(-1.45583)
        assert linha.chave == chave_rua("Passagem Ivan Leao", "Agulha", "Belém", "PA")

    def test_sem_cep_e_sem_viacep_nao_consulta_a_cadeia(self, db):
        provider = MockGeocodingProvider(encontrado=False)
        cadeia = _CepFake(_ENDERECO_ACEITE)
        svc = GeocodingService(db, provider=provider, cep_fallback=cadeia)

        # Contato sem CEP e sem cidade/uf: não há como abrir a cadeia.
        resultado, status = svc.get_or_geocode("rua desconhecida")

        assert resultado is None
        assert status == STATUS_NAO_ENCONTRADO
        assert cadeia.chamadas == 0

    def test_viacep_abre_a_cadeia_quando_o_contato_nao_traz_cep(self, db):
        """Cadeia completa: OSM falha → ViaCEP (endereço→CEP) → CEP→coordenada."""
        viacep = _ViaCepFake(CEP_ACEITE)
        cadeia = _CepFake(_ENDERECO_ACEITE)
        svc = GeocodingService(db, provider=MockGeocodingProvider(encontrado=False), viacep=viacep, cep_fallback=cadeia)

        resultado, status = svc.get_or_geocode("Passagem Ivan Leao", "Agulha", "Belém", "PA")

        assert status == STATUS_OK
        assert viacep.chamadas == 1
        assert cadeia.ceps == ["66811120"]  # a cadeia recebe o CEP normalizado

    def test_cep_do_contato_dispensa_o_viacep(self, db):
        viacep = _ViaCepFake("00000-000")
        cadeia = _CepFake(_ENDERECO_ACEITE)
        svc = GeocodingService(db, provider=MockGeocodingProvider(encontrado=False), viacep=viacep, cep_fallback=cadeia)

        svc.get_or_geocode("Passagem Ivan Leao", "Agulha", "Belém", "PA", cep_hint=CEP_ACEITE)

        assert viacep.chamadas == 0  # o CEP do contato já bastava
        assert cadeia.ceps == ["66811120"]

    def test_osm_achou_o_cep_nem_e_consultado(self, db):
        provider = MockGeocodingProvider(GeocodeResult(lat=-1.30, lng=-48.47, cep=CEP_ACEITE))
        cadeia = _CepFake(_ENDERECO_ACEITE)
        svc = GeocodingService(db, provider=provider, cep_fallback=cadeia)

        resultado, status = svc.get_or_geocode("berredos", "Centro", "Belém", "PA", cep_hint=CEP_ACEITE)

        assert status == STATUS_OK
        assert resultado.lat == pytest.approx(-1.30)
        assert cadeia.chamadas == 0  # fallback é segunda opção, não primeira

    def test_negativo_e_cacheado_quando_nem_o_cep_resolve(self, db):
        provider = MockGeocodingProvider(encontrado=False)
        cadeia = _CepFake(None)  # cadeia não achou nada
        svc = GeocodingService(db, provider=provider, cep_fallback=cadeia)

        assert svc.get_or_geocode("xyz", "", "Belém", "PA", cep_hint=CEP_ACEITE)[1] == STATUS_NAO_ENCONTRADO
        # A 2ª chamada sai do cache: nem provedor nem cadeia são consultados.
        assert svc.get_or_geocode("xyz", "", "Belém", "PA", cep_hint=CEP_ACEITE)[1] == STATUS_NAO_ENCONTRADO
        assert cadeia.chamadas == 1

    def test_desligado_por_env_nao_consulta_a_cadeia(self, db, monkeypatch):
        monkeypatch.setattr(settings, "cep_fallback_enabled", False)
        cadeia = _CepFake(_ENDERECO_ACEITE)
        svc = GeocodingService(db, provider=MockGeocodingProvider(encontrado=False), cep_fallback=cadeia)

        assert svc.get_or_geocode("rua x", "", "Belém", "PA", cep_hint=CEP_ACEITE)[1] == STATUS_NAO_ENCONTRADO
        assert cadeia.chamadas == 0

    def test_geocodificar_cliente_preenche_cep_coordenada_e_status(self, db):
        """O caminho real do job GEOCODE: o contato sai com CEP e lat/lng."""
        svc = GeocodingService(
            db, provider=MockGeocodingProvider(encontrado=False), cep_fallback=_CepFake(_ENDERECO_ACEITE)
        )
        cliente = _cliente(cep=CEP_ACEITE)

        assert svc.geocodificar_cliente(cliente) == STATUS_OK

        assert cliente.geocode_status == STATUS_OK
        assert cliente.cep == CEP_ACEITE
        assert cliente.lat == pytest.approx(-1.45583)
        assert cliente.lng == pytest.approx(-48.50444)

    def test_geocodificar_cliente_sem_cep_usa_o_do_viacep(self, db):
        viacep = _ViaCepFake(CEP_ACEITE)
        svc = GeocodingService(
            db,
            provider=MockGeocodingProvider(encontrado=False),
            viacep=viacep,
            cep_fallback=_CepFake(_ENDERECO_ACEITE),
        )
        cliente = _cliente(cep=None, cidade="Belém", uf="PA")

        assert svc.geocodificar_cliente(cliente) == STATUS_OK

        assert cliente.cep == CEP_ACEITE
        assert cliente.lat == pytest.approx(-1.45583)


# ═══════════════════════════════════════════════════════════
# 5. Config — a cadeia sai dos settings na ordem fixa
# ═══════════════════════════════════════════════════════════


class TestConfigDaCadeia:
    def test_ordem_e_ligada_por_env(self, monkeypatch):
        from app.infrastructure.geocoding.cep import build_cep_clients

        monkeypatch.setattr(settings, "brasilapi_enabled", True)
        monkeypatch.setattr(settings, "pontofato_enabled", True)
        nomes = [c.name for c in build_cep_clients()]
        assert nomes == ["brasilapi", "pontofato"]

    def test_desligar_um_provedor_tira_da_cadeia(self, monkeypatch):
        from app.infrastructure.geocoding.cep import build_cep_clients

        monkeypatch.setattr(settings, "brasilapi_enabled", False)
        monkeypatch.setattr(settings, "pontofato_enabled", True)
        assert [c.name for c in build_cep_clients()] == ["pontofato"]
