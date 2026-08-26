"""
Order Repository Interface — Interface de repositório do Pedido.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from app.domain.order.entity import Order, OrderStatus


class OrderRepository(ABC):
    """Interface abstrata para repositório de pedidos."""

    @abstractmethod
    def criar(self, order: Order) -> Order:
        """Cria um novo pedido no banco."""
        ...

    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[Order]:
        """Busca um pedido pelo código único."""
        ...

    @abstractmethod
    def listar_todos(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """Lista todos os pedidos, opcionalmente filtrando por status."""
        ...

    @abstractmethod
    def atualizar_status(self, codigo: str, status: OrderStatus) -> Optional[Order]:
        """Atualiza o status de um pedido."""
        ...

    @abstractmethod
    def atribuir_entregador(self, codigo: str, driver_codigo: str) -> Optional[Order]:
        """Atribui um entregador ao pedido."""
        ...

    @abstractmethod
    def proximo_codigo(self) -> str:
        """Gera o próximo código sequencial para o pedido."""
        ...
