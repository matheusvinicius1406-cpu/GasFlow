"""F6 — Organizador de Contatos: regras de renomeação, backfill de códigos,
lista de conflitos e audit (before/after).

Estratégia:
- Regras puras: unitário direto (sem banco).
- Preview/apply/backfill: FakeClientRepo (mesmo padrão de test_contacts_crm).
- Audit em apply: TestClient contra o engine isolado do conftest — mesma
  via de produção (permissões + auth_audit_log).
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.contacts.geocoding import chave_rua
from app.application.contacts.organizer import (
    ContactOrganizer,
    apply_rename_rule,
    build_rename_rule,
)
from app.application.contacts.service import ContactService
from app.domain.client.entity import Client

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel
import app.infrastructure.repositories.settings_model  # noqa: F401
import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401
import app.infrastructure.repositories.geocode_cache_model  # noqa: F401


# ═══════════════════════════════════════════════════════════
# Fakes
# ═══════════════════════════════════════════════════════════


class FakeClientRepo:
    """Repositório em memória com a superfície usada pelo ContactOrganizer."""

    def __init__(self):
        self.clients = []
        self._next = 1

    def proximo_codigo(self) -> str:
        # Espelha o repo real: sequência derivada do maior código existente.
        existing = [int(c.codigo) for c in self.clients if c.codigo and c.codigo.isdigit()]
        next_id = max(existing) + 1 if existing else 1
        return f"{next_id:06d}"

    def criar(self, client: Client) -> Client:
        client.id = self._next
        self._next += 1
        self.clients.append(client)
        return client

    def atualizar(self, client: Client) -> Client:
        return client

    def buscar_por_codigo(self, codigo: str):
        for c in self.clients:
            if c.codigo == codigo:
                return c
        return None

    def listar_todos(self):
        return [c for c in self.clients if c.ativo]

    def buscar(self, query: str = "", page: int = 1, page_size: int = 200):
        items = [c for c in self.clients if c.ativo]
        if query:
            q = query.lower()
            items = [c for c in items if q in (c.nome or "").lower() or q in c.codigo]
        total = len(items)
        start = (page - 1) * page_size
        # Precisa honrar page/page_size: o fake antigo devolvia tudo sempre e
        # mascarava o teto de 200 do preview.
        return items[start : start + page_size], total


def _make_client(codigo, nome, telefone, **kwargs) -> Client:
    return Client(
        codigo=codigo,
        nome=nome,
        telefone=telefone,
        rua=kwargs.get("rua", "A definir"),
        numero=kwargs.get("numero", "S/N"),
        bairro=kwargs.get("bairro", "A definir"),
        **{k: v for k, v in kwargs.items() if k not in ("rua", "numero", "bairro")},
    )


@pytest.fixture()
def organizer_env():
    db = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    Base.metadata.create_all(db.bind)
    repo = FakeClientRepo()
    return db, ContactOrganizer(db, repo), repo


# ═══════════════════════════════════════════════════════════
# 1. Regras puras
# ═══════════════════════════════════════════════════════════


class TestRenameRules:
    def test_trim_collapses_spaces(self):
        rule = build_rename_rule()
        assert apply_rename_rule("  Maria   Silva  ", "", rule) == "Maria Silva"

    def test_strip_prefixes_removes_wa(self):
        rule = build_rename_rule(strip_prefixes=True)
        assert apply_rename_rule("WA-João Souza", "", rule) == "João Souza"

    def test_strip_prefixes_removes_repeated(self):
        rule = build_rename_rule(strip_prefixes=True)
        assert apply_rename_rule("WA-WPP- Ana", "", rule) == "Ana"

    def test_title_case_keeps_minor_words(self):
        rule = build_rename_rule(case="title")
        assert apply_rename_rule("maria da silva", "", rule) == "Maria da Silva"

    def test_upper_and_lower(self):
        assert apply_rename_rule("joão", "", build_rename_rule(case="upper")) == "JOÃO"
        assert apply_rename_rule("JOÃO", "", build_rename_rule(case="lower")) == "joão"

    def test_pattern_bairro_appends_when_defined(self):
        rule = build_rename_rule(pattern_bairro=True)
        assert apply_rename_rule("Maria", "Centro", rule) == "Maria — Centro"

    def test_pattern_bairro_skips_placeholder(self):
        rule = build_rename_rule(pattern_bairro=True)
        assert apply_rename_rule("Maria", "A definir", rule) == "Maria"

    def test_combined_rule(self):
        rule = build_rename_rule(strip_prefixes=True, case="title", pattern_bairro=True)
        assert apply_rename_rule("WA-maria  da silva", "Centro", rule) == "Maria da Silva — Centro"

    def test_invalid_case_rejected(self):
        with pytest.raises(ValueError):
            build_rename_rule(case="camel")


# ═══════════════════════════════════════════════════════════
# 2. Preview / Apply
# ═══════════════════════════════════════════════════════════


class TestPreviewRename:
    def test_preview_lists_changes_without_writing(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "  WA-maria   silva ", "11999990001"))
        rule = build_rename_rule(strip_prefixes=True, case="title")
        result = org.preview_rename(rule)
        assert result["total"] == 1
        assert result["changes"][0]["after"] == "Maria Silva"
        assert repo.clients[0].nome == "  WA-maria   silva "  # intacto

    def test_preview_excludes_conflicts(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-Dup", "11999990001"))
        repo.criar(_make_client("000002", "Dup", "11999990002"))  # nome duplicado
        rule = build_rename_rule(strip_prefixes=True)
        result = org.preview_rename(rule)
        assert result["total"] == 0  # ambos em conflito → nada no preview


class TestApplyRename:
    def test_apply_renames_only_requested_codes(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-a", "11999990001"))
        repo.criar(_make_client("000002", "WA-b", "11999990002"))
        rule = build_rename_rule(strip_prefixes=True)
        result = org.apply_rename(rule, codes=["000001"])
        assert result["renamed"] == 1
        assert repo.clients[0].nome == "a"
        assert repo.clients[1].nome == "WA-b"  # fora do lote

    def test_apply_never_touches_conflicts(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-Dup", "11999990001"))
        repo.criar(_make_client("000002", "Dup", "11999990002"))
        rule = build_rename_rule(strip_prefixes=True)
        result = org.apply_rename(rule, codes=["000001", "000002"])
        assert result["conflicts_skipped"] == 2
        assert result["renamed"] == 0
        assert repo.clients[0].nome == "WA-Dup"

    def test_apply_missing_code_reported(self, organizer_env):
        db, org, repo = organizer_env
        result = org.apply_rename(build_rename_rule(), codes=["999999"])
        assert result["skipped_missing"] == 1

    def test_apply_idempotent_when_already_renamed(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "Maria", "11999990001"))
        result = org.apply_rename(build_rename_rule(case="title"), codes=["000001"])
        assert result["renamed"] == 0
        assert result["results"][0]["status"] == "unchanged"

    def test_apply_requires_an_explicit_selection(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-a", "11999990001"))
        with pytest.raises(ValueError):
            org.apply_rename(build_rename_rule(strip_prefixes=True))

    def test_apply_skips_stale_names(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-a", "11999990001"))
        # `expected` com o nome de outro momento = o contato mudou depois do preview.
        result = org.apply_rename(
            build_rename_rule(strip_prefixes=True),
            codes=["000001"],
            expected={"000001": "nome que o operador viu"},
        )
        assert result["skipped_stale"] == 1
        assert result["renamed"] == 0
        assert repo.clients[0].nome == "WA-a"

    def test_apply_expected_matching_still_renames(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-a", "11999990001"))
        result = org.apply_rename(build_rename_rule(strip_prefixes=True), codes=["000001"], expected={"000001": "WA-a"})
        assert result["renamed"] == 1


# ═══════════════════════════════════════════════════════════
# 2b. Preview paginado + apply por filtro (Fase 2 §6.4)
# ═══════════════════════════════════════════════════════════


def _seed(repo, total: int, prefix: str = "WA-cliente") -> None:
    for i in range(1, total + 1):
        repo.criar(_make_client(f"{i:06d}", f"{prefix} {i}", f"1199999000{i}"))


class TestPreviewPagination:
    def test_preview_paginates_without_the_200_cap(self, organizer_env):
        db, org, repo = organizer_env
        _seed(repo, 5)
        rule = build_rename_rule(strip_prefixes=True, case="title")

        first = org.preview_rename(rule, page=1, page_size=2)
        assert first["total"] == 5  # total real, não o tamanho da página
        assert first["total_pages"] == 3
        assert len(first["changes"]) == 2

        last = org.preview_rename(rule, page=3, page_size=2)
        assert len(last["changes"]) == 1

    def test_preview_page_size_is_capped(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-a", "11999990001"))
        result = org.preview_rename(build_rename_rule(strip_prefixes=True), page_size=99999)
        assert result["page_size"] == 500

    def test_preview_filters_by_status(self, organizer_env):
        db, org, repo = organizer_env
        pending = _make_client("000001", "WA-pendente", "11999990001")
        pending.geocode_status = "PENDENTE"
        repo.criar(pending)
        resolved = _make_client("000002", "WA-ok", "11999990002")
        resolved.geocode_status = "OK"
        repo.criar(resolved)

        result = org.preview_rename(build_rename_rule(strip_prefixes=True), filtro={"status": "PENDENTE"})
        assert result["total"] == 1
        assert result["changes"][0]["codigo"] == "000001"

    def test_preview_filters_by_bairro(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-centro", "11999990001", bairro="Centro"))
        repo.criar(_make_client("000002", "WA-norte", "11999990002", bairro="Norte"))
        result = org.preview_rename(build_rename_rule(strip_prefixes=True), filtro={"bairro": "centro"})
        assert result["total"] == 1
        assert result["changes"][0]["codigo"] == "000001"


class TestApplyByFilter:
    def test_apply_all_matching_goes_beyond_the_old_cap(self, organizer_env):
        db, org, repo = organizer_env
        _seed(repo, 5)
        result = org.apply_rename(build_rename_rule(strip_prefixes=True, case="title"), all_matching=True)
        assert result["renamed"] == 5
        assert all(not c.nome.startswith("WA-") for c in repo.clients)

    def test_apply_by_filter_does_not_leak_outside_the_filter(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "WA-centro", "11999990001", bairro="Centro"))
        repo.criar(_make_client("000002", "WA-norte", "11999990002", bairro="Norte"))
        result = org.apply_rename(build_rename_rule(strip_prefixes=True), filtro={"bairro": "Centro"})
        assert result["renamed"] == 1
        assert repo.clients[0].nome == "centro"
        assert repo.clients[1].nome == "WA-norte"  # fora do filtro, intacto


# ═══════════════════════════════════════════════════════════
# 2c. Modo endereço — formatter de rota (Fase 2 §9 etapa 7)
# ═══════════════════════════════════════════════════════════


def _endereco(repo, codigo="000001", nome="Maria", telefone="11999990001", **kw):
    return repo.criar(
        _make_client(
            codigo,
            nome,
            telefone,
            rua=kw.get("rua", "Travessa São Roque"),
            numero=kw.get("numero", "145"),
            bairro=kw.get("bairro", "Centro"),
            **{k: v for k, v in kw.items() if k not in ("rua", "numero", "bairro")},
        )
    )


class TestRenamePatternEndereco:
    """`pattern_endereco` reusa o preview/apply existentes com o nome de rota (D5)."""

    def test_preview_monta_o_nome_de_rota(self, organizer_env):
        db, org, repo = organizer_env
        _endereco(repo, has_name=True, entre_ruas="Rua A e Rua B", cep="66811-120")

        result = org.preview_rename(build_rename_rule(pattern_endereco=True))

        assert result["total"] == 1
        assert result["changes"][0]["after"] == (
            "1= Travessa São Roque Nº 145 entre Rua A e Rua B - CEP 66811-120 (Maria)"
        )

    def test_apply_grava_e_a_segunda_passada_e_unchanged(self, organizer_env):
        db, org, repo = organizer_env
        c = _endereco(repo, has_name=True, entre_ruas="Rua A e Rua B", cep="66811-120")
        rule = build_rename_rule(pattern_endereco=True)

        first = org.apply_rename(rule, codes=["000001"])
        assert first["renamed"] == 1
        assert c.nome == ("1= Travessa São Roque Nº 145 entre Rua A e Rua B - CEP 66811-120 (Maria)")

        second = org.apply_rename(rule, codes=["000001"])
        assert second["renamed"] == 0
        assert second["results"][0]["status"] == "unchanged"
        assert c.nome == first["results"][0]["after"]

    def test_placeholder_nao_vira_sufixo_nem_promove_has_name(self, organizer_env):
        db, org, repo = organizer_env
        c = _endereco(repo, nome="Contato 11999990001", has_name=False)

        org.apply_rename(build_rename_rule(pattern_endereco=True), codes=["000001"])

        assert c.nome == "1= Travessa São Roque Nº 145"
        assert c.has_name is False  # o padrão de endereço não promove o nome

    def test_apply_por_filtro_nao_vaza_para_fora(self, organizer_env):
        db, org, repo = organizer_env
        centro = _endereco(repo, "000001", "WA-centro", "11999990001", bairro="Centro")
        norte = _endereco(repo, "000002", "WA-norte", "11999990002", bairro="Norte")

        result = org.apply_rename(build_rename_rule(pattern_endereco=True), filtro={"bairro": "Centro"})

        assert result["renamed"] == 1
        assert centro.nome.startswith("1= ")
        assert norte.nome == "WA-norte"


# ═══════════════════════════════════════════════════════════
# 3. Backfill de códigos
# ═══════════════════════════════════════════════════════════


class TestEntreRuasDerivadoDoCache:
    """O par "entre A e B" derivado do cache (D12) chega ao nome.

    Fecha o elo que faltava: o passe Overpass (etapa 6) preenchia
    `geocode_cache.intersecoes` e nada as levava ao nome — `escolher_entre_ruas`
    só tinha chamador em teste. O par entra nos três lugares que formatam
    contato: preview, apply e export.
    """

    PAR = "entre Rua A e Rua B"

    @staticmethod
    def _cache(db, rua="Travessa São Roque", bairro="Centro", intersecoes=None):
        db.add(
            GeocodeCacheModel(
                chave=chave_rua(rua, bairro, "Belém", "PA"),
                lat=-1.3,
                lng=-48.47,
                rua=rua,
                bairro=bairro,
                cidade="Belém",
                uf="PA",
                intersecoes=(
                    intersecoes
                    if intersecoes is not None
                    else [{"nome": "Rua A", "numero": 100}, {"nome": "Rua B", "numero": 200}]
                ),
            )
        )
        db.commit()

    @staticmethod
    def _defaults(db):
        """Cidade/UF default (D11) — sem eles a chave do cache não fecha."""
        from app.application.settings.settings_service import SettingsService

        SettingsService(db).seed_defaults()

    def test_preview_traz_o_par_derivado(self, organizer_env):
        db, org, repo = organizer_env
        self._defaults(db)
        self._cache(db)
        _endereco(repo, has_name=True, cep="66811-120")

        result = org.preview_rename(build_rename_rule(pattern_endereco=True))

        assert result["total"] == 1
        assert result["changes"][0]["after"] == (
            "1= Travessa São Roque Nº 145 entre Rua A e Rua B - CEP 66811-120 (Maria)"
        )

    def test_apply_grava_o_par_e_a_segunda_passada_e_unchanged(self, organizer_env):
        db, org, repo = organizer_env
        self._defaults(db)
        self._cache(db)
        c = _endereco(repo, has_name=True, cep="66811-120")
        rule = build_rename_rule(pattern_endereco=True)

        first = org.apply_rename(rule, codes=["000001"])
        assert first["renamed"] == 1
        assert c.nome == "1= Travessa São Roque Nº 145 entre Rua A e Rua B - CEP 66811-120 (Maria)"

        second = org.apply_rename(rule, codes=["000001"])
        assert second["renamed"] == 0
        assert second["results"][0]["status"] == "unchanged"

    def test_par_derivado_vence_a_coluna_do_vcf(self, organizer_env):
        """.vcf traz um par antigo; o cache calcula o par do número (D12)."""
        db, org, repo = organizer_env
        self._defaults(db)
        self._cache(db)
        _endereco(repo, has_name=True, entre_ruas="Rua Z e Rua W")

        after = org.preview_rename(build_rename_rule(pattern_endereco=True))["changes"][0]["after"]

        assert self.PAR in after
        assert "Rua Z" not in after

    def test_sem_cache_a_coluna_do_vcf_continua_valendo(self, organizer_env):
        """Regressão: quem não tem cache não perde o par que veio no arquivo."""
        db, org, repo = organizer_env
        self._defaults(db)
        _endereco(repo, has_name=True, entre_ruas="Rua Z e Rua W")

        after = org.preview_rename(build_rename_rule(pattern_endereco=True))["changes"][0]["after"]

        assert "entre Rua Z e Rua W" in after

    def test_numero_fora_da_faixa_do_cache_cai_na_coluna(self, organizer_env):
        """Sem par que cerque o número, nada é inventado (D2)."""
        db, org, repo = organizer_env
        self._defaults(db)
        self._cache(db)
        _endereco(repo, has_name=True, numero="999", entre_ruas="Rua Z e Rua W")

        after = org.preview_rename(build_rename_rule(pattern_endereco=True))["changes"][0]["after"]

        assert "entre Rua Z e Rua W" in after

    def test_all_matching_pega_contato_que_so_muda_pelo_par(self, organizer_env):
        """O par derivado conta na SELEÇÃO, não só na formatação.

        Sem derivar em `_select_codes`, este contato (nome já formatado, sem o
        "entre") seria pulado como `unchanged` e o lote não o pegaria.
        """
        db, org, repo = organizer_env
        self._defaults(db)
        self._cache(db)
        c = _endereco(repo, has_name=True, cep="66811-120")
        c.nome = "1= Travessa São Roque Nº 145 - CEP 66811-120 (Maria)"

        result = org.apply_rename(build_rename_rule(pattern_endereco=True), all_matching=True)

        assert result["renamed"] == 1
        assert self.PAR in c.nome

    def test_regra_sem_padrao_de_endereco_nem_le_o_cache(self, organizer_env):
        db, org, repo = organizer_env
        self._cache(db)
        _endereco(repo, nome="WA-maria")

        org.preview_rename(build_rename_rule())

        assert org._entre_ruas is None


class TestBackfillCodes:
    @staticmethod
    def _no_code(repo, nome, telefone):
        """Cria contato direto no fake, sem passar pela validação da entidade
        (código vazio é a condição de backfill — no banco real não há CHECK)."""
        c = _make_client("000099", nome, telefone)
        c.codigo = ""
        repo.clients.append(c)
        return c

    def test_backfill_assigns_sequential_codes(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000005", "A", "11999990001"))
        no_code = self._no_code(repo, "B", "11999990002")
        repo.criar(_make_client("000010", "C", "11999990003"))
        no_code2 = self._no_code(repo, "D", "11999990004")

        result = org.backfill_codes()
        assert result["fixed"] == 2
        # Continua a sequência global a partir do maior código existente.
        assert no_code.codigo == "000011"
        assert no_code2.codigo == "000012"

    def test_backfill_keeps_existing_codes(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "A", "11999990001"))
        org.backfill_codes()
        assert repo.clients[0].codigo == "000001"

    def test_backfill_idempotent(self, organizer_env):
        db, org, repo = organizer_env
        self._no_code(repo, "A", "11999990001")
        assert org.backfill_codes()["fixed"] == 1
        assert org.backfill_codes()["fixed"] == 0


# ═══════════════════════════════════════════════════════════
# 4. Lista "Revisar" (conflitos)
# ═══════════════════════════════════════════════════════════


class TestConflicts:
    def test_duplicate_names_flagged(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "Maria Silva", "11999990001"))
        repo.criar(_make_client("000002", "maria silva ", "11999990002"))
        repo.criar(_make_client("000003", "João", "11999990003"))
        result = org.list_conflicts()
        assert result["total"] == 2
        issues = {i["codigo"]: i["issues"] for i in result["items"]}
        assert issues["000001"] == ["duplicate_name"]
        assert issues["000002"] == ["duplicate_name"]
        assert issues["000001"].count("duplicate_name") == 1

    def test_bad_phone_flagged(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "Curto", "999"))
        result = org.list_conflicts()
        assert result["total"] == 1
        assert result["items"][0]["issues"] == ["bad_phone"]

    def test_valid_phone_not_flagged(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "Ok", "11999990001"))
        assert org.list_conflicts()["total"] == 0

    def test_duplicate_and_bad_phone_combined(self, organizer_env):
        db, org, repo = organizer_env
        repo.criar(_make_client("000001", "Duo", "11999990001"))
        repo.criar(_make_client("000002", "Duo", "11999990001"))  # mesmo tel (não é BR-issue)
        result = org.list_conflicts()
        assert result["total"] == 2
        assert all(i["issues"] == ["duplicate_name"] for i in result["items"])


# ═══════════════════════════════════════════════════════════
# 5. API HTTP + audit (via produção: TestClient + conftest engine)
# ═══════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _audit_rows(db, resource_id):
    from sqlalchemy import text

    return db.execute(
        text(
            "SELECT action, before_json, after_json FROM auth_audit_log WHERE resource='contact' AND resource_id=:rid"
        ),
        {"rid": resource_id},
    ).fetchall()


class TestOrganizerAPI:
    def test_rename_preview_endpoint(self, client, admin_headers):
        res = client.post(
            "/whatsapp/contacts/organizer/rename-preview",
            json={"trim": True, "strip_prefixes": True, "case": "title"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        assert "changes" in res.json() and "total" in res.json()

    def test_rename_preview_invalid_case_422(self, client, admin_headers):
        res = client.post(
            "/whatsapp/contacts/organizer/rename-preview",
            json={"case": "camel"},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_geocode_origem_endpoint(self, client, admin_headers):
        """A triagem da UI lê a origem do geocode por aqui (etapa 9)."""
        res = client.get("/whatsapp/contacts/organizer/geocode-origem", headers=admin_headers)

        assert res.status_code == 200, res.text
        body = res.json()
        assert set(body["por_origem"]) == {"osm", "cep"}
        assert set(body["por_status"]) == {"OK", "NAO_ENCONTRADO", "PENDENTE", "SEM_ENDERECO"}
        assert isinstance(body["ruas_cep"], list)

    def test_geocode_origem_limite_e_clampado(self, client, admin_headers):
        res = client.get(
            "/whatsapp/contacts/organizer/geocode-origem",
            params={"limite": 1},
            headers=admin_headers,
        )

        assert res.status_code == 200, res.text
        assert len(res.json()["ruas_cep"]) <= 1

    def test_rename_apply_writes_audit_before_after(self, client, admin_headers):
        db = _request_db()
        try:
            # Telefone único e válido (padrão BR, só dígitos) para não cair
            # na lista "Revisar" e ser excluído do rename em lote.
            codigo = f"{int(uuid.uuid4().hex[:4], 16) % 800000 + 100000:06d}"
            telefone = f"1199{uuid.uuid4().int % 10_000_000:07d}"[:13]
            from app.infrastructure.repositories.client_model import ClientModel

            db.add(
                ClientModel(
                    tenant_id="default",
                    codigo=codigo,
                    nome="WA-teste sujo",
                    telefone=telefone,
                    rua="A definir",
                    numero="S/N",
                    bairro="Centro",
                )
            )
            db.commit()

            res = client.post(
                "/whatsapp/contacts/organizer/rename-apply",
                json={"rule": {"strip_prefixes": True, "case": "title"}, "codes": [codigo]},
                headers=admin_headers,
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["renamed"] == 1

            rows = _audit_rows(db, codigo)
            assert len(rows) == 1
            action, before, after = rows[0]
            # SELECT cru: coluna JSON volta como string no SQLite.
            if isinstance(before, str):
                before = json.loads(before)
                after = json.loads(after)
            assert action == "contact.rename"
            assert before["nome"] == "WA-teste sujo"
            assert after["nome"] == "Teste Sujo"
        finally:
            db.close()

    def test_rename_apply_requires_selection_422(self, client, admin_headers):
        res = client.post(
            "/whatsapp/contacts/organizer/rename-apply",
            json={"rule": {"trim": True}},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_rename_preview_returns_pagination_fields(self, client, admin_headers):
        res = client.post(
            "/whatsapp/contacts/organizer/rename-preview",
            json={"trim": True},
            params={"page": 1, "page_size": 10},
            headers=admin_headers,
        )
        assert res.status_code == 200
        body = res.json()
        assert {"changes", "total", "page", "page_size", "total_pages"} <= set(body)
        assert body["page_size"] == 10

    def test_rename_preview_aceita_pattern_endereco(self, client, admin_headers):
        res = client.post(
            "/whatsapp/contacts/organizer/rename-preview",
            json={"pattern_endereco": True},
            headers=admin_headers,
        )
        assert res.status_code == 200
        assert "changes" in res.json()

    def test_backfill_endpoint(self, client, admin_headers):
        res = client.post("/whatsapp/contacts/organizer/backfill-codes", headers=admin_headers)
        assert res.status_code == 200
        assert "fixed" in res.json()

    def test_conflicts_endpoint(self, client, admin_headers):
        res = client.get("/whatsapp/contacts/organizer/conflicts", headers=admin_headers)
        assert res.status_code == 200
        assert "total" in res.json() and "items" in res.json()

    def test_endpoints_require_permission(self, client):
        res = client.post("/whatsapp/contacts/organizer/backfill-codes")
        assert res.status_code in (401, 403)


class TestImportVcfAPI:
    """Exemplo literal do cliente ponta a ponta (upload → parse → upsert)."""

    def test_import_vcf_persists_the_literal_example_structured(self, client, admin_headers):
        telefone = f"1197{uuid.uuid4().int % 10_000_000:07d}"[:11]
        raw = f"BEGIN:VCARD\nVERSION:3.0\nFN:1443= berredos 145\nTEL;TYPE=CELL:{telefone}\nEND:VCARD\n"
        res = client.post(
            "/whatsapp/contacts/import-vcf",
            files={"file": ("contatos.vcf", raw.encode("utf-8"), "text/vcard")},
            headers=admin_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["imported"] == 1
        assert body["telefones_ignorados"] == 0

        from app.infrastructure.repositories.client_model import ClientModel

        db = _request_db()
        try:
            row = db.query(ClientModel).filter(ClientModel.telefone == telefone).first()
            assert row is not None
            # O endereço veio estruturado do nome legado e o bruto foi preservado.
            assert row.rua == "berredos"
            assert row.numero == "145"
            assert row.nome_importado == "1443= berredos 145"
            assert row.nome == f"Contato {telefone}"  # não é pessoa → placeholder
        finally:
            db.close()


class TestExportVcfFormatado:
    """`export-vcf?formatar_rota=true` fecha a lacuna G7: export no nome de rota
    sem precisar aplicar nada no CRM."""

    def test_export_formatar_rota_usa_o_nome_de_rota(self, client, admin_headers):
        from app.infrastructure.repositories.client_model import ClientModel

        codigo = f"{int(uuid.uuid4().hex[:4], 16) % 800000 + 100000:06d}"
        telefone = f"1198{uuid.uuid4().int % 10_000_000:07d}"[:13]
        db = _request_db()
        try:
            db.add(
                ClientModel(
                    tenant_id="default",
                    codigo=codigo,
                    nome="Maria",
                    telefone=telefone,
                    rua="Travessa São Roque",
                    numero="145",
                    bairro="Centro",
                    has_name=True,
                    cep="66811-120",
                    entre_ruas="Rua A e Rua B",
                )
            )
            db.commit()
        finally:
            db.close()

        res = client.get(
            "/whatsapp/contacts/export-vcf",
            params={"formatar_rota": True},
            headers=admin_headers,
        )
        assert res.status_code == 200, res.text
        assert (f"{int(codigo)}= Travessa São Roque Nº 145 entre Rua A e Rua B - CEP 66811-120 (Maria)") in res.text

    def test_export_deriva_o_par_do_cache_como_o_apply(self, client, admin_headers):
        """O export é a prévia do apply: o par derivado (D12) tem de sair aqui."""
        from app.application.settings.settings_service import SettingsService
        from app.infrastructure.repositories.client_model import ClientModel

        rua = f"Travessa Teste {uuid.uuid4().hex[:6]}"
        codigo = f"{int(uuid.uuid4().hex[:4], 16) % 800000 + 100000:06d}"
        telefone = f"1198{uuid.uuid4().int % 10_000_000:07d}"[:13]
        db = _request_db()
        try:
            SettingsService(db).seed_defaults()
            db.add(
                ClientModel(
                    tenant_id="default",
                    codigo=codigo,
                    nome="Maria",
                    telefone=telefone,
                    rua=rua,
                    numero="145",
                    bairro="Centro",
                    has_name=True,
                    cep="66811-120",
                    # Par antigo do .vcf: o derivado do cache vence (D12).
                    entre_ruas="Rua Z e Rua W",
                )
            )
            db.add(
                GeocodeCacheModel(
                    chave=chave_rua(rua, "Centro", "Belém", "PA"),
                    lat=-1.3,
                    lng=-48.47,
                    rua=rua,
                    bairro="Centro",
                    cidade="Belém",
                    uf="PA",
                    intersecoes=[{"nome": "Rua A", "numero": 100}, {"nome": "Rua B", "numero": 200}],
                )
            )
            db.commit()
        finally:
            db.close()

        res = client.get(
            "/whatsapp/contacts/export-vcf",
            params={"formatar_rota": True},
            headers=admin_headers,
        )

        assert res.status_code == 200, res.text
        assert f"{int(codigo)}= {rua} Nº 145 entre Rua A e Rua B - CEP 66811-120 (Maria)" in res.text
        assert "Rua Z e Rua W" not in res.text


class TestImportacaoEmLoteNoRepositorioReal:
    """§18 etapa 4 contra SQLAlchemy de verdade: 1 transação por bloco.

    O FakeClientRepo prova o agrupamento; aqui provamos o que o fake não vê —
    o contador de código atravessa os blocos (o repo real lê o maior código
    já gravado) e nada se perde entre uma transação e a seguinte.
    """

    @pytest.fixture()
    def repo(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import app.infrastructure.repositories.client_model  # noqa: F401
        from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        return SQLAlchemyClientRepository(sessionmaker(bind=engine)(), "default")

    def test_lote_de_1200_grava_todos_com_codigos_em_ordem(self, repo):
        svc = ContactService(repo)

        results = svc.sync_batch([{"telefone": f"1190000{i:04d}"} for i in range(1200)])

        assert len(results) == 1200
        assert all(r["action"] == "created" for r in results)
        # Códigos contíguos = o contador do bloco não reiniciou ao virar a
        # transação (500 → 500 → 200).
        assert [r["codigo"] for r in results] == [f"{i:06d}" for i in range(1, 1201)]
        _, total = repo.buscar(query="", page=1, page_size=1)
        assert total == 1200

    def test_reimportar_o_mesmo_lote_nao_duplica(self, repo):
        svc = ContactService(repo)
        contacts = [{"telefone": f"1190000{i:04d}", "nome": f"Cliente {i}"} for i in range(30)]

        svc.sync_batch(contacts)
        results = svc.sync_batch(contacts)

        assert all(r["action"] == "unchanged" for r in results)
        _, total = repo.buscar(query="", page=1, page_size=1)
        assert total == 30

    def test_telefone_repetido_no_bloco_nao_estoura_unique(self, repo):
        svc = ContactService(repo)

        results = svc.sync_batch(
            [
                {"telefone": "11999999999", "nome": "Maria"},
                {"telefone": "(11) 99999-9999", "nome": "Maria Silva"},
            ]
        )

        assert results[0]["action"] == "created"
        assert results[1]["action"] == "unchanged"
        _, total = repo.buscar(query="", page=1, page_size=1)
        assert total == 1


def _request_db():
    from app.infrastructure.database.init_db import engine
    from sqlalchemy.orm import Session

    return Session(bind=engine)


# ═══════════════════════════════════════════════════════════
# Origem do geocode (etapa 9) — OSM × fallback de CEP
# ═══════════════════════════════════════════════════════════


class TestGeocodeOrigem:
    """A triagem precisa dizer se o endereço veio do OSM ou do fallback de CEP.

    Aqui o banco é REAL (o resumo é query em `clients` + `geocode_cache`); o
    `FakeClientRepo` não serviria porque não persiste.
    """

    @pytest.fixture()
    def env(self):
        from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        return db, ContactOrganizer(db, SQLAlchemyClientRepository(db, "default"))

    def _cache(self, db, rua, provider, cep=None, lat=-1.3, lng=-48.47):
        from app.application.contacts.geocoding import chave_rua

        db.add(
            GeocodeCacheModel(
                chave=chave_rua(rua, "Centro", "Belém", "PA"),
                rua=rua,
                bairro="Centro",
                cidade="Belém",
                uf="PA",
                cep=cep,
                provider=provider,
                lat=lat,
                lng=lng,
            )
        )
        db.commit()

    def test_separa_osm_do_fallback_de_cep(self, env):
        db, org = env
        self._cache(db, "Travessa São Roque", "nominatim")
        self._cache(db, "Passagem Ivan Leão", "brasilapi", cep="66811-120")
        self._cache(db, "Alameda Sem Nome", "pontofato", cep="66810-000")

        resumo = org.geocode_origem()

        assert resumo["por_origem"] == {"osm": 1, "cep": 2}
        assert resumo["total_ruas_cache"] == 3
        assert resumo["total_ruas_cep"] == 2
        # A lista é só do fallback — é o que o operador confere antes de aplicar.
        assert {r["provider"] for r in resumo["ruas_cep"]} == {"brasilapi", "pontofato"}
        assert {r["rua"] for r in resumo["ruas_cep"]} == {"Passagem Ivan Leão", "Alameda Sem Nome"}

    def test_negativo_cacheado_continua_sendo_osm(self, env):
        """A classificação é pelo provedor, não por ter achado coordenada."""
        db, org = env
        self._cache(db, "Rua Inexistente", "nominatim", lat=None, lng=None)

        resumo = org.geocode_origem()

        assert resumo["por_origem"] == {"osm": 1, "cep": 0}

    def test_provider_desconhecido_conta_como_osm(self, env):
        db, org = env
        self._cache(db, "Rua Y", "photon")
        self._cache(db, "Rua Z", None)

        resumo = org.geocode_origem()

        assert resumo["por_origem"] == {"osm": 2, "cep": 0}
        assert resumo["por_provider"] == {"photon": 1, "desconhecido": 1}

    def test_por_status_conta_buckets_e_sem_endereco(self, env):
        _, org = env
        repo = org.repo
        for i, status in enumerate(["OK", "OK", "NAO_ENCONTRADO", None, "PENDENTE"]):
            _endereco(repo, codigo=f"{i + 1:06d}", telefone=f"119000{i:04d}", geocode_status=status)
        _endereco(repo, codigo="000099", telefone="11999999999", rua="A definir")

        resumo = org.geocode_origem()

        assert resumo["por_status"] == {
            "OK": 2,
            "NAO_ENCONTRADO": 1,
            "PENDENTE": 2,  # None e "PENDENTE" caem no mesmo bucket (D3)
            "SEM_ENDERECO": 1,
        }

    def test_limite_corta_a_lista_mas_nao_o_total(self, env):
        db, org = env
        for i in range(5):
            self._cache(db, f"Rua CEP {i}", "brasilapi")

        resumo = org.geocode_origem(limite=2)

        assert len(resumo["ruas_cep"]) == 2
        assert resumo["total_ruas_cep"] == 5
        assert resumo["por_origem"] == {"osm": 0, "cep": 5}

    def test_sem_cache_fica_tudo_zerado(self, env):
        _, org = env

        resumo = org.geocode_origem()

        assert resumo["por_origem"] == {"osm": 0, "cep": 0}
        assert resumo["total_ruas_cache"] == 0
        assert resumo["total_ruas_cep"] == 0
        assert resumo["ruas_cep"] == []
