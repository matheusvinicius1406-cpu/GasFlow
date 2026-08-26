"""
OrderItem Domain Entity — Entidade de negócio do Item do Pedido.

Regras de Negócio:
- Cada item pertence a um pedido
- O preço unitário é registrado no momento da criação (snapshot)
- O preço histórico NUNCA é alterado
- Subtotal = quantity × unit_price
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class OrderItem:
    """Entidade de domínio do Item do Pedido."""

    order_codigo: str
    product_codigo: str
    product_nome: str
    quantity: int
    unit_price: float

    id: Optional[int] = None
    subtotal: Optional[float] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Validações de negócio após construção."""
        if not self.order_codigo:
            raise ValueError("Código do pedido é obrigatório")
        if not self.product_codigo:
            raise ValueError("Código do produto é obrigatório")
        if not self.product_nome:
            raise ValueError("Nome do produto é obrigatório")
        if self.quantity <= 0:
            raise ValueError("Quantidade deve ser maior que 0")
        if self.unit_price < 0:
            raise ValueError("Preço unitário não pode ser negativo")

        # Calcula subtotal se não fornecido
        if self.subtotal is None:
            self.subtotal = self.quantity * self.unit_price

    @property
    def valor_total(self) -> float:
        """Retorna o valor total do item."""
        return self.quantity * self.unit_price
