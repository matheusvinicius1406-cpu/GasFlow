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

from app.application.contacts.organizer import (
    ContactOrganizer,
    apply_rename_rule,
    build_rename_rule,
)
from app.domain.client.entity import Client

from app.infrastructure.database.base import Base
import app.infrastructure.repositories.settings_model  # noqa: F401
import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401


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
        return items, len(items)


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


# ═══════════════════════════════════════════════════════════
# 3. Backfill de códigos
# ═══════════════════════════════════════════════════════════


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
            "SELECT action, before_json, after_json FROM auth_audit_log "
            "WHERE resource='contact' AND resource_id=:rid"
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


def _request_db():
    from app.infrastructure.database.init_db import engine
    from sqlalchemy.orm import Session

    return Session(bind=engine)
