"""
Contacts CRM — testes do ContactService (upsert/enriquecimento) e da
ReactivationService (elegibilidade, template, idempotência diária).
"""

import json
from datetime import datetime, timedelta

import pytest

from app.application.contacts.service import ContactService, normalize_phone
from app.domain.client.entity import Client


# ═══════════════════════════════════════════════════════════
# Fakes
# ═══════════════════════════════════════════════════════════


class FakeClientRepo:
    """Repositório em memória com a superfície usada pelo ContactService."""

    def __init__(self):
        self.clients = []
        self._next = 1
        # Nº de transações: o lote tem de agrupar por bloco (etapa 4), não
        # commitar 1x por contato.
        self.commits = 0

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

    def buscar_por_telefones(self, telefones):
        found = {}
        for telefone in telefones:
            c = self.buscar_por_telefone(telefone)
            if c:
                found[normalize_phone(telefone)] = c
        return found

    def salvar_lote(self, criar, atualizar) -> None:
        """Uma transação só para o bloco inteiro."""
        self.commits += 1
        for client in criar:
            self.criar(client)
        for client in atualizar:
            self.atualizar(client)

    def buscar_por_telefone(self, telefone: str):
        normalized = normalize_phone(telefone)
        for c in self.clients:
            if c.telefone == normalized:
                return c
        return None

    def buscar_por_codigo(self, codigo: str):
        for c in self.clients:
            if c.codigo == codigo:
                return c
        return None

    def listar_todos(self):
        return [c for c in self.clients if c.ativo]


class FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content
        self.error = None


class FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = 0

    def generate(self, messages, temperature=0.1):
        self.calls += 1
        return FakeLLMResponse(self.content)


def _make_client(codigo: str, nome: str, telefone: str, **kwargs) -> Client:
    return Client(
        codigo=codigo,
        nome=nome,
        telefone=telefone,
        rua=kwargs.get("rua", "A definir"),
        numero=kwargs.get("numero", "S/N"),
        bairro=kwargs.get("bairro", "A definir"),
        **{k: v for k, v in kwargs.items() if k not in ("rua", "numero", "bairro")},
    )


# ═══════════════════════════════════════════════════════════
# Upsert
# ═══════════════════════════════════════════════════════════


class TestUpsertContact:
    def test_create_minimal_with_placeholder(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        client, action = svc.upsert_contact({"telefone": "(11) 99999-9999"})

        assert action == "created"
        assert client.telefone == "11999999999"
        assert client.nome == "Contato 11999999999"
        assert client.has_name is False
        assert client.rua == "A definir"
        assert len(client.codigo) == 6

    def test_sync_fills_placeholder_name_but_never_overwrites(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        client, _ = svc.upsert_contact({"telefone": "1199999999"})
        assert client.has_name is False

        updated, action = svc.upsert_contact({"telefone": "1199999999", "nome": "Maria Silva"})
        assert action == "updated"
        assert updated.nome == "Maria Silva"
        assert updated.has_name is True
        assert updated.codigo == client.codigo  # código permanente

        # Sync repetido com outro nome NÃO sobrescreve nome real do CRM.
        again, action2 = svc.upsert_contact({"telefone": "1199999999", "nome": "Outro Nome"})
        assert action2 == "unchanged"
        assert again.nome == "Maria Silva"

    def test_protected_fields_ignored(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        client, _ = svc.upsert_contact({"telefone": "1199999999", "nome": "Maria", "codigo": "999999", "id": 123})
        assert client.codigo != "999999"
        assert client.id != 123

    def test_create_persists_geocoding_fields(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        client, action = svc.upsert_contact(
            {"telefone": "1199999999", "nome": "Maria", "cep": "00000-000", "entre_ruas": "Rua A e Rua B"}
        )
        assert action == "created"
        assert client.cep == "00000-000"
        assert client.entre_ruas == "Rua A e Rua B"

    def test_reimport_fills_missing_cep_and_never_overwrites(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        client, _ = svc.upsert_contact({"telefone": "1199999999", "nome": "Maria"})
        assert client.cep is None

        updated, action = svc.upsert_contact({"telefone": "1199999999", "cep": "00000-000"})
        assert action == "updated"
        assert updated.cep == "00000-000"

        # CEP já preenchido não é sobrescrito por reimportação.
        again, _ = svc.upsert_contact({"telefone": "1199999999", "cep": "11111-111"})
        assert again.cep == "00000-000"

    def test_invalid_phone_rejected(self):
        svc = ContactService(FakeClientRepo())
        with pytest.raises(ValueError):
            svc.upsert_contact({"telefone": "123"})

    def test_sync_batch_never_aborts_on_bad_item(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        results = svc.sync_batch(
            [
                {"telefone": "1199999999", "nome": "A"},
                {"telefone": "1"},  # inválido
            ]
        )
        assert len(results) == 2
        assert results[0]["action"] == "created"
        assert results[1]["action"] == "error"


# ═══════════════════════════════════════════════════════════
# Importação em lote (§18 etapa 4)
# ═══════════════════════════════════════════════════════════


def _lote(n: int):
    return [{"telefone": f"1190000{i:04d}"} for i in range(n)]


class _FakeRepoQueFalhaNoLote(FakeClientRepo):
    """salvar_lote sempre estoura — força o fallback linha a linha."""

    def salvar_lote(self, criar, atualizar) -> None:
        self.commits += 1
        raise RuntimeError("lote indisponível")


class TestSyncBatchEmLote:
    def test_agrupa_criacoes_em_transacoes_de_500(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)

        results = svc.sync_batch(_lote(1200))

        assert len(results) == 1200
        assert all(r["action"] == "created" for r in results)
        assert repo.commits == 3  # 500 + 500 + 200
        assert len(repo.clients) == 1200

    def test_chunk_size_configuravel(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)

        results = svc.sync_batch(_lote(5), chunk_size=2)

        assert len(results) == 5
        assert repo.commits == 3  # 2 + 2 + 1

    def test_codigos_sequenciais_atravessando_blocos(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)

        results = svc.sync_batch(_lote(5), chunk_size=2)

        assert [r["codigo"] for r in results] == ["000001", "000002", "000003", "000004", "000005"]

    def test_telefone_repetido_no_mesmo_bloco_cria_uma_vez(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)

        results = svc.sync_batch(
            [
                {"telefone": "11999999999", "nome": "Maria"},
                {"telefone": "(11) 99999-9999", "nome": "Maria Silva"},
            ]
        )

        # O 2º card é o MESMO telefone: enriquece em memória, não duplica insert
        # (seria UNIQUE violation e derrubaria o bloco inteiro).
        assert len(repo.clients) == 1
        assert results[0]["action"] == "created"
        assert results[1]["action"] == "unchanged"  # nome real não é sobrescrito

    def test_item_invalido_no_meio_nao_aborta_o_bloco(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)

        results = svc.sync_batch(
            [
                {"telefone": "1199999999"},
                {"telefone": "1"},  # inválido, no meio
                {"telefone": "1188888888"},
            ]
        )

        assert [r["action"] for r in results] == ["created", "error", "created"]
        assert len(repo.clients) == 2

    def test_bloco_que_falha_cai_para_linha_a_linha_sem_perder_contato(self):
        repo = _FakeRepoQueFalhaNoLote()
        svc = ContactService(repo)

        results = svc.sync_batch(_lote(3), chunk_size=10)

        assert [r["action"] for r in results] == ["created", "created", "created"]
        assert len(repo.clients) == 3

    def test_reimportacao_do_mesmo_lote_e_idempotente(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        contacts = [{"telefone": f"1190000{i:04d}", "nome": f"Cliente {i}"} for i in range(3)]

        svc.sync_batch(contacts, chunk_size=2)
        results = svc.sync_batch(contacts, chunk_size=2)

        assert all(r["action"] == "unchanged" for r in results)
        assert len(repo.clients) == 3


# ═══════════════════════════════════════════════════════════
# Enriquecimento via LLM
# ═══════════════════════════════════════════════════════════


class TestEnrichWithAI:
    def test_enriches_address_from_name(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        client, _ = svc.upsert_contact({"telefone": "1199999999", "nome": "Maria - Rua das Flores, 123, Centro"})
        assert client.rua == "A definir"

        llm = FakeLLM(
            json.dumps(
                {"nome": "Maria", "rua": "Rua das Flores", "numero": "123", "complemento": "", "bairro": "Centro"}
            )
        )
        svc.llm_provider = llm
        result = svc.enrich_with_ai(client.codigo)

        assert result["success"] is True
        assert result["enriched"] is True
        refreshed = repo.buscar_por_codigo(client.codigo)
        assert refreshed.rua == "Rua das Flores"
        assert refreshed.numero == "123"
        assert refreshed.bairro == "Centro"

    def test_skips_when_address_already_set(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        repo.criar(_make_client("000001", "João", "11988887777", rua="Rua Real"))
        llm = FakeLLM("{}")
        svc.llm_provider = llm
        result = svc.enrich_with_ai("000001")
        assert result["success"] is False
        assert llm.calls == 0  # nem chamou o LLM

    def test_llm_garbage_is_safe_noop(self):
        repo = FakeClientRepo()
        svc = ContactService(repo)
        client, _ = svc.upsert_contact({"telefone": "1199999999", "nome": "Sem endereço aqui"})
        svc.llm_provider = FakeLLM("desculpe, não sei")
        result = svc.enrich_with_ai(client.codigo)
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════
# Reativação
# ═══════════════════════════════════════════════════════════


class TestReactivation:
    @pytest.fixture()
    def reactivation_env(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import app.infrastructure.repositories.settings_model  # noqa: F401
        import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401
        from app.application.settings.settings_service import SettingsService
        from app.infrastructure.database.base import Base
        from app.infrastructure.repositories.whatsapp_automation_repository import (
            SQLAlchemyAutomationRepository,
        )

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()

        SettingsService(db).seed_defaults()
        SettingsService(db).update("whatsapp_reactivate_enabled", True, updated_by="test")

        repo = FakeClientRepo()
        old = _make_client("000001", "Antigo", "11900000001")
        old.is_whatsapp = True
        old.marketing_status = "OPTED_IN"
        old.last_interaction_at = datetime.utcnow() - timedelta(days=120)

        recent = _make_client("000002", "Recente", "11900000002")
        recent.is_whatsapp = True
        recent.marketing_status = "OPTED_IN"
        recent.last_interaction_at = datetime.utcnow() - timedelta(days=2)

        opted_out = _make_client("000003", "OptOut", "11900000003")
        opted_out.is_whatsapp = True
        opted_out.marketing_status = "OPTED_OUT"
        opted_out.last_interaction_at = datetime.utcnow() - timedelta(days=200)

        repo.clients = [old, recent, opted_out]

        from app.application.contacts.reactivate import ReactivationService

        svc = ReactivationService(db, repo, automation_repo=SQLAlchemyAutomationRepository(db))
        return svc, db

    def test_preview_lists_only_eligible(self, reactivation_env):
        svc, _ = reactivation_env
        result = svc.preview(days=90)
        assert result["total_eligible"] == 1
        assert result["sample"][0]["codigo"] == "000001"

    def test_run_creates_executions_and_is_idempotent(self, reactivation_env):
        svc, db = reactivation_env
        result = svc.run(days=90)
        assert result["success"] is True
        assert result["created"] == 1

        # Segunda execução no mesmo dia: nada novo (anti-spam).
        again = svc.run(days=90)
        assert again["created"] == 0
        assert again["skipped_recent"] == 1

    def test_run_disabled_by_setting(self, reactivation_env):
        from app.application.settings.settings_service import SettingsService

        svc, db = reactivation_env
        SettingsService(db).update("whatsapp_reactivate_enabled", False, updated_by="test")
        result = svc.run(days=90)
        assert result["success"] is False
