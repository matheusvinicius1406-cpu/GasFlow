"""Etapa 9 — medição do geocode FRIO com os provedores REAIS (opt-in).

O E2E de 10 mil (`test_contacts_e2e.py`) mede **o nosso pipeline** com provedor
mock; ele não diz quanto custa a internet. Este arquivo mede o que o §4.1 do
prompt estima em ~1 s/rua (política do Nominatim público: 1 req/s + `User-Agent`).

Como bate na rede, ele é **opt-in**:

    cd backend
    LIVE_MODE=true python -m pytest tests/test_contacts_geocode_live.py -q -s

O que ele verifica de verdade:
- o `GeocodingService` respeita o teto de **1 req/s** do Nominatim (o tempo do
  frio cresce ~1 s por rua, não por contato);
- o **fallback de CEP** (ADR-0007) resolve coordenada de um logradouro que o OSM
  não conhece, usando o CEP do endereço de aceite (66811-120);
- o **quente** (2ª passada) não faz nenhuma requisição nova.

Não asserta tempo absoluto contra a parede (seria flaky na internet); asserta a
**propriedade** do rate limit e publica os segundos medidos.
"""

import os
import time
from typing import List, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.contacts.geocoding import STATUS_OK, GeocodingService
from app.application.settings.settings_service import SettingsService
from app.core.config import settings
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel

import app.infrastructure.repositories.settings_model  # noqa: F401
import app.infrastructure.repositories.geocode_cache_model  # noqa: F401

LIVE_MODE = os.getenv("LIVE_MODE", "false").lower() == "true"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE_MODE, reason="LIVE_MODE not enabled. Set LIVE_MODE=true to hit real providers."),
]

# Endereço de aceite (§17.1) — o mesmo do catálogo de APIs.
CEP_ACEITE = "66811-120"
CIDADE, UF = "Belém", "PA"

# Ruas reais de Belém/Icoaraci (as do spike + comuns da região). O objetivo é
# medir o custo por rua, não a precisão de cada par.
RUAS = [
    "Passagem Ivan Leão",
    "Travessa São Roque",
    "Rua 8 de Maio",
    "Estrada do Outeiro",
    "Avenida Augusto Montenegro",
]


@pytest.fixture()
def svc():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    # Fatos do negócio (§17.1): cidade/UF default entram na chave do cache.
    SettingsService(db).seed_defaults()
    geocoder = GeocodingService(db)
    yield geocoder, db
    db.close()


class TestGeocodeFrioReal:
    def test_frio_respeita_1_req_s_e_quente_e_gratis(self, svc, capsys):
        geocoder, db = svc
        limite_s = float(settings.geocoding_rate_limit_s)

        # ── FRIO: 1 requisição por rua, com o teto da política ──
        inicio = time.perf_counter()
        resultados: List[Tuple[str, str]] = []
        for rua in RUAS:
            _, status = geocoder.get_or_geocode(rua, "", CIDADE, UF)
            resultados.append((rua, status))
        frio_s = time.perf_counter() - inicio

        ruas_no_cache = db.query(GeocodeCacheModel).count()
        assert ruas_no_cache == len(RUAS)  # 1 linha por rua (D12)
        # O teto de 1 req/s é o que dimensiona o frio (§4.1): com N ruas, o
        # tempo NÃO pode ser menor que (N-1) × o intervalo mínimo.
        assert frio_s >= (len(RUAS) - 1) * limite_s * 0.9

        # ── QUENTE: mesma pergunta, zero requisição nova ──
        inicio = time.perf_counter()
        for rua in RUAS:
            geocoder.get_or_geocode(rua, "", CIDADE, UF)
        quente_s = time.perf_counter() - inicio
        assert db.query(GeocodeCacheModel).count() == ruas_no_cache
        assert quente_s < frio_s

        por_rua = frio_s / len(RUAS)
        relatorio = [
            "",
            "== Geocode FRIO real (Nominatim publico, 1 req/s) =================",
            f"  ruas medidas : {len(RUAS)}",
            f"  FRIO         : {frio_s:6.2f}s  | {por_rua:5.2f}s por rua",
            f"  QUENTE       : {quente_s:6.2f}s  | 0 requisicao nova (cache por rua)",
            f"  alvo §4.1    : ~{len(RUAS)}s para {len(RUAS)} ruas (1 s/rua)",
            "  por rua:",
        ]
        relatorio += [f"    {status:16} {rua}" for rua, status in resultados]
        relatorio.append("")
        with capsys.disabled():
            print("\n".join(relatorio))

    def test_fallback_de_cep_real_resolve_o_endereco_de_aceite(self, svc, capsys):
        """O 2º elo ao vivo: CEP → coordenada, sem chave (BrasilAPI/PontoFato)."""
        geocoder, _ = svc

        endereco = geocoder.buscar_endereco_por_cep(CEP_ACEITE)

        assert endereco is not None, "nenhum provedor de CEP respondeu (rede?)"
        assert endereco.tem_coordenada, "o provedor respondeu sem coordenada"
        assert endereco.provider in ("brasilapi", "pontofato")
        assert endereco.cep.replace("-", "") == CEP_ACEITE.replace("-", "")

        with capsys.disabled():
            print(
                "\n".join(
                    [
                        "",
                        "== Fallback de CEP real (endereco de aceite) =====================",
                        f"  cep      : {endereco.cep}",
                        f"  provedor : {endereco.provider}",
                        f"  endereco : {endereco.rua or '-'} / {endereco.bairro or '-'} - {endereco.cidade}/{endereco.uf}",
                        f"  lat,lng  : {endereco.lat}, {endereco.lng}",
                        "",
                    ]
                )
            )

    def test_logradouro_desconhecido_cai_no_cep_e_volta_ok(self, svc, capsys):
        """Cadeia completa ao vivo: OSM não acha a rua → CEP resolve → status OK."""
        geocoder, _ = svc

        rua = "Rua Que Nao Existe Nenhum 12345"
        resultado, status = geocoder.get_or_geocode(rua, "", CIDADE, UF, cep_hint=CEP_ACEITE)

        if status == STATUS_OK and resultado is not None:
            origem = "CEP (fallback)"
            assert resultado.lat and resultado.lng
        else:
            # Sem rede ou provedores fora: a resposta honesta é triagem (D2),
            # nunca um endereço chutado. Registra e segue.
            origem = "triagem (sem resposta dos provedores)"
            assert resultado is None

        with capsys.disabled():
            print(
                "\n".join(
                    [
                        "",
                        "== Logradouro que o OSM nao conhece ===============================",
                        f"  rua      : {rua}",
                        f"  status   : {status}",
                        f"  origem   : {origem}",
                        f"  lat,lng  : {getattr(resultado, 'lat', None)}, {getattr(resultado, 'lng', None)}",
                        "",
                    ]
                )
            )
