"""Fase 2, etapa 9 — E2E de 10.000 contatos + medição frio/quente.

Roda o pipeline COMPLETO do renomeador sobre um `.vcf` sintético de 10.000
contatos, pelos serviços de aplicação (sem HTTP):

    parse (.vcf) → upsert em blocos → job GEOCODE (bounded-batch)
    → preview → job APPLY (bounded-batch) → formatação do export

**Não toca a rede.** O provedor é o `MockGeocodingProvider` (contável), então o
"frio × quente" é medido em **requisições ao provedor**, não em milissegundos de
internet — a métrica que o ADR-0004 usa para dimensionar o frio (D12: 1
requisição por RUA, não por contato).

O que está travado aqui:
- 10.000 contatos ponta a ponta, sem perder nenhum;
- **frio** = 1 requisição por rua distinta (200 ruas → 200 requisições);
- **quente** = 0 requisições (cache por rua do ADR-0004);
- o job avança em faixas (bounded-batch), nunca num request só;
- o nome de rota sai no formato D5 e o 2º apply é idempotente.

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
from app.domain.delivery.routing import GeocodeResult, MockGeocodingProvider
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

import app.infrastructure.repositories.settings_model  # noqa: F401
import app.infrastructure.repositories.geocode_cache_model  # noqa: F401
import app.infrastructure.repositories.contact_job_model  # noqa: F401

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
