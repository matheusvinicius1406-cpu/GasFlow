"""
OrderItem Repository Interface — Interface de repositório do Item do Pedido.
"""

from abc import ABC, abstractmethod
from typing import List
from app.domain.order_item.entity import OrderItem


class OrderItemRepository(ABC):
    """Interface abstrata para repositório de itens de pedido."""

    @abstractmethod
    def criar(self, item: OrderItem) -> OrderItem:
        """Cria um novo item no banco."""
        ...

    @abstractmethod
    def listar_por_pedido(self, order_codigo: str) -> List[OrderItem]:
        """Lista todos os itens de um pedido."""
        ...

    @abstractmethod
    def deletar_por_pedido(self, order_codigo: str) -> int:
        """Deleta todos os itens de um pedido (para recriação)."""
        ...
