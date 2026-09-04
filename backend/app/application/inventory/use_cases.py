"""
Inventory Use Cases — FASE 7.1

All operations delegate to atomic repository methods.
Single transaction: validate → update → move → commit.
On error: automatic ROLLBACK.
"""

from datetime import datetime
from typing import Optional, List
from app.domain.inventory.entity import Inventory
from app.domain.inventory.repository import InventoryRepository


class GetInventoryUseCase:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, stock_status: Optional[str] = None,
                product_type: Optional[str] = None) -> List[Inventory]:
        return self.repository.list_all(stock_status=stock_status, product_type=product_type)


class GetInventoryByProductUseCase:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str) -> Optional[Inventory]:
        return self.repository.get_by_product(product_codigo)


class GetMovementsUseCase:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str, page: int = 1,
                page_size: int = 20) -> dict:
        items, total = self.repository.get_movements(
            product_codigo, page=page, page_size=page_size
        )
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


class AddStockUseCase:
    """Entry of stock (purchase/restocking)."""

    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str, quantity: int,
                reason: str = "Entrada de estoque") -> dict:
        if quantity <= 0:
            raise ValueError("Quantidade deve ser maior que 0")
        return self.repository.add_stock_atomic(
            product_codigo=product_codigo,
            quantity=quantity,
            reason=reason,
        )


class RemoveStockUseCase:
    """Deduction of stock (manual sale)."""

    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str, quantity: int,
                reason: str = "Saída de estoque",
                reference_type: Optional[str] = None,
                reference_id: Optional[str] = None) -> dict:
        if quantity <= 0:
            raise ValueError("Quantidade deve ser maior que 0")
        return self.repository.deduct_stock_atomic(
            product_codigo=product_codigo,
            quantity=quantity,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
        )


class AdjustStockUseCase:
    """Physical count adjustment."""

    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str, new_quantity: int,
                reason: str = "Ajuste de inventário") -> dict:
        if new_quantity < 0:
            raise ValueError("Estoque ajustado não pode ser negativo")
        return self.repository.adjust_stock_atomic(
            product_codigo=product_codigo,
            new_quantity=new_quantity,
            reason=reason,
        )


class ReturnStockUseCase:
    """Return stock (order cancellation)."""

    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str, quantity: int,
                reason: str = "Devolução — cancelamento de pedido",
                reference_type: Optional[str] = None,
                reference_id: Optional[str] = None) -> dict:
        if quantity <= 0:
            raise ValueError("Quantidade deve ser maior que 0")
        return self.repository.return_stock_atomic(
            product_codigo=product_codigo,
            quantity=quantity,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
        )


class LossStockUseCase:
    """Record stock loss (damage/breakage)."""

    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str, quantity: int,
                reason: str = "Perda de estoque") -> dict:
        if quantity <= 0:
            raise ValueError("Quantidade deve ser maior que 0")
        return self.repository.deduct_stock_atomic(
            product_codigo=product_codigo,
            quantity=quantity,
            reason=reason,
            reference_type="LOSS",
            reference_id=f"LOSS_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        )


class SetMinimumUseCase:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def execute(self, product_codigo: str, minimum: int) -> Optional[Inventory]:
        if minimum < 0:
            raise ValueError("Estoque mínimo não pode ser negativo")
        inventory = self.repository.get_by_product(product_codigo)
        if not inventory:
            raise ValueError(f"Inventário não encontrado para produto {product_codigo}")
        return self.repository.update_minimum(product_codigo, minimum)


class ReconciliationService:
    """Detect inventory/ledger mismatches."""

    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def check_product(self, product_codigo: str) -> dict:
        """Reconcile inventory quantity with ledger balance."""
        inventory = self.repository.get_by_product(product_codigo)
        if not inventory:
            return {"product_codigo": product_codigo, "status": "NO_INVENTORY"}

        # Reconstruct balance from movements
        movements, _ = self.repository.get_movements(product_codigo, page=1, page_size=999999)
        ledger_balance = 0
        for m in movements:
            if m.type.value in ("ENTRY", "RETURN", "INITIAL_BALANCE"):
                ledger_balance += m.quantity
            elif m.type.value in ("SALE", "LOSS"):
                ledger_balance -= m.quantity
            elif m.type.value == "ADJUSTMENT":
                ledger_balance = m.balance_after

        match = inventory.quantity == ledger_balance
        return {
            "product_codigo": product_codigo,
            "inventory_quantity": inventory.quantity,
            "ledger_balance": ledger_balance,
            "match": match,
            "status": "MATCH" if match else "MISMATCH",
        }

    def check_all(self) -> list:
        """Check all products for mismatches."""
        inventories = self.repository.list_all()
        return [self.check_product(inv.product_codigo) for inv in inventories]
