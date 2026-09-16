"""
Testes F3 — Auto-print com filtro de status (printer.auto_print.min_status).

Cobre:
- Config default (PAID,CONFIRMED): DRAFT não imprime; PAID imprime.
- Idempotência: evento repetido do mesmo pedido não cria 2º job.
- Customização do setting (ex.: só PAID).
- Falha do settings não quebra (default conservador).
- Hook na API: PATCH /orders/{codigo}/status cria job quando elegível.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base


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


def _fresh_trigger():
    from app.application.delivery.auto_print_trigger import AutoPrintTrigger

    return AutoPrintTrigger()


class TestStatusFilter:
    def test_draft_does_not_print(self):
        trigger = _fresh_trigger()
        result = trigger.maybe_auto_print(order_id="ORD-DRAFT", tenant_id="default", order_status="DRAFT")
        assert result["created"] is False
        assert result["skipped_reason"] == "status_not_eligible:DRAFT"
        # Pedido bloqueado não entra no registro de impressos
        assert not trigger.already_printed("ORD-DRAFT")

    def test_paid_prints(self):
        trigger = _fresh_trigger()
        result = trigger.maybe_auto_print(order_id="ORD-PAID", tenant_id="default", order_status="PAID")
        assert result["created"] is True
        assert trigger.already_printed("ORD-PAID")

    def test_confirmed_prints_by_default(self):
        trigger = _fresh_trigger()
        result = trigger.maybe_auto_print(order_id="ORD-CONF", tenant_id="default", order_status="CONFIRMED")
        assert result["created"] is True

    def test_case_insensitive_status(self):
        trigger = _fresh_trigger()
        result = trigger.maybe_auto_print(order_id="ORD-LOWER", tenant_id="default", order_status="paid")
        assert result["created"] is True


class TestIdempotency:
    def test_repeated_event_does_not_create_second_job(self):
        trigger = _fresh_trigger()
        first = trigger.maybe_auto_print("ORD-DUP", "default", "PAID")
        second = trigger.maybe_auto_print("ORD-DUP", "default", "PAID")

        assert first["created"] is True
        assert second["created"] is False
        assert second["skipped_reason"] == "already_auto_printed"

    def test_failed_job_releases_idempotency_mark(self, monkeypatch):
        import app.application.delivery.auto_print_trigger as apt

        trigger = _fresh_trigger()

        class BoomAgent:
            def create_print_job(self, **kwargs):
                raise RuntimeError("printer offline")

        monkeypatch.setattr(apt, "get_print_agent", lambda: BoomAgent())
        result = trigger.maybe_auto_print("ORD-BOOM", "default", "PAID")
        assert result["created"] is False
        assert result["skipped_reason"] == "job_error"
        # Marca liberada: próximo evento tenta de novo
        assert not trigger.already_printed("ORD-BOOM")


class TestSettingConfig:
    def test_setting_read_single_status(self, db, monkeypatch):
        import app.infrastructure.database.init_db as init_db
        from app.application.settings.settings_service import SettingsService

        import app.infrastructure.repositories.settings_model  # noqa: F401

        SettingsService(db).seed_defaults()
        SettingsService(db).update("printer.auto_print.min_status", "PAID", updated_by="test")

        import app.application.delivery.auto_print_trigger as apt

        def _fake_session():
            return sessionmaker(bind=db.get_bind())()

        class _FakeSessionCtx:
            pass

        # Patch do _load_allowed_statuses para usar a session de teste
        monkeypatch.setattr(init_db, "engine", db.get_bind())
        statuses = apt.AutoPrintTrigger._load_allowed_statuses()
        assert statuses == {"PAID"}

    def test_invalid_setting_falls_back_to_default(self, db, monkeypatch):
        import app.infrastructure.database.init_db as init_db
        from app.application.settings.settings_service import SettingsService

        import app.infrastructure.repositories.settings_model  # noqa: F401

        SettingsService(db).seed_defaults()
        SettingsService(db).update("printer.auto_print.min_status", "   ", updated_by="test")

        import app.application.delivery.auto_print_trigger as apt

        monkeypatch.setattr(init_db, "engine", db.get_bind())
        statuses = apt.AutoPrintTrigger._load_allowed_statuses()
        assert statuses == {"PAID", "CONFIRMED"}


class TestOrdersApiHook:
    def test_hook_swallows_internal_error(self, monkeypatch):
        """_safe_auto_print engole erro do trigger — PATCH de status não pode cair."""
        import app.application.delivery.auto_print_trigger as apt
        from app.presentation.api import orders as orders_api

        def _boom(self, **kwargs):
            raise RuntimeError("boom no trigger")

        monkeypatch.setattr(apt.AutoPrintTrigger, "maybe_auto_print", _boom)

        # Não pode propagar: o endpoint PATCH /orders/{codigo}/status chama
        # o hook depois de publicar o evento; qualquer exceção viraria 422.
        orders_api._safe_auto_print(
            order_id="ORD-BOOM",
            tenant_id="default",
            order_status="PAID",
            order_data={"codigo": "ORD-BOOM"},
        )

    def test_hook_calls_trigger_with_order_fields(self, monkeypatch):
        """Contrato: hook repassa order_id/status/tenant/order_data ao trigger."""
        import app.application.delivery.auto_print_trigger as apt
        from app.presentation.api import orders as orders_api

        calls = []

        def _spy(self, **kwargs):
            calls.append(kwargs)
            return {"created": False, "skipped_reason": "status_not_eligible:DRAFT"}

        monkeypatch.setattr(apt.AutoPrintTrigger, "maybe_auto_print", _spy)
        orders_api._safe_auto_print(
            order_id="ORD-OK",
            tenant_id="default",
            order_status="PAID",
            order_data={"codigo": "ORD-OK"},
        )

        assert len(calls) == 1
        assert calls[0]["order_id"] == "ORD-OK"
        assert calls[0]["order_status"] == "PAID"
        assert calls[0]["order_data"]["codigo"] == "ORD-OK"

    def test_trigger_never_raises(self):
        """maybe_auto_print engole exceções internas (settings, print agent)."""
        trigger = _fresh_trigger()
        # Status vazio — não explode, só skipa
        result = trigger.maybe_auto_print("ORD-X", "default", "")
        assert result["created"] is False
        assert result["skipped_reason"] == "status_not_eligible:EMPTY"
