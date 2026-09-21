"""B3 — par `deliver_stock_atomic` / `reverse_delivery_stock_atomic`.

Decisão B3(a) v3 (ver `docs/ROADMAP_BLOCKERS.md`): o **pedido** não toca
estoque; quem debita é a **entrega DELIVERED**. O caminho de ida já tem teste
em `test_delivery_debit.py`; o de volta não tinha nenhum — `reverse_delivery_stock_atomic`
não era chamado por teste algum, e o clamp de vazios nunca era exercitado de
fato (os testes existentes revertiam exatamente o que havia sido creditado, então
remover o `min()` não faria nenhum assert falhar).

Sem estes testes, um erro nesta conta vira estoque errado em produção sem
aparecer em lugar nenhum — é o tipo de número que só se descobre em inventário.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.repositories.product_model import ProductModel

PRODUCT = "P00001"
DELIVERY = "ent-1"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def repo(db):
    return SQLAlchemyInventoryRepository(db)


def _seed(db, *, full: int, empty: int, codigo: str = PRODUCT) -> None:
    """Produto com composição explícita. Invariante A: quantity == quantity_full."""
    db.add(ProductModel(codigo=codigo, nome="GLP P13", tipo="GAS", preco=100.0, estoque=full))
    db.add(InventoryModel(product_codigo=codigo, quantity=full, quantity_full=full, quantity_empty=empty))
    db.commit()


def _saldo(db, codigo: str = PRODUCT) -> tuple[int, int, int]:
    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == codigo).first()
    return inv.quantity, inv.quantity_full, inv.quantity_empty


def _movimentos(db, codigo: str = PRODUCT) -> list[StockMovementModel]:
    return db.query(StockMovementModel).filter(StockMovementModel.product_codigo == codigo).all()


def test_par_completo_devolve_o_estoque_ao_estado_inicial(db, repo):
    """Entrega + reversão da mesma entrega = estoque exatamente como estava.

    O round-trip é o teste que pega erro de sinal: se qualquer um dos dois
    lados trocar de direção, o saldo não fecha.
    """
    _seed(db, full=10, empty=3)
    antes = _saldo(db)

    repo.deliver_stock_atomic(PRODUCT, 4, reason="Venda na entrega", reference_type="DELIVERY", reference_id=DELIVERY)
    assert _saldo(db) == (6, 6, 7), "entrega: saem 4 cheios, entram 4 vazios"

    repo.reverse_delivery_stock_atomic(
        PRODUCT, 4, reason="Entrega cancelada", reference_type="DELIVERY", reference_id=DELIVERY
    )

    assert _saldo(db) == antes


def test_reverso_e_idempotente_por_referencia(db, repo):
    """Cancelar a mesma entrega duas vezes não credita estoque duas vezes.

    A idempotência é a constraint `uq_stock_movements_reference_product_type`;
    sem ela, um duplo clique em "cancelar" inflaria o estoque.
    """
    _seed(db, full=10, empty=2)
    repo.deliver_stock_atomic(PRODUCT, 3, reason="Venda na entrega", reference_type="DELIVERY", reference_id=DELIVERY)
    repo.reverse_delivery_stock_atomic(
        PRODUCT, 3, reason="Entrega cancelada", reference_type="DELIVERY", reference_id=DELIVERY
    )
    depois_da_primeira = _saldo(db)
    movimentos_antes = len(_movimentos(db))

    with pytest.raises(ValueError, match="Reversão já registrada"):
        repo.reverse_delivery_stock_atomic(
            PRODUCT, 3, reason="Entrega cancelada", reference_type="DELIVERY", reference_id=DELIVERY
        )

    assert _saldo(db) == depois_da_primeira, "a segunda tentativa não pode mexer no saldo"
    assert len(_movimentos(db)) == movimentos_antes, "nem registrar movimento novo"


def test_reverso_nao_deixa_vazios_negativos(db, repo):
    """Clamp: base sem vazios para receber a reversão não fica com saldo negativo.

    Cenário real: o cliente devolveu os vazios, mas a base já os despachou
    (perda, ajuste, coleta). A reversão da entrega devolve os cheios e remove
    vazios **até o que existe** — `quantity_empty` nunca vai abaixo de zero.
    """
    _seed(db, full=8, empty=0)
    repo.deliver_stock_atomic(PRODUCT, 4, reason="Venda na entrega", reference_type="DELIVERY", reference_id=DELIVERY)
    assert _saldo(db) == (4, 4, 4)

    # Os 4 vazios saíram da base antes do cancelamento (coleta/perda).
    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == PRODUCT).first()
    inv.quantity_empty = 0
    db.commit()

    repo.reverse_delivery_stock_atomic(
        PRODUCT, 4, reason="Entrega cancelada", reference_type="DELIVERY", reference_id=DELIVERY
    )

    quantity, full, empty = _saldo(db)
    assert empty == 0, "sem vazios para remover, o saldo fica em zero — nunca negativo"
    # Os cheios voltam por inteiro: a parte física que volta não depende dos vazios.
    assert (quantity, full) == (8, 8)

    reversal = [m for m in _movimentos(db) if m.type == "RETURN"][0]
    assert reversal.quantity_full_delta == 4
    assert reversal.quantity_empty_delta == 0, "o delta registra o que de fato saiu, não o que deveria"


def test_entrega_sem_estoque_nao_registra_movimento(db, repo):
    """Entregar mais do que existe falha e não deixa rastro pela metade.

    A baixa é um UPDATE atômico condicionado a `quantity >= :qty`; a validação
    do aplicativo não é o que protege, o `WHERE` é. Aqui se prova que a recusa
    não grava movimento nem muda saldo.
    """
    _seed(db, full=2, empty=0)

    with pytest.raises(ValueError, match="Estoque insuficiente"):
        repo.deliver_stock_atomic(
            PRODUCT, 5, reason="Venda na entrega", reference_type="DELIVERY", reference_id=DELIVERY
        )

    assert _saldo(db) == (2, 2, 0)
    assert _movimentos(db) == [], "recusa não pode registrar movimento de venda"


def test_entrega_e_reverso_movimentam_apenas_o_produto_alvo(db, repo):
    """A troca não vaza para outro produto (bug clássico de UPDATE sem filtro)."""
    _seed(db, full=10, empty=1, codigo=PRODUCT)
    _seed(db, full=5, empty=5, codigo="P00002")

    repo.deliver_stock_atomic(PRODUCT, 3, reason="Venda na entrega", reference_type="DELIVERY", reference_id=DELIVERY)
    repo.reverse_delivery_stock_atomic(
        PRODUCT, 3, reason="Entrega cancelada", reference_type="DELIVERY", reference_id=DELIVERY
    )

    assert _saldo(db, "P00002") == (5, 5, 5)
    assert _saldo(db, PRODUCT) == (10, 10, 1)
