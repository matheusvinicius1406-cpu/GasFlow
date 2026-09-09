"""
Address Update Tool + Reativação end-to-end (com bridge stubado).

Cobre os dois fluxos novos:
1. Tool `update_client_address` — atualiza endereço do cliente durante a
   conversa do WhatsApp (registro no gateway tool registry).
2. Reativação: ReactivationService cria executions → ExecutionProcessor envia
   via bridge → idempotência diária.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.domain.client.entity import Client
from app.presentation.api.whatsapp_gateway import _build_tool_registry
from app.domain.ai.tools import ToolType, ToolPermission


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def sample_client(db):
    client = ClientModel(
        codigo="000001",
        nome="Maria Silva",
        telefone="5511999887766",
        rua="Rua Antiga",
        numero="10",
        bairro="Centro",
        ativo=True,
        tenant_id="default",
    )
    db.add(client)
    db.commit()
    return client


# ═══════════════════════════════════════════════════════════
# 1. Tool update_client_address
# ═══════════════════════════════════════════════════════════


class TestUpdateClientAddressTool:
    def _tool(self, db):
        registry = _build_tool_registry(db)
        tool = registry.get("update_client_address")
        assert tool is not None, "tool update_client_address deve estar registrado"
        return tool

    def test_tool_registered_with_confirmation(self, db):
        tool = self._tool(db)
        assert tool.tool_type == ToolType.WRITE
        assert tool.requires_confirmation is True
        assert tool.permission == ToolPermission.OPERATOR

    def _run(self, tool, args):
        return tool.handler(args)

    def test_updates_address_by_phone(self, db, sample_client):
        tool = self._tool(db)
        result = self._run(
            tool,
            {
                "phone": "5511999887766",
                "rua": "Rua Nova",
                "numero": "222",
                "bairro": "Jardim",
                "complemento": "Fundos",
            },
        )
        assert result.success is True
        assert result.data["codigo"] == "000001"
        assert "Rua Nova" in result.data["endereco"]

        db.refresh(sample_client)
        assert sample_client.rua == "Rua Nova"
        assert sample_client.numero == "222"
        assert sample_client.complemento == "Fundos"

    def test_updates_address_by_codigo(self, db, sample_client):
        tool = self._tool(db)
        result = self._run(
            tool,
            {"customer_codigo": "000001", "rua": "Rua X", "numero": "1", "bairro": "B"},
        )
        assert result.success is True
        db.refresh(sample_client)
        assert sample_client.rua == "Rua X"

    def test_missing_client_fails(self, db):
        tool = self._tool(db)
        result = self._run(
            tool,
            {"phone": "11900000000", "rua": "Rua", "numero": "1", "bairro": "B"},
        )
        assert result.success is False

    def test_missing_fields_fail(self, db, sample_client):
        tool = self._tool(db)
        result = self._run(
            tool,
            {"phone": "5511999887766", "rua": "Rua Sem Numero"},
        )
        assert result.success is False
        db.refresh(sample_client)
        assert sample_client.rua == "Rua Antiga"  # intocado


# ═══════════════════════════════════════════════════════════
# 2. Reativação → executor → envio (bridge stubado)
# ═══════════════════════════════════════════════════════════


class FakeClientRepo:
    """Superfície mínima usada por ReactivationService."""

    def __init__(self, clients):
        self.clients = clients

    def listar_todos(self):
        return [c for c in self.clients if c.ativo]

    def buscar_por_telefone(self, telefone):
        for c in self.clients:
            if c.telefone == telefone:
                return c
        return None


def _make_client(codigo, telefone, days_inactive, marketing="OPTED_IN"):
    return Client(
        codigo=codigo,
        nome=f"Cliente {codigo}",
        telefone=telefone,
        rua="Rua A",
        numero="1",
        bairro="Centro",
        is_whatsapp=True,
        marketing_status=marketing,
        last_interaction_at=datetime.utcnow() - timedelta(days=days_inactive),
    )


class TestReactivationEndToEnd:
    @pytest.fixture()
    def setup(self, db):
        import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401
        from app.application.settings.settings_service import SettingsService
        from app.infrastructure.repositories.whatsapp_automation_repository import (
            SQLAlchemyAutomationRepository,
        )

        SettingsService(db).seed_defaults()
        SettingsService(db).update("whatsapp_reactivate_enabled", True, updated_by="test")

        repo = FakeClientRepo([_make_client("000001", "11900000001", 120), _make_client("000002", "11900000002", 5)])
        auto_repo = SQLAlchemyAutomationRepository(db, "default")

        from app.application.contacts.reactivate import ReactivationService

        svc = ReactivationService(db, repo, automation_repo=auto_repo)
        return svc, auto_repo

    @pytest.mark.asyncio
    async def test_reactivation_messages_are_actually_sent(self, setup):
        from app.application.whatsapp_automation.executor import ExecutionProcessor

        svc, auto_repo = setup
        run = svc.run(days=90)
        assert run["created"] == 1  # só o cliente com 120 dias

        sent: list = []

        class StubBridge:
            async def send_message(self, phone, text, account_id="primary", idempotency_key=None):
                sent.append({"phone": phone, "text": text, "account_id": account_id})
                return {"success": True, "message_id": "stub-123"}

        processor = ExecutionProcessor(auto_repo, whatsapp_bridge=StubBridge())
        result = await processor.process_pending_executions(limit=10)

        assert result["sent"] == 1
        assert len(sent) == 1
        assert sent[0]["phone"] == "11900000001"
        # Template renderizado com dados do cliente
        assert "Cliente 000001" in sent[0]["text"]
        assert "Rua A" in sent[0]["text"]

    @pytest.mark.asyncio
    async def test_opted_out_never_receives(self, setup, db):
        import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401
        from app.application.settings.settings_service import SettingsService
        from app.infrastructure.repositories.whatsapp_automation_repository import (
            SQLAlchemyAutomationRepository,
        )
        from app.application.contacts.reactivate import ReactivationService
        from app.application.whatsapp_automation.executor import ExecutionProcessor

        SettingsService(db).update("whatsapp_reactivate_enabled", True, updated_by="test")
        repo = FakeClientRepo([_make_client("000009", "11900000009", 200, marketing="OPTED_OUT")])
        auto_repo = SQLAlchemyAutomationRepository(db, "default")
        svc = ReactivationService(db, repo, automation_repo=auto_repo)

        run = svc.run(days=90)
        assert run["created"] == 0

        processor = ExecutionProcessor(auto_repo, whatsapp_bridge=StubBridge())
        result = await processor.process_pending_executions(limit=10)
        assert result["sent"] == 0


class StubBridge:
    async def send_message(self, phone, text, account_id="primary", idempotency_key=None):
        return {"success": True, "message_id": "stub-123"}
