"""
Payment Service Persistence Tests — P0.2

Verifies that payment state survives process restart
by using the database as single source of truth.
"""

import pytest
from datetime import datetime
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.domain.payment.service import PaymentService
from app.domain.payment.models import PaymentStatus


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = DBSession(bind=engine)
    yield session
    session.close()


@pytest.fixture
def payment_service(db):
    return PaymentService(db=db)


# ═══════════════════════════════════════════════════════════
# PAYMENT METHOD TESTS
# ═══════════════════════════════════════════════════════════

class TestPaymentMethodPersistence:
    def test_create_method_persists(self, db, payment_service):
        method = payment_service.create_method("t1", "PIX", "PIX", "PIX")
        assert method.code == "PIX"
        # Verify in new instance
        ps2 = PaymentService(db=db)
        methods = ps2.get_methods("t1")
        assert len(methods) == 1
        assert methods[0].code == "PIX"

    def test_toggle_method_persists(self, db, payment_service):
        method = payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        payment_service.toggle_method(method.id, "t1")
        ps2 = PaymentService(db=db)
        m = ps2.get_method(method.id, "t1")
        assert m.enabled is False

    def test_delete_method_persists(self, db, payment_service):
        method = payment_service.create_method("t1", "CARD", "Cartão", "CREDIT_CARD")
        payment_service.delete_method(method.id, "t1")
        ps2 = PaymentService(db=db)
        assert ps2.get_method(method.id, "t1") is None

    def test_method_tenant_isolation(self, db, payment_service):
        payment_service.create_method("t1", "PIX", "PIX A", "PIX")
        payment_service.create_method("t2", "PIX", "PIX B", "PIX")
        ps2 = PaymentService(db=db)
        assert len(ps2.get_methods("t1")) == 1
        assert len(ps2.get_methods("t2")) == 1
        assert ps2.get_methods("t1")[0].name == "PIX A"


# ═══════════════════════════════════════════════════════════
# PIX CONFIG TESTS
# ═══════════════════════════════════════════════════════════

class TestPixConfigPersistence:
    def test_create_pix_config_persists(self, db, payment_service):
        config = payment_service.create_pix_config("t1", "key-123", "EMAIL", "Test")
        assert config.key == "key-123"
        ps2 = PaymentService(db=db)
        active = ps2.get_pix_config("t1")
        assert active is not None
        assert active.key == "key-123"

    def test_pix_config_tenant_isolation(self, db, payment_service):
        payment_service.create_pix_config("t1", "key-a")
        payment_service.create_pix_config("t2", "key-b")
        ps2 = PaymentService(db=db)
        assert ps2.get_pix_config("t1").key == "key-a"
        assert ps2.get_pix_config("t2").key == "key-b"


# ═══════════════════════════════════════════════════════════
# PAYMENT TESTS
# ═══════════════════════════════════════════════════════════

class TestPaymentPersistence:
    def test_create_payment_persists(self, db, payment_service):
        payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        payment = payment_service.create_payment(
            "t1", "order-1", "ORD-001", "C001", 100.0, "CASH",
        )
        assert payment.status == PaymentStatus.PENDING
        ps2 = PaymentService(db=db)
        found = ps2.get_payment(payment.id, "t1")
        assert found is not None
        assert found.amount == 100.0

    def test_confirm_payment_persists(self, db, payment_service):
        payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        payment = payment_service.create_payment(
            "t1", "order-1", "ORD-001", "C001", 50.0, "CASH",
        )
        payment_service.confirm_payment(payment.id, "t1", confirmed_by="admin")
        ps2 = PaymentService(db=db)
        found = ps2.get_payment(payment.id, "t1")
        assert found.status == PaymentStatus.CONFIRMED
        assert found.confirmed_by == "admin"

    def test_cancel_payment_persists(self, db, payment_service):
        payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        payment = payment_service.create_payment(
            "t1", "order-1", "ORD-001", "C001", 50.0, "CASH",
        )
        payment_service.cancel_payment(payment.id, "t1", reason="Changed mind")
        ps2 = PaymentService(db=db)
        found = ps2.get_payment(payment.id, "t1")
        assert found.status == PaymentStatus.CANCELLED

    def test_refund_payment_persists(self, db, payment_service):
        payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        payment = payment_service.create_payment(
            "t1", "order-1", "ORD-001", "C001", 75.0, "CASH",
        )
        payment_service.confirm_payment(payment.id, "t1")
        payment_service.refund_payment(payment.id, "t1", reason="Defect")
        ps2 = PaymentService(db=db)
        found = ps2.get_payment(payment.id, "t1")
        assert found.status == PaymentStatus.REFUNDED

    def test_order_total_paid_persists(self, db, payment_service):
        payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        p1 = payment_service.create_payment("t1", "o1", "ORD-1", "C1", 100.0, "CASH")
        p2 = payment_service.create_payment("t1", "o1", "ORD-1", "C1", 50.0, "CASH")
        payment_service.confirm_payment(p1.id, "t1")
        # p2 still pending
        ps2 = PaymentService(db=db)
        total = ps2.get_order_total_paid("o1", "t1")
        assert total == 100.0

    def test_payment_summary_persists(self, db, payment_service):
        payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        p1 = payment_service.create_payment("t1", "o1", "ORD-1", "C1", 100.0, "CASH")
        payment_service.confirm_payment(p1.id, "t1")
        ps2 = PaymentService(db=db)
        summary = ps2.get_payment_summary("t1")
        assert summary["total_received"] == 100.0
        assert summary["confirmed_count"] == 1

    def test_payment_tenant_isolation(self, db, payment_service):
        payment_service.create_method("t1", "CASH", "Dinheiro", "CASH")
        payment_service.create_method("t2", "CASH", "Dinheiro", "CASH")
        payment_service.create_payment("t1", "o1", "ORD-1", "C1", 100.0, "CASH")
        payment_service.create_payment("t2", "o2", "ORD-2", "C2", 200.0, "CASH")
        ps2 = PaymentService(db=db)
        assert len(ps2.get_payments_for_tenant("t1")) == 1
        assert len(ps2.get_payments_for_tenant("t2")) == 1
        assert ps2.get_payments_for_tenant("t1")[0].amount == 100.0

    def test_restart_survives(self, db, payment_service):
        """Full lifecycle survives restart."""
        payment_service.create_method("t1", "PIX", "PIX", "PIX")
        payment_service.create_pix_config("t1", "key-abc", "EMAIL", "Test")
        payment = payment_service.create_payment(
            "t1", "order-1", "ORD-001", "C001", 150.0, "PIX",
        )
        payment_service.confirm_payment(payment.id, "t1", confirmed_by="admin")

        # Simulate restart
        ps2 = PaymentService(db=db)
        methods = ps2.get_methods("t1")
        assert len(methods) == 1
        assert methods[0].code == "PIX"

        pix = ps2.get_pix_config("t1")
        assert pix.key == "key-abc"

        found = ps2.get_payment(payment.id, "t1")
        assert found.status == PaymentStatus.CONFIRMED
        assert found.amount == 150.0

        summary = ps2.get_payment_summary("t1")
        assert summary["total_received"] == 150.0
