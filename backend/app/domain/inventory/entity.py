"""
Inventory Domain Entity — Entidade de domínio de Inventário.

Regras de Negócio:
- Inventory é a ÚNICA fonte de verdade para quantidade atual de estoque
- Product é responsável por: nome, tipo, preço, cadastro
- Inventory é responsável por: quantidade, mínimo, máximo, movimentações
- available = quantity (sem reserva por enquanto — simplificação)
- Stock status é DERIVADO (não armazenado): IN_STOCK / LOW_STOCK / OUT_OF_STOCK
- minimum_quantity permite classificar estoque baixo
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class StockStatus(str, Enum):
    """Status derivado do estoque (calculado, não armazenado)."""
    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


@dataclass
class Inventory:
    """Entidade de domínio de Inventário."""

    product_codigo: str
    quantity: int
    minimum_quantity: int = 0
    maximum_quantity: Optional[int] = None

    id: Optional[int] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validações de negócio após construção."""
        if not self.product_codigo:
            raise ValueError("product_codigo é obrigatório")
        if self.quantity < 0:
            raise ValueError("quantity não pode ser negativo")
        if self.minimum_quantity < 0:
            raise ValueError("minimum_quantity não pode ser negativo")
        if self.maximum_quantity is not None and self.maximum_quantity < self.minimum_quantity:
            raise ValueError("maximum_quantity não pode ser menor que minimum_quantity")

    @property
    def stock_status(self) -> StockStatus:
        """Calcula status do estoque (derivado, não armazenado)."""
        if self.quantity == 0:
            return StockStatus.OUT_OF_STOCK
        if self.quantity <= self.minimum_quantity:
            return StockStatus.LOW_STOCK
        return StockStatus.IN_STOCK

    @property
    def available_quantity(self) -> int:
        """Quantidade disponível (sem reserva por enquanto)."""
        return self.quantity

    def entry(self, quantity: int) -> int:
        """Registra entrada e retorna novo saldo."""
        if quantity <= 0:
            raise ValueError("Quantidade de entrada deve ser maior que 0")
        self.quantity += quantity
        self.updated_at = datetime.utcnow()
        return self.quantity

    def exit(self, quantity: int) -> int:
        """Registra saída e retorna novo saldo. Não permite saldo negativo."""
        if quantity <= 0:
            raise ValueError("Quantidade de saída deve ser maior que 0")
        if self.quantity < quantity:
            raise ValueError(
                f"Estoque insuficiente. Disponível: {self.quantity}, solicitado: {quantity}"
            )
        self.quantity -= quantity
        self.updated_at = datetime.utcnow()
        return self.quantity

    def adjust(self, new_quantity: int) -> int:
        """Ajusta estoque para quantidade específica (contagem física)."""
        if new_quantity < 0:
            raise ValueError("Estoque ajustado não pode ser negativo")
        old = self.quantity
        self.quantity = new_quantity
        self.updated_at = datetime.utcnow()
        return old  # Retorna saldo anterior

    def set_minimum(self, minimum: int) -> None:
        """Define quantidade mínima."""
        if minimum < 0:
            raise ValueError("minimum_quantity não pode ser negativo")
        self.minimum_quantity = minimum
