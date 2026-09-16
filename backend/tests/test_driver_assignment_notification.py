"""
Testes F3 — Zap do entregador na atribuição (driver_assignment_notification).

Cobre:
- Idempotência: 1 execução por (delivery_id, driver_id); reatribuição do
  mesmo driver não duplica; reatribuição para outro driver cria nova.
- Renderização do template default.
- Hook no AssignmentService.assign: cria execução PENDING e não quebra a
  atribuição se a notificação falhar.
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


@pytest.fixture()
def auto_repo(db):
    import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401
    from app.infrastructure.repositories.whatsapp_automation_repository import (
        SQLAlchemyAutomationRepository,
    )

    return SQLAlchemyAutomationRepository(db, "default")


def _pending_execs(auto_repo, rule_id):
    from app.domain.whatsapp_automation.entity import ExecutionStatus

    return [e for e in auto_repo.list_executions(rule_id=rule_id, limit=500) if e.status == ExecutionStatus.PENDING]


class TestDriverAssignmentIdempotency:
    def test_first_assignment_creates_execution(self, auto_repo):
        from app.application.delivery.driver_notification import DriverAssignmentNotifier

        notifier = DriverAssignmentNotifier(auto_repo)
        result = notifier.notify_assignment(
            delivery_id="DLV-1",
            driver_codigo="M-001",
            payload={
                "driver_name": "João",
                "order_ref": "ORD-10",
                "customer_name": "Maria",
                "address": "Rua A, 10",
                "customer_phone": "5511999990001",
            },
        )

        assert result["success"] is True
        assert result["created"] is True
        execs = _pending_execs(auto_repo, notifier._get_or_create_rule().id)
        assert len(execs) == 1
        assert "ORD-10" in execs[0].message_text
        assert "Maria" in execs[0].message_text
        assert execs[0].customer_phone == "5511999990001"
        assert execs[0].trigger_context["delivery_id"] == "DLV-1"
        assert execs[0].trigger_context["driver_codigo"] == "M-001"

    def test_same_driver_reassignment_does_not_duplicate(self, auto_repo):
        from app.application.delivery.driver_notification import DriverAssignmentNotifier

        notifier = DriverAssignmentNotifier(auto_repo)
        first = notifier.notify_assignment(delivery_id="DLV-2", driver_codigo="M-001")
        second = notifier.notify_assignment(delivery_id="DLV-2", driver_codigo="M-001")

        assert first["created"] is True
        assert second["success"] is True
        assert second.get("idempotent_replay") is True
        assert second.get("created") is False
        assert len(_pending_execs(auto_repo, notifier._get_or_create_rule().id)) == 1

    def test_reassignment_to_other_driver_creates_new_execution(self, auto_repo):
        from app.application.delivery.driver_notification import DriverAssignmentNotifier

        notifier = DriverAssignmentNotifier(auto_repo)
        notifier.notify_assignment(delivery_id="DLV-3", driver_codigo="M-001")
        second = notifier.notify_assignment(delivery_id="DLV-3", driver_codigo="M-002")

        assert second["created"] is True
        assert len(_pending_execs(auto_repo, notifier._get_or_create_rule().id)) == 2

    def test_default_template_renders_variables(self):
        from app.application.delivery.driver_notification import render_assignment_message

        msg = render_assignment_message(
            {
                "driver_name": "João",
                "order_ref": "ORD-10",
                "customer_name": "Maria",
                "address": "Rua A, 10",
            }
        )
        assert "João" in msg and "ORD-10" in msg and "Maria" in msg and "Rua A, 10" in msg


class TestAssignmentServiceHook:
    def test_assign_creates_pending_execution(self, db, monkeypatch):
        """assign() enfileira a notificação via engine global (path real)."""
        import app.infrastructure.database.init_db as init_db
        from app.application.delivery.assignment_service import AssignmentService
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
        from app.domain.whatsapp_automation.entity import ExecutionStatus
        from app.infrastructure.repositories.whatsapp_automation_repository import (
            SQLAlchemyAutomationRepository,
        )

        import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401

        db.add(
            DeliveryDriverModel(
                tenant_id="default",
                codigo="M-HOOK",
                nome="Hook Driver",
                telefone="5511900000000",
                status="AVAILABLE",
                ativo=True,
            )
        )
        db.commit()

        # Monkeypatch do engine global: _notify_driver abre própria session.
        monkeypatch.setattr(init_db, "engine", db.get_bind())

        service = AssignmentService(db)
        result = service.assign(tenant_id="default", delivery_id="DLV-HOOK-1", driver_codigo="M-HOOK")
        assert result["success"] is True

        repo = SQLAlchemyAutomationRepository(db, "default")
        pending = _pending_execs(repo, notifier_rule_id(repo))
        assert len(pending) == 1
        assert pending[0].status == ExecutionStatus.PENDING
        assert pending[0].customer_phone == "5511900000000"

    def test_assign_survives_notification_failure(self, db, monkeypatch):
        """Se a notificação explodir, a atribuição continua OK (rollback não ocorre)."""
        import app.infrastructure.database.init_db as init_db
        from app.application.delivery.assignment_service import AssignmentService
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

        import app.infrastructure.repositories.whatsapp_automation_model  # noqa: F401

        db.add(
            DeliveryDriverModel(
                tenant_id="default",
                codigo="M-FAIL",
                nome="Fail Driver",
                telefone="5511900000001",
                status="AVAILABLE",
                ativo=True,
            )
        )
        db.commit()

        class BoomRepo:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(init_db, "engine", db.get_bind())
        monkeypatch.setattr(
            "app.application.delivery.assignment_service.SQLAlchemyAutomationRepository",
            BoomRepo,
        )

        service = AssignmentService(db)
        result = service.assign(tenant_id="default", delivery_id="DLV-FAIL-1", driver_codigo="M-FAIL")
        assert result["success"] is True

        driver = db.query(DeliveryDriverModel).filter_by(codigo="M-FAIL").first()
        assert driver.status == "BUSY"


def notifier_rule_id(repo):
    from app.application.delivery.driver_notification import RULE_NAME

    for rule in repo.list_rules():
        if rule.name == RULE_NAME:
            return rule.id
    pytest.fail("rule de notificação não foi criada")
