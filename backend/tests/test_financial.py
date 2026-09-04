"""
FASE 8 — FINANCIAL CORE TESTS
==============================
Every test uses real in-memory SQLite.
Covers: Money, Payment, Receivable, Expense, Cash, Ledger,
        Transaction, Concurrency, Order integration.
"""

import pytest
import threading
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.financial_models import (
    PaymentModel, ExpenseModel,
    CashMovementModel, FinancialLedgerModel
)
from app.infrastructure.repositories.financial_repositories import (
    SQLAlchemyPaymentRepository, SQLAlchemyReceivableRepository,
    SQLAlchemyExpenseRepository, SQLAlchemyCashMovementRepository,
    SQLAlchemyFinancialLedgerRepository,
)
from app.application.financial.use_cases import (
    RegisterPaymentUseCase, RegisterExpenseUseCase,
    RefundPaymentUseCase, FinancialReportsUseCase,
    CreateReceivableUseCase,
)
from app.domain.financial.payment import Payment, PaymentStatus, PaymentMethod
from app.domain.financial.receivable import Receivable, ReceivableStatus
from app.domain.financial.expense import Expense, ExpenseStatus
from app.domain.financial.cash_movement import CashMovement, CashMovementType
from app.domain.financial.ledger import FinancialLedgerEntry, LedgerEventType


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(c, _):
        cur = c.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _seed_order(db, order_codigo="ORD001", client_codigo="000001",
                product_codigo="P00001", total=Decimal("100.00")):
    """Seed a complete order with all dependencies."""
    c = ClientModel(codigo=client_codigo, nome="Test Client",
                    telefone="11999999999", rua="Rua A", numero="1", bairro="Centro")
    db.add(c)
    p = ProductModel(codigo=product_codigo, nome="GLP P13",
                     tipo="GAS", preco=float(total), estoque=0)
    db.add(p)
    o = OrderModel(
        codigo=order_codigo, client_codigo=client_codigo,
        subtotal=float(total), delivery_fee=0.0, discount=0.0,
        total=float(total), payment_method="CASH",
        payment_status="PENDING", status="CONFIRMED",
        source="MANUAL", address_snapshot="Rua A, 1",
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(o)
    db.commit()
    return o


# ═══════════════════════════════════════════════════════════
# 1. MONEY MODEL (Decimal)
# ═══════════════════════════════════════════════════════════

class TestMoneyModel:
    def test_decimal_precision(self):
        """R$ 10.005 rounds correctly."""
        amount = Decimal("10.005").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert amount == Decimal("10.01")

    def test_decimal_truncation(self):
        """R$ 10.004 rounds down."""
        amount = Decimal("10.004").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert amount == Decimal("10.00")

    def test_decimal_half_up(self):
        """0.005 rounds up."""
        amount = Decimal("0.005").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert amount == Decimal("0.01")

    def test_decimal_large(self):
        """99.995 rounds to 100.00."""
        amount = Decimal("99.995").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert amount == Decimal("100.00")

    def test_payment_rejects_zero(self):
        with pytest.raises(ValueError, match="greater than zero"):
            Payment(order_codigo="X", amount=Decimal("0.00"))

    def test_payment_rejects_negative(self):
        with pytest.raises(ValueError, match="greater than zero"):
            Payment(order_codigo="X", amount=Decimal("-10.00"))

    def test_payment_accepts_float_converted(self):
        p = Payment(order_codigo="X", amount=50.0)
        assert p.amount == Decimal("50.00")

    def test_receivable_rejects_zero(self):
        with pytest.raises(ValueError, match="must be > 0"):
            Receivable(order_codigo="X", customer_codigo="C",
                       original_amount=Decimal("0.00"))

    def test_receivable_rejects_negative_paid(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            Receivable(order_codigo="X", customer_codigo="C",
                       original_amount=Decimal("100.00"),
                       paid_amount=Decimal("-10.00"))

    def test_expense_rejects_negative(self):
        with pytest.raises(ValueError, match="must be > 0"):
            Expense(description="X", amount=Decimal("-5.00"))

    def test_cash_movement_rejects_zero(self):
        with pytest.raises(ValueError, match="must be > 0"):
            CashMovement(amount=Decimal("0.00"))


# ═══════════════════════════════════════════════════════════
# 2. PAYMENT
# ═══════════════════════════════════════════════════════════

class TestPayment:
    def test_full_payment(self, db):
        """Order = 100, Payment = 100 → PAID."""
        _seed_order(db, total=Decimal("100.00"))
        repo = SQLAlchemyPaymentRepository(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)

        # Create receivable
        uc_recv = CreateReceivableUseCase(recv_repo, ledger_repo)
        uc_recv.execute("ORD001", "000001", Decimal("100.00"))

        # Full payment
        uc = RegisterPaymentUseCase(repo, recv_repo, cash_repo, ledger_repo)
        result = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("100.00"),
            "method": "CASH",
        })
        assert result["payment"].status == PaymentStatus.PAID
        assert result["receivable"].status == ReceivableStatus.PAID
        assert result["receivable"].remaining_amount == Decimal("0.00")

    def test_partial_payment(self, db):
        """Order = 100, Payment 40 → PARTIAL."""
        _seed_order(db, total=Decimal("100.00"))
        repo = SQLAlchemyPaymentRepository(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)

        uc_recv = CreateReceivableUseCase(recv_repo, ledger_repo)
        uc_recv.execute("ORD001", "000001", Decimal("100.00"))

        uc = RegisterPaymentUseCase(repo, recv_repo, cash_repo, ledger_repo)
        result = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("40.00"),
            "method": "PIX",
        })
        assert result["receivable"].status == ReceivableStatus.PARTIAL
        assert result["receivable"].remaining_amount == Decimal("60.00")

    def test_multiple_payments(self, db):
        """Order = 100, 40 + 30 + 30 → PAID."""
        _seed_order(db, total=Decimal("100.00"))
        repo = SQLAlchemyPaymentRepository(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)

        uc_recv = CreateReceivableUseCase(recv_repo, ledger_repo)
        uc_recv.execute("ORD001", "000001", Decimal("100.00"))

        uc = RegisterPaymentUseCase(repo, recv_repo, cash_repo, ledger_repo)
        uc.execute({"order_codigo": "ORD001", "amount": Decimal("40.00"), "method": "CASH"})
        uc.execute({"order_codigo": "ORD001", "amount": Decimal("30.00"), "method": "PIX"})
        result = uc.execute({"order_codigo": "ORD001", "amount": Decimal("30.00"), "method": "CARD"})

        assert result["receivable"].status == ReceivableStatus.PAID
        assert result["receivable"].paid_amount == Decimal("100.00")

    def test_overpayment_rejected(self, db):
        """Payment > remaining → rejected."""
        _seed_order(db, total=Decimal("100.00"))
        repo = SQLAlchemyPaymentRepository(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)

        uc_recv = CreateReceivableUseCase(recv_repo, ledger_repo)
        uc_recv.execute("ORD001", "000001", Decimal("100.00"))

        uc = RegisterPaymentUseCase(repo, recv_repo, cash_repo, ledger_repo)
        with pytest.raises(ValueError, match="exceeds remaining"):
            uc.execute({"order_codigo": "ORD001", "amount": Decimal("110.00"), "method": "CASH"})

    def test_payment_idempotency(self, db):
        """Same idempotency_key → not duplicated."""
        _seed_order(db, total=Decimal("100.00"))
        repo = SQLAlchemyPaymentRepository(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)

        uc_recv = CreateReceivableUseCase(recv_repo, ledger_repo)
        uc_recv.execute("ORD001", "000001", Decimal("100.00"))

        uc = RegisterPaymentUseCase(repo, recv_repo, cash_repo, ledger_repo)
        r1 = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("50.00"),
            "method": "PIX", "idempotency_key": "key-001",
        })
        assert r1["status"] == "created"

        r2 = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("50.00"),
            "method": "PIX", "idempotency_key": "key-001",
        })
        assert r2["status"] == "already_exists"

        # Only 1 payment
        payments = repo.get_by_order("ORD001")
        assert len(payments) == 1

    def test_payment_negative_rejected(self, db):
        _seed_order(db, total=Decimal("100.00"))
        uc = RegisterPaymentUseCase(
            SQLAlchemyPaymentRepository(db),
            SQLAlchemyReceivableRepository(db),
            SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db),
        )
        CreateReceivableUseCase(
            SQLAlchemyReceivableRepository(db),
            SQLAlchemyFinancialLedgerRepository(db),
        ).execute("ORD001", "000001", Decimal("100.00"))

        with pytest.raises(ValueError, match="must be > 0"):
            uc.execute({"order_codigo": "ORD001", "amount": Decimal("-10.00"), "method": "CASH"})

    def test_payment_stores_decimal(self, db):
        """Payment amount stored as Decimal, not float."""
        _seed_order(db, total=Decimal("99.99"))
        repo = SQLAlchemyPaymentRepository(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)

        CreateReceivableUseCase(recv_repo, ledger_repo).execute(
            "ORD001", "000001", Decimal("99.99"))

        uc = RegisterPaymentUseCase(repo, recv_repo, cash_repo, ledger_repo)
        result = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("99.99"),
            "method": "CASH",
        })
        assert result["payment"].amount == Decimal("99.99")
        # Verify in DB as Decimal
        model = db.query(PaymentModel).filter(PaymentModel.id == result["payment"].id).first()
        assert isinstance(model.amount, Decimal)


# ═══════════════════════════════════════════════════════════
# 3. RECEIVABLE
# ═══════════════════════════════════════════════════════════

class TestReceivable:
    def test_receivable_open(self, db):
        _seed_order(db)
        repo = SQLAlchemyReceivableRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        uc = CreateReceivableUseCase(repo, ledger)
        r = uc.execute("ORD001", "000001", Decimal("100.00"))
        assert r.status == ReceivableStatus.OPEN
        assert r.remaining_amount == Decimal("100.00")

    def test_receivable_partial(self, db):
        _seed_order(db)
        repo = SQLAlchemyReceivableRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        uc = CreateReceivableUseCase(repo, ledger)
        r = uc.execute("ORD001", "000001", Decimal("100.00"))

        r.paid_amount = Decimal("40.00")
        r.status = ReceivableStatus.PARTIAL
        r = repo.update(r)
        assert r.remaining_amount == Decimal("60.00")

    def test_receivable_paid(self, db):
        _seed_order(db)
        repo = SQLAlchemyReceivableRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        r = CreateReceivableUseCase(repo, ledger).execute("ORD001", "000001", Decimal("100.00"))
        r.paid_amount = Decimal("100.00")
        r.status = ReceivableStatus.PAID
        r.settled_at = datetime.utcnow()
        r = repo.update(r)
        assert r.remaining_amount == Decimal("0.00")
        assert r.status == ReceivableStatus.PAID

    def test_receivable_overdue(self, db):
        _seed_order(db)
        repo = SQLAlchemyReceivableRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        r = CreateReceivableUseCase(repo, ledger).execute(
            "ORD001", "000001", Decimal("100.00"),
            due_date=datetime.utcnow() - timedelta(days=5)
        )
        # Update overdue
        count = repo.update_overdue_status(datetime.utcnow())
        assert count >= 1
        updated = repo.get_by_order("ORD001")
        assert updated.status == ReceivableStatus.OVERDUE

    def test_receivable_no_duplicate(self, db):
        _seed_order(db)
        repo = SQLAlchemyReceivableRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        uc = CreateReceivableUseCase(repo, ledger)
        r1 = uc.execute("ORD001", "000001", Decimal("100.00"))
        r2 = uc.execute("ORD001", "000001", Decimal("100.00"))
        assert r1.id == r2.id

    def test_customer_outstanding(self, db):
        _seed_order(db)
        repo = SQLAlchemyReceivableRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        CreateReceivableUseCase(repo, ledger).execute(
            "ORD001", "000001", Decimal("100.00"))
        outstanding = repo.total_outstanding_for_customer("000001")
        assert outstanding == Decimal("100.00")


# ═══════════════════════════════════════════════════════════
# 4. EXPENSE
# ═══════════════════════════════════════════════════════════

class TestExpense:
    def test_create_expense(self, db):
        repo = SQLAlchemyExpenseRepository(db)
        cash = SQLAlchemyCashMovementRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        uc = RegisterExpenseUseCase(repo, cash, ledger)
        result = uc.execute({
            "description": "Diesel refill",
            "amount": Decimal("250.00"),
            "category": "FUEL",
        })
        assert result["expense"].amount == Decimal("250.00")
        assert result["expense"].status == ExpenseStatus.ACTIVE

    def test_negative_expense_rejected(self, db):
        uc = RegisterExpenseUseCase(
            SQLAlchemyExpenseRepository(db),
            SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db),
        )
        with pytest.raises(ValueError, match="must be > 0"):
            uc.execute({"description": "X", "amount": Decimal("-5.00")})

    def test_cancel_expense(self, db):
        repo = SQLAlchemyExpenseRepository(db)
        uc = RegisterExpenseUseCase(
            repo, SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db))
        result = uc.execute({"description": "Test", "amount": Decimal("50.00")})
        expense = repo.cancel(result["expense"].id)
        assert expense.status == ExpenseStatus.CANCELLED

    def test_expense_by_period(self, db):
        repo = SQLAlchemyExpenseRepository(db)
        uc = RegisterExpenseUseCase(
            repo, SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db))
        uc.execute({"description": "A", "amount": Decimal("100.00")})
        uc.execute({"description": "B", "amount": Decimal("200.00")})

        start = datetime.utcnow().replace(hour=0, minute=0, second=0)
        end = start + timedelta(days=1)
        total = repo.total_by_period(start, end)
        assert total == Decimal("300.00")

    def test_expense_stores_decimal(self, db):
        repo = SQLAlchemyExpenseRepository(db)
        uc = RegisterExpenseUseCase(
            repo, SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db))
        result = uc.execute({"description": "Test", "amount": Decimal("99.99")})
        model = db.query(ExpenseModel).filter(ExpenseModel.id == result["expense"].id).first()
        assert isinstance(model.amount, Decimal)


# ═══════════════════════════════════════════════════════════
# 5. CASH MOVEMENTS
# ═══════════════════════════════════════════════════════════

class TestCashMovement:
    def test_receipt_increases_balance(self, db):
        repo = SQLAlchemyCashMovementRepository(db)
        m = repo.create(CashMovement(
            type=CashMovementType.RECEIPT,
            amount=Decimal("100.00"),
            description="Test receipt",
            balance_after=Decimal("100.00"),
        ))
        assert repo.current_balance() == Decimal("100.00")

    def test_expense_decreases_balance(self, db):
        repo = SQLAlchemyCashMovementRepository(db)
        repo.create(CashMovement(
            type=CashMovementType.RECEIPT,
            amount=Decimal("100.00"), description="In",
            balance_after=Decimal("100.00"),
        ))
        repo.create(CashMovement(
            type=CashMovementType.EXPENSE,
            amount=Decimal("30.00"), description="Out",
            balance_after=Decimal("70.00"),
        ))
        assert repo.current_balance() == Decimal("70.00")

    def test_refund_decreases_balance(self, db):
        repo = SQLAlchemyCashMovementRepository(db)
        repo.create(CashMovement(
            type=CashMovementType.RECEIPT,
            amount=Decimal("100.00"), description="In",
            balance_after=Decimal("100.00"),
        ))
        repo.create(CashMovement(
            type=CashMovementType.REFUND,
            amount=Decimal("25.00"), description="Refund",
            balance_after=Decimal("75.00"),
        ))
        assert repo.current_balance() == Decimal("75.00")

    def test_balance_starts_zero(self, db):
        repo = SQLAlchemyCashMovementRepository(db)
        assert repo.current_balance() == Decimal("0.00")

    def test_cash_flow_full_cycle(self, db):
        """Receipt - Expense + Refund."""
        repo = SQLAlchemyCashMovementRepository(db)
        repo.create(CashMovement(
            type=CashMovementType.RECEIPT,
            amount=Decimal("500.00"), description="Sales",
            balance_after=Decimal("500.00"),
        ))
        repo.create(CashMovement(
            type=CashMovementType.EXPENSE,
            amount=Decimal("100.00"), description="Fuel",
            balance_after=Decimal("400.00"),
        ))
        repo.create(CashMovement(
            type=CashMovementType.REFUND,
            amount=Decimal("50.00"), description="Refund",
            balance_after=Decimal("350.00"),
        ))
        assert repo.current_balance() == Decimal("350.00")


# ═══════════════════════════════════════════════════════════
# 6. LEDGER
# ═══════════════════════════════════════════════════════════

class TestLedger:
    def test_ledger_immutable(self, db):
        repo = SQLAlchemyFinancialLedgerRepository(db)
        entry = repo.create(FinancialLedgerEntry(
            event_type=LedgerEventType.PAYMENT_CREATED,
            amount=Decimal("100.00"),
            description="Test",
        ))
        # No update/delete methods — immutable by design
        assert not hasattr(repo, 'update')
        assert not hasattr(repo, 'delete')

    def test_ledger_consistent(self, db):
        """Ledger entries are consistently created."""
        repo = SQLAlchemyFinancialLedgerRepository(db)
        repo.create(FinancialLedgerEntry(
            event_type=LedgerEventType.PAYMENT_CREATED,
            amount=Decimal("100.00"), description="P1",
            reference_type="PAYMENT", reference_id="1",
        ))
        repo.create(FinancialLedgerEntry(
            event_type=LedgerEventType.EXPENSE_CREATED,
            amount=Decimal("50.00"), description="E1",
            reference_type="EXPENSE", reference_id="1",
        ))
        items, total = repo.list_all()
        assert total == 2

    def test_ledger_exists(self, db):
        repo = SQLAlchemyFinancialLedgerRepository(db)
        repo.create(FinancialLedgerEntry(
            event_type=LedgerEventType.PAYMENT_CREATED,
            amount=Decimal("100.00"), description="P1",
            reference_type="PAYMENT", reference_id="1",
        ))
        assert repo.exists("PAYMENT", "1", LedgerEventType.PAYMENT_CREATED)
        assert not repo.exists("PAYMENT", "999", LedgerEventType.PAYMENT_CREATED)


# ═══════════════════════════════════════════════════════════
# 7. TRANSACTIONS + ROLLBACK
# ═══════════════════════════════════════════════════════════

class TestTransactions:
    def test_payment_creates_all_records(self, db):
        """Payment creates: payment + cash + ledger."""
        _seed_order(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)
        CreateReceivableUseCase(recv_repo, ledger_repo).execute(
            "ORD001", "000001", Decimal("100.00"))

        uc = RegisterPaymentUseCase(
            SQLAlchemyPaymentRepository(db),
            recv_repo,
            SQLAlchemyCashMovementRepository(db),
            ledger_repo,
        )
        result = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("100.00"),
            "method": "CASH",
        })

        # All records exist
        assert result["payment"].id is not None
        assert result["cash_movement"].id is not None
        assert db.query(PaymentModel).count() == 1
        assert db.query(CashMovementModel).count() == 1
        assert db.query(FinancialLedgerModel).count() >= 1

    def test_expense_creates_records(self, db):
        uc = RegisterExpenseUseCase(
            SQLAlchemyExpenseRepository(db),
            SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db),
        )
        result = uc.execute({"description": "Test", "amount": Decimal("50.00")})
        assert db.query(ExpenseModel).count() == 1
        assert db.query(CashMovementModel).count() == 1


# ═══════════════════════════════════════════════════════════
# 8. CONCURRENCY
# ═══════════════════════════════════════════════════════════

class TestConcurrency:
    def test_concurrent_payments_dont_overpay(self, db):
        """Two threads paying 100 each on a 100 order.
        Result: at most 100 total paid."""
        _seed_order(db, total=Decimal("100.00"))
        recv_repo = SQLAlchemyReceivableRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)
        CreateReceivableUseCase(recv_repo, ledger_repo).execute(
            "ORD001", "000001", Decimal("100.00"))
        db.close()  # close main session before threading

        # Use a shared engine for thread safety
        shared_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        @event.listens_for(shared_engine, "connect")
        def set_pragma(c, _):
            cur = c.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            cur.close()
        Base.metadata.create_all(bind=shared_engine)
        Sess = sessionmaker(bind=shared_engine)

        # Seed data into shared engine using ORM
        seed_s = Sess()
        seed_s.add(ClientModel(codigo="000001", nome="Test", telefone="11999999999",
                               rua="Rua A", numero="1", bairro="Centro"))
        seed_s.add(ProductModel(codigo="P00001", nome="GLP", tipo="GAS",
                                preco=100.0, estoque=0))
        seed_s.add(OrderModel(codigo="ORD001", client_codigo="000001",
                               subtotal=100.0, delivery_fee=0.0, discount=0.0, total=100.0,
                               payment_method="CASH", payment_status="PENDING", status="CONFIRMED",
                               source="MANUAL", address_snapshot="Rua A",
                               created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        seed_s.commit()
        seed_s.close()

        results = []
        errors = []

        def pay_thread():
            try:
                s = Sess()
                try:
                    uc = RegisterPaymentUseCase(
                        SQLAlchemyPaymentRepository(s),
                        SQLAlchemyReceivableRepository(s),
                        SQLAlchemyCashMovementRepository(s),
                        SQLAlchemyFinancialLedgerRepository(s),
                    )
                    r = uc.execute({
                        "order_codigo": "ORD001", "amount": Decimal("100.00"),
                        "method": "CASH",
                    })
                    results.append(r["status"])
                except ValueError as e:
                    errors.append(str(e))
                finally:
                    s.close()
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=pay_thread)
        t2 = threading.Thread(target=pay_thread)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # One may have succeeded, one may have failed (SQLite locking is OK)
        # Critical assertion: no overpayment occurred
        check_s = Sess()
        repo = SQLAlchemyPaymentRepository(check_s)
        total = repo.total_paid_for_order("ORD001")
        assert total <= Decimal("100.00"), f"Overpayment detected: {total}"
        check_s.close()
        shared_engine.dispose()


# ═══════════════════════════════════════════════════════════
# 9. REFUND
# ═══════════════════════════════════════════════════════════

class TestRefund:
    def test_refund_payment(self, db):
        _seed_order(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)
        CreateReceivableUseCase(recv_repo, ledger_repo).execute(
            "ORD001", "000001", Decimal("100.00"))

        pay_repo = SQLAlchemyPaymentRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        uc = RegisterPaymentUseCase(pay_repo, recv_repo, cash_repo, ledger_repo)
        result = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("100.00"), "method": "CASH"
        })

        refund_uc = RefundPaymentUseCase(pay_repo, recv_repo, cash_repo, ledger_repo)
        refund_result = refund_uc.execute(result["payment"].id, "Customer request")

        assert refund_result["payment"].status == PaymentStatus.REFUNDED

    def test_double_refund_idempotent(self, db):
        _seed_order(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)
        CreateReceivableUseCase(recv_repo, ledger_repo).execute(
            "ORD001", "000001", Decimal("100.00"))

        pay_repo = SQLAlchemyPaymentRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        uc = RegisterPaymentUseCase(pay_repo, recv_repo, cash_repo, ledger_repo)
        result = uc.execute({
            "order_codigo": "ORD001", "amount": Decimal("100.00"), "method": "CASH"
        })

        refund_uc = RefundPaymentUseCase(pay_repo, recv_repo, cash_repo, ledger_repo)
        refund_uc.execute(result["payment"].id)
        r2 = refund_uc.execute(result["payment"].id)
        assert r2["status"] == "already_refunded"


# ═══════════════════════════════════════════════════════════
# 10. DATABASE CONSTRAINTS
# ═══════════════════════════════════════════════════════════

class TestDatabaseConstraints:
    def test_payment_decimal_in_db(self, db):
        """Payment stores NUMERIC(10,2) not float."""
        _seed_order(db)
        repo = SQLAlchemyPaymentRepository(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        CreateReceivableUseCase(recv_repo, SQLAlchemyFinancialLedgerRepository(db)).execute(
            "ORD001", "000001", Decimal("100.00"))
        uc = RegisterPaymentUseCase(repo, recv_repo,
            SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db))
        r = uc.execute({"order_codigo": "ORD001", "amount": Decimal("99.99"), "method": "CASH"})

        model = db.query(PaymentModel).filter(PaymentModel.id == r["payment"].id).first()
        assert type(model.amount).__name__ == "Decimal"

    def test_expense_decimal_in_db(self, db):
        repo = SQLAlchemyExpenseRepository(db)
        uc = RegisterExpenseUseCase(repo,
            SQLAlchemyCashMovementRepository(db),
            SQLAlchemyFinancialLedgerRepository(db))
        r = uc.execute({"description": "Test", "amount": Decimal("42.50")})
        model = db.query(ExpenseModel).filter(ExpenseModel.id == r["expense"].id).first()
        assert type(model.amount).__name__ == "Decimal"

    def test_payment_unique_idempotency_key(self, db):
        """UNIQUE(idempotency_key) enforced."""
        _seed_order(db)
        repo = SQLAlchemyPaymentRepository(db)
        repo.create(Payment(
            order_codigo="ORD001", amount=Decimal("10.00"),
            method=PaymentMethod.CASH, status=PaymentStatus.PAID,
            idempotency_key="dup-key-001",
        ))
        with pytest.raises(Exception):
            repo.create(Payment(
                order_codigo="ORD001", amount=Decimal("20.00"),
                method=PaymentMethod.CASH, status=PaymentStatus.PAID,
                idempotency_key="dup-key-001",
            ))
            db.commit()


# ═══════════════════════════════════════════════════════════
# 11. FRESH DATABASE E2E
# ═══════════════════════════════════════════════════════════

class TestFreshDatabaseE2E:
    def test_full_flow(self, db):
        """Customer → Order → Payment → Receivable → Cash → Ledger."""
        # 1. Customer
        db.add(ClientModel(
            codigo="C001", nome="João", telefone="11988887777",
            rua="Rua B", numero="42", bairro="Vila",
        ))
        db.add(ProductModel(
            codigo="GAS13", nome="GLP P13", tipo="GAS", preco=120.0, estoque=0,
        ))
        db.commit()

        # 2. Order
        db.add(OrderModel(
            codigo="O001", client_codigo="C001",
            subtotal=120.0, delivery_fee=10.0, discount=0.0,
            total=130.0, payment_method="PIX",
            payment_status="PENDING", status="CONFIRMED",
            source="MANUAL", address_snapshot="Rua B, 42",
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        db.commit()

        # 3. Receivable
        recv_repo = SQLAlchemyReceivableRepository(db)
        ledger = SQLAlchemyFinancialLedgerRepository(db)
        r = CreateReceivableUseCase(recv_repo, ledger).execute(
            "O001", "C001", Decimal("130.00"))
        assert r.status == ReceivableStatus.OPEN

        # 4. Payment (partial)
        pay_repo = SQLAlchemyPaymentRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        uc = RegisterPaymentUseCase(pay_repo, recv_repo, cash_repo, ledger)
        result = uc.execute({
            "order_codigo": "O001", "amount": Decimal("80.00"),
            "method": "PIX",
        })
        assert result["receivable"].status == ReceivableStatus.PARTIAL
        assert result["receivable"].remaining_amount == Decimal("50.00")

        # 5. Cash balance
        balance = cash_repo.current_balance()
        assert balance == Decimal("80.00")

        # 6. Second payment
        result2 = uc.execute({
            "order_codigo": "O001", "amount": Decimal("50.00"),
            "method": "CASH",
        })
        assert result2["receivable"].status == ReceivableStatus.PAID
        assert cash_repo.current_balance() == Decimal("130.00")

        # 7. Ledger has entries
        entries, total = ledger.list_all()
        assert total >= 2


# ═══════════════════════════════════════════════════════════
# 12. REPORTS
# ═══════════════════════════════════════════════════════════

class TestReports:
    def test_daily_summary(self, db):
        _seed_order(db)
        recv_repo = SQLAlchemyReceivableRepository(db)
        ledger_repo = SQLAlchemyFinancialLedgerRepository(db)
        CreateReceivableUseCase(recv_repo, ledger_repo).execute(
            "ORD001", "000001", Decimal("100.00"))

        pay_repo = SQLAlchemyPaymentRepository(db)
        cash_repo = SQLAlchemyCashMovementRepository(db)
        RegisterPaymentUseCase(pay_repo, recv_repo, cash_repo, ledger_repo).execute({
            "order_codigo": "ORD001", "amount": Decimal("100.00"), "method": "CASH"
        })

        exp_repo = SQLAlchemyExpenseRepository(db)
        RegisterExpenseUseCase(exp_repo, cash_repo, ledger_repo).execute({
            "description": "Fuel", "amount": Decimal("30.00"), "category": "FUEL"
        })

        uc = FinancialReportsUseCase(pay_repo, recv_repo, exp_repo, cash_repo)
        report = uc.daily_summary(datetime.utcnow())
        assert report["total_receipts"] == Decimal("100.00")
        assert report["total_expenses"] == Decimal("30.00")
        assert report["net_result"] == Decimal("70.00")
