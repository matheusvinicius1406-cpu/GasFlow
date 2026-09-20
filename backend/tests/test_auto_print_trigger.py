"""
Testes F3/F10.7 — Auto-print com filtro de status (printer.auto_print.min_status).

Cobre:
- Config default (PAID,CONFIRMED): DRAFT não imprime; PAID imprime.
- Idempotência PERSISTIDA: evento repetido não cria 2º job (e sobrevive a
  restart, porque a marca vive no banco).
- Cupom montado com o PEDIDO REAL (itens/total/pagamento) — antes ia vazio.
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


def _create_order(db, codigo: str, status: str = "CONFIRMED") -> None:
    """Pedido real com item — o cupom precisa sair preenchido."""
    from app.infrastructure.repositories.order_item_model import OrderItemModel
    from app.infrastructure.repositories.order_model import OrderModel

    db.add(
        OrderModel(
            tenant_id="default",
            codigo=codigo,
            client_codigo="000001",
            address_snapshot="Rua das Flores, 120 - Jardim América",
            status=status,
            subtotal=120.0,
            delivery_fee=5.0,
            discount=0.0,
            total=125.0,
            payment_method="DINHEIRO",
            payment_status="PAID",
            source="MANUAL",
            notes="Trocar o botijão vazio",
        )
    )
    db.add(
        OrderItemModel(
            tenant_id="default",
            order_codigo=codigo,
            product_codigo="000002",
            product_nome="Botijao de Gas P13 (13kg)",
            quantity=1,
            unit_price=120.0,
            subtotal=120.0,
        )
    )
    db.commit()


class TestStatusFilter:
    def test_draft_does_not_print(self, db):
        trigger = _fresh_trigger()
        result = trigger.maybe_auto_print("000100", "default", "DRAFT", db=db)
        assert result["created"] is False
        assert result["skipped_reason"] == "status_not_eligible:DRAFT"
        assert not trigger.already_printed("000100", "default", db)

    def test_paid_prints(self, db):
        _create_order(db, "000101", status="CONFIRMED")
        trigger = _fresh_trigger()
        result = trigger.maybe_auto_print("000101", "default", "PAID", db=db)
        assert result["created"] is True
        assert trigger.already_printed("000101", "default", db)

    def test_confirmed_prints_by_default(self, db):
        _create_order(db, "000102")
        result = _fresh_trigger().maybe_auto_print("000102", "default", "CONFIRMED", db=db)
        assert result["created"] is True

    def test_case_insensitive_status(self, db):
        _create_order(db, "000103")
        result = _fresh_trigger().maybe_auto_print("000103", "default", "paid", db=db)
        assert result["created"] is True


class TestReceiptHasRealData:
    """O motivo de existir a F10.7: o cupom saía com items=[] e total=0."""

    def test_job_payload_contains_real_items_and_total(self, db):
        from app.application.printing.print_queue import PrintQueueService

        _create_order(db, "000110")
        result = _fresh_trigger().maybe_auto_print("000110", "default", "PAID", db=db)
        assert result["created"] is True

        job = PrintQueueService(db, "default").get_job(result["job_id"])
        assert job is not None
        text = (job.payload or b"").decode("cp850", errors="replace")

        # Nome do produto (o formatador trunca em 22 colunas na linha do item)
        assert "Botijao de Gas P13 (13" in text
        assert "R$ 120,00" in text  # subtotal do item, não zero
        assert "R$ 125,00" in text  # total com taxa de entrega
        assert "DINHEIRO" in text
        assert "Trocar o botijão vazio" in text  # observações (acento via cp850)
        # Separador é traço, não o número da largura (bug do char posicional)
        assert "-" * 20 in text
        assert "48484848" not in text

    def test_build_receipt_data_uses_order_fields(self, db):
        from app.application.printing.receipt_data import build_receipt_data

        _create_order(db, "000111")
        data = build_receipt_data(db, "default", "000111")

        assert data["codigo"] == "000111"
        assert data["subtotal"] == 120.0
        assert data["delivery_fee"] == 5.0
        assert data["total"] == 125.0
        assert data["payment_method"] == "DINHEIRO"
        assert data["client_address"].startswith("Rua das Flores")
        assert len(data["items"]) == 1
        assert data["items"][0]["product_nome"] == "Botijao de Gas P13 (13kg)"
        assert data["items"][0]["subtotal"] == 120.0

    def test_unknown_order_is_an_error_not_an_empty_receipt(self, db):
        from app.application.printing.receipt_data import (
            OrderNotFoundError,
            build_receipt_data,
        )

        with pytest.raises(OrderNotFoundError):
            build_receipt_data(db, "default", "999999")


class TestIdempotency:
    def test_repeated_event_does_not_create_second_job(self, db):
        _create_order(db, "000120")
        trigger = _fresh_trigger()
        first = trigger.maybe_auto_print("000120", "default", "PAID", db=db)
        second = trigger.maybe_auto_print("000120", "default", "PAID", db=db)

        assert first["created"] is True
        assert second["created"] is False
        assert second["skipped_reason"] == "already_auto_printed"

        from app.application.printing.print_queue import PrintQueueService

        assert len(PrintQueueService(db, "default").jobs_for_order("000120")) == 1

    def test_manual_reprint_is_not_blocked_by_idempotency(self, db):
        """Reimpressão manual (is_reprint) nunca é bloqueada pela marca."""
        from app.application.printing.print_queue import PrintQueueService

        _create_order(db, "000121")
        trigger = _fresh_trigger()
        trigger.maybe_auto_print("000121", "default", "PAID", db=db)

        queue = PrintQueueService(db, "default")
        reprint = queue.enqueue(order_id="000121", requested_by="admin", is_reprint=True)

        assert reprint.is_reprint is True
        assert len(queue.jobs_for_order("000121")) == 2
        # A marca de auto-print continua sendo só a do job automático
        assert queue.has_job_for_order("000121", only_auto=True) is True

    def test_failed_enqueue_leaves_no_mark(self, db):
        """Pedido inexistente → nada criado → próximo evento tenta de novo."""
        trigger = _fresh_trigger()
        result = trigger.maybe_auto_print("000199", "default", "PAID", db=db)
        assert result["created"] is False
        assert result["skipped_reason"] == "job_error"
        assert not trigger.already_printed("000199", "default", db)


class TestSettingConfig:
    def test_setting_read_single_status(self, db, monkeypatch):
        import app.infrastructure.database.init_db as init_db
        from app.application.settings.settings_service import SettingsService

        import app.infrastructure.repositories.settings_model  # noqa: F401

        SettingsService(db).seed_defaults()
        SettingsService(db).update("printer.auto_print.min_status", "PAID", updated_by="test")

        import app.application.delivery.auto_print_trigger as apt

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
            order_id="000200",
            tenant_id="default",
            order_status="PAID",
        )

    def test_hook_passes_session_and_status(self, monkeypatch):
        """Contrato: o hook repassa a sessão do endpoint (o cupom precisa do
        pedido real, visível na mesma transação)."""
        import app.application.delivery.auto_print_trigger as apt
        from app.presentation.api import orders as orders_api

        calls = []
        sentinel_db = object()

        def _spy(self, **kwargs):
            calls.append(kwargs)
            return {"created": False, "skipped_reason": "status_not_eligible:DRAFT"}

        monkeypatch.setattr(apt.AutoPrintTrigger, "maybe_auto_print", _spy)
        orders_api._safe_auto_print(
            order_id="000201",
            tenant_id="default",
            order_status="PAID",
            db=sentinel_db,
        )

        assert len(calls) == 1
        assert calls[0]["order_id"] == "000201"
        assert calls[0]["order_status"] == "PAID"
        assert calls[0]["db"] is sentinel_db

    def test_trigger_never_raises(self, db):
        """maybe_auto_print engole exceções internas (settings, enfileiramento)."""
        result = _fresh_trigger().maybe_auto_print("000202", "default", "", db=db)
        assert result["created"] is False
        assert result["skipped_reason"] == "status_not_eligible:EMPTY"
