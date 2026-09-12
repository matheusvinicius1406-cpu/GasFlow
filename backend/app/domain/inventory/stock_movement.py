"""
StockMovement Domain Entity — Entidade de domínio do Movimento de Estoque.

Regras de Negócio:
- Cada movimento é imutável após criação (histórico)
- Movimento registra: produto, tipo, quantidade, motivo, referência, saldos
- quantity é sempre positivo; o tipo indica direção (ENTRY = +, SALE = -)
- balance_before e balance_after são calculados pelo backend
- reference_type + reference_id permitem rastreamento (ex: ORDER, ADJUSTMENT)
- Um erro de estoque é corrigido com um NOVO movimento, nunca editando o histórico
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class MovementType(str, Enum):
    """Tipos de movimentação de estoque."""

    ENTRY = "ENTRY"  # Compra / reposição
    SALE = "SALE"  # Baixa por pedido
    ADJUSTMENT = "ADJUSTMENT"  # Ajuste de inventário (contagem física)
    LOSS = "LOSS"  # Perda / quebra
    RETURN = "RETURN"  # Devolução (cancelamento de pedido)
    INITIAL_BALANCE = "INITIAL_BALANCE"  # Saldo inicial (migração)
    # P0 (Decisão B2): troca física cheio→vazio na entrega DELIVERED.
    # Não altera `quantity` (total) — só a composição: empty += qty.
    DELIVERY_EXCHANGE = "DELIVERY_EXCHANGE"


@dataclass
class StockMovement:
    """Entidade de domínio do Movimento de Estoque."""

    id: Optional[int]
    product_codigo: str
    type: MovementType
    quantity: int  # Sempre positivo — o tipo indica direção
    reason: str

    reference_type: Optional[str] = None  # "ORDER", "ADJUSTMENT", etc.
    reference_id: Optional[str] = None  # código do pedido, etc.

    balance_before: int = 0
    balance_after: int = 0

    created_at: Optional[datetime] = None
    created_by: Optional[str] = None  # Placeholder — auth não existe ainda

    def __post_init__(self):
        """Validações de negócio após construção."""
        if not self.product_codigo:
            raise ValueError("product_codigo é obrigatório")
        if self.quantity < 0:
            raise ValueError("quantity não pode ser negativo")
        if self.quantity == 0 and self.type != MovementType.ADJUSTMENT:
            raise ValueError("quantity deve ser maior que 0 para movimentos não-ajuste")
        if not self.reason or not self.reason.strip():
            raise ValueError("reason é obrigatório")

    @property
    def direction(self) -> int:
        """Retorna +1 para entradas, -1 para saídas."""
        if self.type in (MovementType.ENTRY, MovementType.RETURN, MovementType.INITIAL_BALANCE):
            return 1
        if self.type in (MovementType.SALE, MovementType.LOSS):
            return -1
        # ADJUSTMENT pode ser positivo ou negativo — usar signed_quantity
        return 0

    @property
    def signed_quantity(self) -> int:
        """Quantidade com sinal: positivo para entradas, negativo para saídas."""
        if self.type in (MovementType.ENTRY, MovementType.RETURN, MovementType.INITIAL_BALANCE):
            return self.quantity
        if self.type in (MovementType.SALE, MovementType.LOSS):
            return -self.quantity
        # ADJUSTMENT: quantity é o delta (pode ser positivo ou negativo no input)
        # Mas no modelo armazenamos como positivo e usamos um campo separado
        # Para simplificar: adjustments são tratados no use case
        return self.quantity

    @property
    def summary(self) -> str:
        """Resumo do movimento para exibição."""
        sign = "+" if self.direction >= 0 else "-"
        ref = f" ({self.reference_type} #{self.reference_id})" if self.reference_id else ""
        return f"{self.type.value} {sign}{self.quantity} [{self.product_codigo}]{ref}"
