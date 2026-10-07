"""Fase 2, etapa 9 + Fase 3, etapa 6 — E2E de 10.000 contatos + medição frio/quente.

Roda o pipeline COMPLETO do renomeador sobre um `.vcf` sintético de 10.000
contatos, pelos serviços de aplicação (sem HTTP):

    parse (.vcf) → upsert em blocos → job GEOCODE (bounded-batch)
    → preview → job APPLY (bounded-batch) → formatação do export

**Não toca a rede.** O provedor é o `MockGeocodingProvider` (contável), então o
"frio × quente" é medido em **requisições ao provedor**, não em milissegundos de
internet — a métrica que o ADR-0004 usa para dimensionar o frio (D12: 1
requisição por RUA, não por contato).

Duas travas daqui valem para os dois testes da classe:

- **`VIACEP`/`CEP_FALLBACK` desligados no fixture** (autouse). Sem isto o
  passe frio faz 1 chamada HTTP **por rua** para enriquecer o CEP que o mock
  não trouxe — medido na rede de desenvolvimento: **0,826 s por rua** ligado
  contra **0,002 s** desligado, ou seja 200 ruas ≈ 3 min só de ViaCEP. O
  relatório deixaria de medir o provedor e passaria a medir a internet, e o
  contrato "não toca a rede" do cabeçalho seria falso. O CEP do nome de rota
  vem do `.vcf` (normalize_cep), não do ViaCEP.
- **O passe "entre ruas"** roda em duas versões: a Fase 2 (mock devolve as
  interseções) e a **Fase 3 com o provider IBGE** (`TestRenomeadorE2E10kComIBGE`),
  que semeia as tabelas do CNEFE/Faces e deixa o `IbgeEntreRuasProvider`
  preencher `geocode_cache.intersecoes` sem rede nenhuma (D18).

O que está travado aqui:
- 10.000 contatos ponta a ponta, sem perder nenhum;
- **frio** = 1 requisição por rua distinta (200 ruas → 200 requisições);
- **quente** = 0 requisições (cache por rua do ADR-0004);
- o job avança em faixas (bounded-batch), nunca num request só;
- o nome de rota sai no formato D5 e o 2º apply é idempotente;
- com IBGE: 200/200 ruas com `intersecoes` + `provider='ibge'`, e o 2º passe
  não tem NADA a fazer (total=0).

Rode com `-s` para ver o relatório de medição.
"""

import re
import time
from typing import List, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.contacts.formatter import formatar_nome_rota
from app.application.contacts.geocoding import STATUS_OK, GeocodingService
from app.application.contacts.jobs import ContactJobService
from app.application.contacts.organizer import ContactOrganizer, build_rename_rule
from app.application.contacts.service import ContactService
from app.application.contacts.vcf import parse_vcf
from app.core.config import settings
from app.domain.delivery.routing import GeocodeResult, MockGeocodingProvider
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

import app.infrastructure.repositories.settings_model  # noqa: F401
import app.infrastructure.repositories.geocode_cache_model  # noqa: F401
import app.infrastructure.repositories.contact_job_model  # noqa: F401
import app.infrastructure.repositories.ibge_model  # noqa: F401 — tabelas da Fase 3

from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel
from app.infrastructure.repositories.ibge_model import (
    CnefeEnderecoModel,
    LogradouroFaceModel,
    LogradouroNoModel,
)

N_CONTATOS = 10_000
N_RUAS = 200
POR_RUA = N_CONTATOS // N_RUAS  # 50 contatos por rua

# Formato D5: `{codigo}= {rua} Nº {numero} entre {A} e {B} - CEP {cep} ({nome})`.
# O "entre" é OBRIGATÓRIO aqui: o provedor do teste traz interseções para toda
# rua, então o par derivado (D12) tem de aparecer em TODOS os nomes.
_NOME_ROTA = re.compile(r"^\d+= Rua Teste \d{3} Nº \d+ entre .+ e .+ - CEP \d{5}-\d{3} \(Cliente \d{5}\)$")


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    # Fatos do negócio (§17.1): cidade/UF default do cliente. Sem eles, o
    # geocoder preencheria o UF do contato na 1ª passada e a chave do cache
    # (rua|bairro|cidade|uf, D12) mudaria entre frio e quente — 1 requisição
    # extra por rua num re-run. Com o default definido (produção), a chave é
    # estável.
    from app.application.settings.settings_service import SettingsService

    SettingsService(session).seed_defaults()
    yield session
    session.close()


@pytest.fixture()
def repo(db):
    return SQLAlchemyClientRepository(db, tenant_id="default")


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    """E2E hermético: mede o PROVEDOR, não a latência da internet.

    Com `VIACEP_ENABLED=true` (default) o passe frio chama o ViaCEP uma vez por
    rua para enriquecer o CEP que o mock não devolve — 0,826 s por rua medido,
    contra 0,002 s sem rede. O relatório de frio/quente sairia medindo a
    internet. O CEP do nome de rota vem do `.vcf`, então desligar não muda o
    que é assertado.
    """
    monkeypatch.setattr(settings, "viacep_enabled", False)
    monkeypatch.setattr(settings, "cep_fallback_enabled", False)


def _gerar_vcf(n_contatos: int = N_CONTATOS, n_ruas: int = N_RUAS) -> str:
    """`.vcf` sintético: `n_ruas` logradouros, cada um com vários contatos.

    Todo contato tem telefone único (a chave do upsert) e endereço estruturado
    no `ADR` — é o caminho que o parser estendido lê do arquivo real.
    """
    linhas: List[str] = []
    for i in range(n_contatos):
        k = i % n_ruas
        numero = 100 + (i // n_ruas) * 10
        cep = f"{66810000 + k:08d}"
        linhas += [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:Cliente {i:05d}",
            f"TEL;TYPE=CELL:+9198{i:07d}",
            f"ADR;TYPE=HOME:;;Rua Teste {k:03d} {numero};Bairro {k % 20:02d};Belém;{cep};Brasil",
            "END:VCARD",
        ]
    return "\n".join(linhas) + "\n"


def _consumir_ate_concluir(jobs: ContactJobService, job_id: str, limite: int) -> Tuple[int, int]:
    """Avança o job em faixas. Devolve (nº de faixas, maior faixa processada)."""
    faixas = 0
    maior_faixa = 0
    while True:
        antes = jobs.status(job_id)["processados"]
        estado = jobs.processar_proximo_lote(job_id, limite=limite)
        faixas += 1
        maior_faixa = max(maior_faixa, estado["processados"] - antes)
        if estado["status"] == "CONCLUIDO":
            return faixas, maior_faixa


@pytest.mark.slow
class TestRenomeadorE2E10k:
    """Gate da etapa 9: `pytest tests/test_contacts_e2e.py -q -s` (~2,5 min)."""

    def test_10k_ponta_a_ponta_com_medicao_de_frio_e_quente(self, db, repo, capsys):
        relatorio: List[str] = []

        # ── 1. Parse + upsert em blocos ────────────────────────
        t0 = time.perf_counter()
        contatos = parse_vcf(_gerar_vcf())
        t_parse = time.perf_counter() - t0
        assert len(contatos) == N_CONTATOS  # nada perdido no parser

        t0 = time.perf_counter()
        resultados = ContactService(repo).sync_batch(contatos)  # blocos de 500
        t_upsert = time.perf_counter() - t0
        assert sum(1 for r in resultados if r.get("action") == "created") == N_CONTATOS
        assert len(repo.listar_todos()) == N_CONTATOS  # nenhum contato perdido

        # Interseções para TODA rua: é o dado que a etapa 6 busca no OSM (e o
        # OSM-BR quase não tem). Os números do .vcf vão de 100 a 590, então
        # [50, 700] cerca qualquer um deles.
        provider = MockGeocodingProvider(
            GeocodeResult(
                lat=-1.3,
                lng=-48.47,
                intersecoes=[{"nome": "Rua Alpha", "numero": 50}, {"nome": "Rua Beta", "numero": 700}],
            )
        )
        geocoder = GeocodingService(db, provider=provider)
        jobs = ContactJobService(db, repo, geocoding=geocoder)

        # ── 2. Geocode FRIO (bounded-batch) ────────────────────
        job = jobs.criar_job("GEOCODE")
        assert job["total"] == N_CONTATOS

        t0 = time.perf_counter()
        faixas, maior_faixa = _consumir_ate_concluir(jobs, job["id"], limite=100)
        t_frio = time.perf_counter() - t0

        # D12/ADR-0004: o custo do frio é por RUA, não por contato.
        requisicoes_frio = provider.chamadas
        assert requisicoes_frio == N_RUAS
        # Bounded-batch: nenhuma faixa passou do limite (nada de request gigante).
        assert maior_faixa <= 100
        assert faixas >= N_CONTATOS // 100

        # ── 3. Geocode QUENTE (cache por rua) ──────────────────
        quente_antes = provider.chamadas
        t0 = time.perf_counter()
        for cliente in repo.listar_todos():
            assert geocoder.geocodificar_cliente(cliente) == STATUS_OK
        t_quente = time.perf_counter() - t0
        assert provider.chamadas == quente_antes  # 0 requisições: cache quente

        # ── 4. Preview + nome de rota (formato D5) ─────────────
        regra = build_rename_rule(pattern_endereco=True)
        organizer = ContactOrganizer(db, repo)
        previa = organizer.preview_rename(regra, page=1, page_size=20)
        assert previa["total"] == N_CONTATOS
        for mudanca in previa["changes"]:
            assert _NOME_ROTA.match(mudanca["after"]), mudanca["after"]

        # ── 5. Apply no CRM (bounded-batch) ────────────────────
        job_apply = jobs.criar_job("APPLY", regra=regra)
        assert job_apply["total"] == N_CONTATOS
        t0 = time.perf_counter()
        faixas_apply, maior_faixa_apply = _consumir_ate_concluir(jobs, job_apply["id"], limite=500)
        t_apply = time.perf_counter() - t0

        estado_apply = jobs.status(job_apply["id"])
        assert estado_apply["alterados"] == N_CONTATOS
        assert maior_faixa_apply <= 500

        # ── 6. Idempotência: 2º apply não muda nada ────────────
        segundo = ContactOrganizer(db, repo).apply_rename(regra, all_matching=True)
        assert segundo["renamed"] == 0

        # ── 7. Export: o nome de rota sai montado do contato ───
        # Mesmo caminho do export `?formatar_rota=true`: o par derivado entra
        # pela mesma porta, então o export é igual ao que o apply gravou.
        resolvedor = GeocodingService(db).resolvedor_entre_ruas()
        amostra = repo.listar_todos()[:20]
        for cliente in amostra:
            esperado = formatar_nome_rota(cliente, entre_ruas=resolvedor.do_contato(cliente))
            assert _NOME_ROTA.match(esperado), esperado
            assert esperado == cliente.nome  # export == apply
        # 200 ruas, 20 contatos da amostra: o memo evita reler a mesma rua.
        assert resolvedor.leituras <= len(amostra)

        # Relatório em ASCII de propósito: o console do Windows (cp1252)
        # derruba o teste com UnicodeEncodeError em box-drawing/setas.
        relatorio += [
            "",
            "== Etapa 9 - medicao (10.000 contatos / 200 ruas) ==================",
            f"  parse    : {t_parse:7.2f}s",
            f"  upsert   : {t_upsert:7.2f}s  ({len(contatos) // 500} blocos de 500)",
            f"  FRIO     : {t_frio:7.2f}s  | {requisicoes_frio} requisicoes"
            f" ({N_RUAS} ruas x 1) | {faixas} faixas de ate 100",
            f"  QUENTE   : {t_quente:7.2f}s  | {provider.chamadas - requisicoes_frio} requisicoes (cache por rua)",
            f"  apply    : {t_apply:7.2f}s  | {faixas_apply} faixas de ate 500",
            f"  economia : {requisicoes_frio} requisicoes no frio -> 0 no quente",
            "",
        ]
        with capsys.disabled():
            print("\n".join(relatorio))


# ── Fase 3, etapa 6: o mesmo pipeline com o passe do IBGE ─────────────
#
# Grade sintética (D18): uma face horizontal por rua do `.vcf`, `cod_setor`
# próprio (a junção D17 é por `cod_setor + quadra + face`), três âncoras
# CNEFE na linha da face e um nó de via transversal em cada extremidade - é o
# nó que vira "entre" sem query nenhuma.
_MUN_IBGE = "1501402"
_LAT_IBGE = -1.300000
_LNG0_IBGE = -48.470000  # ~222 m de face na latitude de Belem
_LNG1_IBGE = -48.468000
# Âncoras CNEFE (posicao, numero): 35/350/665 cercam os 100..590 do `.vcf`,
# entao o "entre" fecha para TODO contato - e a cobertura do eixo fica em 90%.
_ANCORAS_IBGE = ((0.05, 35), (0.50, 350), (0.95, 665))


def _semear_ibge(db, n_ruas: int = N_RUAS) -> None:
    """Semeia faces + CNEFE + nós para as `n_ruas` ruas do `.vcf`.

    Reproduz a forma medida em Belém (ADR-0008) numa grade: cada rua tem sua
    face, suas âncoras e seu par de cruzamentos próprios.
    """
    for k in range(n_ruas):
        chave = f"rua teste {k:03d}"
        nome = f"Rua Teste {k:03d}"
        setor = f"SET{k:05d}"
        lat = round(_LAT_IBGE - k * 0.00020, 6)  # ~22 m entre ruas vizinhas

        db.add(
            LogradouroFaceModel(
                cod_municipio=_MUN_IBGE,
                cod_setor=setor,
                cod_quadra=1,
                cod_face=1,
                chave_logradouro=chave,
                nome_logradouro=nome,
                geom=[[lat, _LNG0_IBGE], [lat, _LNG1_IBGE]],
            )
        )
        # Extremidade da face = nó compartilhado com a via transversal (D16).
        for (node_lat, node_lng), chave_cruz, nome_cruz in (
            ((lat, _LNG0_IBGE), "rua alpha", "Rua Alpha"),
            ((lat, _LNG1_IBGE), "rua beta", "Rua Beta"),
        ):
            db.add(
                LogradouroNoModel(
                    cod_municipio=_MUN_IBGE,
                    node_lat=node_lat,
                    node_lng=node_lng,
                    chave_logradouro=chave_cruz,
                    nome_logradouro=nome_cruz,
                )
            )
        for i, (frac, numero) in enumerate(_ANCORAS_IBGE):
            db.add(
                CnefeEnderecoModel(
                    cod_municipio=_MUN_IBGE,
                    cod_unico_endereco=f"e2e-{k:03d}-{i}",
                    cod_setor=setor,
                    num_quadra=1,
                    num_face=1,
                    num_endereco=numero,
                    chave_logradouro=chave,
                    chave_nome=f"teste {k:03d}",
                    nome_logradouro=nome,
                    lat=lat,
                    lng=round(_LNG0_IBGE + (_LNG1_IBGE - _LNG0_IBGE) * frac, 7),
                    nv_geo_coord="1",
                )
            )
    db.commit()


@pytest.mark.slow
class TestRenomeadorE2E10kComIBGE:
    """Etapa 6 da Fase 3: pipeline de 10k com `IbgeEntreRuasProvider` (D18).

    Diferente da etapa 9, o passe "entre ruas" não vem do mock do OSM: ele roda
    sobre as tabelas ingeridas do IBGE e precisa provar as três travas do DoD -
    UPDATE-only, idempotência e nenhum toque de rede.
    """

    def test_10k_com_passe_do_ibge(self, db, repo, monkeypatch, capsys):
        # O passe da Fase 3 escolhido por ENVI (D23) - e o município da carga.
        monkeypatch.setattr(settings, "entre_ruas_provider", "ibge")
        monkeypatch.setattr(settings, "ibge_cod_municipio", _MUN_IBGE)
        relatorio: List[str] = []

        # ── 1. Parse + upsert ─────────────────────────────────────
        t0 = time.perf_counter()
        contatos = parse_vcf(_gerar_vcf())
        t_parse = time.perf_counter() - t0
        assert len(contatos) == N_CONTATOS

        t0 = time.perf_counter()
        resultados = ContactService(repo).sync_batch(contatos)
        t_upsert = time.perf_counter() - t0
        assert sum(1 for r in resultados if r.get("action") == "created") == N_CONTATOS
        assert len(repo.listar_todos()) == N_CONTATOS

        # ── 2. Geocode FRIO sem interseções ───────────────────────
        # Sem `intersecoes` no resultado: a coluna fica NULL e é o marcador
        # que o passe da etapa 8 procura (`intersecoes IS NULL`).
        provider = MockGeocodingProvider(GeocodeResult(lat=-1.3, lng=-48.47))
        geocoder = GeocodingService(db, provider=provider)
        jobs = ContactJobService(db, repo, geocoding=geocoder)

        job = jobs.criar_job("GEOCODE")
        assert job["total"] == N_CONTATOS
        t0 = time.perf_counter()
        faixas, maior_faixa = _consumir_ate_concluir(jobs, job["id"], limite=100)
        t_frio = time.perf_counter() - t0
        assert provider.chamadas == N_RUAS  # 1 requisição por rua (D12)
        assert maior_faixa <= 100
        assert faixas >= N_CONTATOS // 100

        cache = db.query(GeocodeCacheModel).all()
        assert len(cache) == N_RUAS
        assert all(linha.intersecoes is None for linha in cache)  # passe pendente
        antes = {linha.id: (linha.lat, linha.lng, linha.cep, linha.provider, linha.chave) for linha in cache}
        status_antes = {c.codigo: c.geocode_status for c in repo.listar_todos()}

        # ── 3. Dado do IBGE ingerido (D18: offline) ───────────────
        t0 = time.perf_counter()
        _semear_ibge(db)
        t_carga = time.perf_counter() - t0

        # ── 4. Passe "entre ruas" com o provider IBGE ─────────────
        t0 = time.perf_counter()
        job_pass = jobs.criar_job("OVERPASS")
        assert job_pass["total"] == N_RUAS  # só as ruas com intersecoes NULL
        faixas_pass, maior_faixa_pass = _consumir_ate_concluir(jobs, job_pass["id"], limite=50)
        t_pass = time.perf_counter() - t0

        estado = jobs.status(job_pass["id"])
        assert estado["processados"] == N_RUAS
        assert estado["alterados"] == N_RUAS  # 200/200 com par (≥2 itens)
        assert maior_faixa_pass <= 50
        metrica = estado["metrica"]
        assert metrica["ruas"] == N_RUAS
        assert metrica["ruas_com_2_ancoras"] == N_RUAS
        assert metrica["ruas_com_2_cruzamentos"] == N_RUAS
        assert metrica["ruas_com_intersecoes"] == N_RUAS
        assert metrica["por_motivo"] == {"ok": N_RUAS}
        assert metrica["por_intersecoes_provider"] == {"ibge": N_RUAS}
        # §10: a grade cobre 90% do eixo de cada face (35→665 sobre 0→1).
        assert round(metrica["cobertura_eixo_soma"] / metrica["cobertura_eixo_ruas"], 4) == 0.9

        # ── 5. UPDATE-only: nada além de interseções mudou ────────
        for linha in db.query(GeocodeCacheModel).all():
            assert antes[linha.id] == (linha.lat, linha.lng, linha.cep, linha.provider, linha.chave)
            assert linha.intersecoes_provider == "ibge"  # D23
            assert len(linha.intersecoes or []) >= 2
        assert status_antes == {c.codigo: c.geocode_status for c in repo.listar_todos()}

        # ── 6. Quente: o 2º passe não tem NADA a fazer ────────────
        job2 = jobs.criar_job("OVERPASS")
        assert job2["total"] == 0  # nenhuma rua com intersecoes NULL
        quente_antes = provider.chamadas
        for cliente in repo.listar_todos():
            assert geocoder.geocodificar_cliente(cliente) == STATUS_OK
        assert provider.chamadas == quente_antes  # 0 requisições no quente

        # ── 7. Idempotência do passe (mesmo lote de novo) ─────────
        job3 = jobs.criar_job("OVERPASS")
        assert job3["total"] == 0

        # ── 8. Preview: o par do IBGE entra no formato D5 ─────────
        regra = build_rename_rule(pattern_endereco=True)
        previa = ContactOrganizer(db, repo).preview_rename(regra, page=1, page_size=20)
        assert previa["total"] == N_CONTATOS
        for mudanca in previa["changes"]:
            assert _NOME_ROTA.match(mudanca["after"]), mudanca["after"]
            assert "entre Rua Alpha e Rua Beta" in mudanca["after"]

        # ── 9. Apply no CRM (bounded-batch) + idempotência ────────
        job_apply = jobs.criar_job("APPLY", regra=regra)
        assert job_apply["total"] == N_CONTATOS
        t0 = time.perf_counter()
        _faixas_apply, maior_faixa_apply = _consumir_ate_concluir(jobs, job_apply["id"], limite=500)
        t_apply = time.perf_counter() - t0
        assert jobs.status(job_apply["id"])["alterados"] == N_CONTATOS
        assert maior_faixa_apply <= 500
        assert ContactOrganizer(db, repo).apply_rename(regra, all_matching=True)["renamed"] == 0

        # ── 10. Export: montado do contato == o que o apply gravou ─
        resolvedor = GeocodingService(db).resolvedor_entre_ruas()
        for cliente in repo.listar_todos()[:20]:
            esperado = formatar_nome_rota(cliente, entre_ruas=resolvedor.do_contato(cliente))
            assert esperado == cliente.nome

        relatorio += [
            "",
            "== Etapa 6 - medicao com o passe do IBGE (10.000 contatos) ==========",
            f"  parse    : {t_parse:7.2f}s",
            f"  upsert   : {t_upsert:7.2f}s",
            f"  FRIO     : {t_frio:7.2f}s  | {provider.chamadas} requisicoes ({N_RUAS} ruas x 1)",
            f"  carga    : {t_carga:7.2f}s  | {N_RUAS} faces + ancoras + nos (offline)",
            f"  passe    : {t_pass:7.2f}s  | {N_RUAS} ruas SEM rede (provider ibge)",
            f"  apply    : {t_apply:7.2f}s  | 10.000 contatos (2º apply: 0)",
            f"  cobertura: {metrica['ruas_com_intersecoes']}/{N_RUAS} ruas com par"
            f" | eixo {metrica['cobertura_eixo_soma'] / metrica['cobertura_eixo_ruas']:.0%}",
            "",
        ]
        with capsys.disabled():
            print("\n".join(relatorio))
