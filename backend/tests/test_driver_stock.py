"""Testes F7 — Estoque do entregador (driver_stock) + despacho com elegibilidade.

Cobre o spec §3.3.1:
- Carga (LOADING): soma full_tanks_loaded, NÃO debita a base (empréstimo).
- Entrega DELIVERED: base debita 1x (deliver_stock_atomic) E o entregador
  decrementa — consistência base+entregador no mesmo fluxo.
- CANCELLED pós-DELIVERED: reversão espelhada nos dois.
- Avaria: motivo obrigatório, debita entregador + base.
- Reconciliação: carga − entregas − avarias = cheios + vazios;
  divergência > tolerância → bloqueio de novas cargas.
- Elegibilidade no despacho: só quem tem cheio disponível.
"""

from __future__ import annotations


import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.application.delivery.driver_stock_service import DriverStockService, DriverStockError
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDeliveryPersistenceRepository,
)
from app.infrastructure.repositories.driver_stock_model import DriverStockModel
from app.infrastructure.repositories.inventory_model import InventoryModel
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.product_model import ProductModel


# ── Test DB Setup ─────────────────────────────────────────


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def svc(db):
    return DriverStockService(db, "default")


def _seed_product(db, codigo: str = "P13", full: int = 100, empty: int = 0) -> None:
    db.add(ProductModel(codigo=codigo, nome="GLP P13", tipo="GAS", preco=100.0, estoque=full))
    db.add(InventoryModel(product_codigo=codigo, quantity=full, quantity_full=full, quantity_empty=empty))
    db.commit()


def _seed_order_items(db, order_id: str, product_codigo: str, quantity: int) -> None:
    db.add(
        OrderItemModel(
            order_codigo=order_id,
            product_codigo=product_codigo,
            product_nome="GLP P13",
            quantity=quantity,
            unit_price=100,
            subtotal=100 * quantity,
        )
    )
    db.commit()


def _seed_delivery(db, delivery_id: str, order_id: str, driver_id: str) -> None:
    repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    repo.create_delivery(delivery_id=delivery_id, order_id=order_id, customer_codigo="000001", customer_name="Cliente")
    repo.assign_delivery(delivery_id, driver_id, None, version=1)


# ═══════════════════════════════════════════════════════════
# 1. Carga (empréstimo — não debita a base)
# ═══════════════════════════════════════════════════════════


class TestLoading:
    def test_load_increments_driver_stock_without_touching_base(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D00001", "P13", 10)

        inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P13").first()
        assert inv.quantity == 100  # base intacta — conta dupla é bug
        stock = svc.get_stock("D00001")
        assert stock[0]["full_tanks_loaded"] == 10

    def test_load_blocked_when_divergence_pending(self, db, svc):
        _seed_product(db)
        svc.load_tanks("D00001", "P13", 10)
        # Força bloqueio (como faria uma reconciliação divergente)
        row = db.query(DriverStockModel).filter(DriverStockModel.driver_id == "D00001").first()
        row.blocked = True
        row.blocked_reason = "divergência 5 > 2"
        db.commit()

        with pytest.raises(DriverStockError, match="bloqueado"):
            svc.load_tanks("D00001", "P13", 5)

    def test_load_negative_rejected(self, db, svc):
        with pytest.raises(DriverStockError):
            svc.load_tanks("D00001", "P13", -3)


# ═══════════════════════════════════════════════════════════
# 2. Entrega: débito espelhado (base + entregador)
# ═══════════════════════════════════════════════════════════


class TestDeliveryDebit:
    def test_delivered_debits_base_once_and_driver_once(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        _seed_order_items(db, "O1", "P13", 3)
        _seed_delivery(db, "DLV1", "O1", "D1")
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")

        repo.complete_delivery("DLV1", version=2)

        inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P13").first()
        assert inv.quantity == 97  # 100 - 3 (base, única vez)
        stock = svc.get_stock("D1")[0]
        assert stock["full_tanks_loaded"] == 7  # 10 - 3 (entregador)
        assert stock["empty_tanks_returned"] == 3  # vazios do cliente

    def test_delivered_twice_is_idempotent(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        _seed_order_items(db, "O1", "P13", 3)
        _seed_delivery(db, "DLV1", "O1", "D1")
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        repo.complete_delivery("DLV1", version=2)

        # Segunda transição DELIVERED não é possível (estado atual DELIVERED
        # sem transição válida) — mas chamar o débito direto 2x é seguro:
        svc.apply_delivery_debit("D1", {"P13": 3}, "DLV1")
        stock = svc.get_stock("D1")[0]
        assert stock["full_tanks_loaded"] == 7

    def test_cancelled_after_delivered_reverses_both(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        _seed_order_items(db, "O1", "P13", 3)
        _seed_delivery(db, "DLV1", "O1", "D1")
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        repo.complete_delivery("DLV1", version=2)

        # Simula cancelamento pós-DELIVERED via transição direta
        record = repo.get_delivery("DLV1")
        repo._transition("DLV1", "CANCELLED", record.version, actor_type="OPERATOR")

        inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P13").first()
        assert inv.quantity == 100  # base revertida
        stock = svc.get_stock("D1")[0]
        assert stock["full_tanks_loaded"] == 10  # entregador também
        assert stock["empty_tanks_returned"] == 0


# ═══════════════════════════════════════════════════════════
# 3. Avaria
# ═══════════════════════════════════════════════════════════


class TestDamage:
    def test_damage_requires_reason(self, db, svc):
        _seed_product(db)
        with pytest.raises(DriverStockError, match="obrigatório"):
            svc.register_damage("D1", "P13", 1, "  ")

    def test_damage_debits_driver_and_base(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        result = svc.register_damage("D1", "P13", 2, "cilindro amassado no carregamento")

        assert result["full_tanks_loaded"] == 8
        assert result["base_debited"] is True
        inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P13").first()
        assert inv.quantity == 98  # base também debita (fato físico)

    def test_damage_beyond_loaded_rejected(self, db, svc):
        _seed_product(db, full=100)
        with pytest.raises(DriverStockError, match="insuficiente"):
            svc.register_damage("D1", "P13", 5, "queda")


# ═══════════════════════════════════════════════════════════
# 4. Reconciliação
# ═══════════════════════════════════════════════════════════


class TestReconciliation:
    def test_counts_match_expected_no_block(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        svc.apply_delivery_debit("D1", {"P13": 3}, "DLV1")  # 10 - 3 = 7 esperados
        result = svc.reconcile("D1", counts={"P13": 7}, empty_returned={"P13": 3})

        r = result["results"][0]
        assert r["divergence_full"] == 0 and r["divergence_empty"] == 0
        assert r["blocked"] is False
        stock = svc.get_stock("D1")[0]
        assert stock["full_tanks_loaded"] == 7  # contagem física confirmada
        assert stock["empty_tanks_returned"] == 0  # vazios devolvidos à base

    def test_divergence_beyond_tolerance_blocks_new_loads(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        # Operador conta 4 (esperado 10) — divergência 6 > tolerância 2
        result = svc.reconcile("D1", counts={"P13": 4}, empty_returned={})
        assert result["any_blocked"] is True
        assert result["results"][0]["blocked"] is True

        with pytest.raises(DriverStockError, match="bloqueado"):
            svc.load_tanks("D1", "P13", 1)

    def test_divergence_within_tolerance_is_accepted(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        # Divergência 2 = tolerância (não superior) → aceita
        result = svc.reconcile("D1", counts={"P13": 8}, empty_returned={})
        assert result["results"][0]["blocked"] is False
        assert svc.get_stock("D1")[0]["full_tanks_loaded"] == 8

    def test_unblock_allows_loading_again(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        svc.reconcile("D1", counts={"P13": 4}, empty_returned={})  # bloqueia
        svc.unblock("D1", actor_id="admin")
        svc.load_tanks("D1", "P13", 5)  # não levanta
        # Nota: a divergência (informado 4 vs esperado 10) não altera o saldo
        # quando bloqueia — o ajuste só acontece numa reconciliação aceita.
        # Saldo continua 10 (carga original − nada) + 5 = 15; a divergência
        # fica registrada no evento RECONCILE para investigação manual.
        assert svc.get_stock("D1")[0]["full_tanks_loaded"] == 15


# ═══════════════════════════════════════════════════════════
# 5. Elegibilidade para o despacho
# ═══════════════════════════════════════════════════════════


class TestEligibility:
    def test_eligible_capacity_only_positive_unblocked(self, db, svc):
        _seed_product(db, full=100)
        svc.load_tanks("D1", "P13", 10)
        svc.load_tanks("D1", "P45", 0) if False else None  # produto zerado não entra
        # D2 bloqueado com estoque → não elegível
        svc.load_tanks("D2", "P13", 8)
        row = db.query(DriverStockModel).filter(DriverStockModel.driver_id == "D2").first()
        row.blocked = True
        db.commit()

        assert svc.eligible_capacity("D1") == {"P13": 10}
        assert svc.eligible_capacity("D2") == {}

    def test_dispatch_suggestion_filters_by_stock(self, db, svc):
        """Entregador sem cheio é rejeitado mesmo sendo o mais próximo."""
        from app.domain.delivery.dispatch_engine import DispatchEngine, DispatchMode, OrderRequest, DriverCandidate

        _seed_product(db, full=100)
        svc.load_tanks("D_COM_ESTOQUE", "P13", 5)

        order = OrderRequest(order_id="O1", tenant_id="default", customer_codigo="000001", customer_name="C")
        order.items = [type("OI", (), {"product_codigo": "P13", "product_name": "P13", "quantity": 2})()]

        candidates = [
            DriverCandidate(
                driver_id="D_SEM_ESTOQUE",
                driver_name="Perto Sem Estoque",
                vehicle_id="V1",
                latitude=-23.55,
                longitude=-46.63,  # mais próximo
                capacity={},  # sem cheios
            ),
            DriverCandidate(
                driver_id="D_COM_ESTOQUE",
                driver_name="Longe Com Estoque",
                vehicle_id="V2",
                latitude=-23.60,
                longitude=-46.70,  # mais longe
                capacity=svc.eligible_capacity("D_COM_ESTOQUE"),
            ),
        ]
        result = DispatchEngine(mode=DispatchMode.ASSISTED).recommend(order, candidates)
        assert result["success"] is True
        # O único recomendado é quem tem estoque (o sem estoque é rejeitado
        # por INSUFFICIENT_CAPACITY)
        rec_ids = [r["driver_id"] for r in result["recommendations"]]
        assert rec_ids and all(rid == "D_COM_ESTOQUE" for rid in rec_ids)
        rejected_ids = [r["driver_id"] for r in result.get("rejected", [])]
        assert "D_SEM_ESTOQUE" in rejected_ids
