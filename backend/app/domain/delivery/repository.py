"""
DeliveryDriver Repository Interface — Interface de repositório do Entregador.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from app.domain.delivery.entity import DeliveryDriver


class DeliveryDriverRepository(ABC):
    """Interface abstrata para repositório de entregadores."""

    @abstractmethod
    def criar(self, driver: DeliveryDriver) -> DeliveryDriver:
        """Cria um novo entregador no banco."""
        ...

    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[DeliveryDriver]:
        """Busca um entregador pelo código único."""
        ...

    @abstractmethod
    def listar_todos(self) -> List[DeliveryDriver]:
        """Lista todos os entregadores ativos."""
        ...

    @abstractmethod
    def desativar(self, codigo: str) -> Optional[DeliveryDriver]:
        """Desativa um entregador (soft delete)."""
        ...

    @abstractmethod
    def proximo_codigo(self) -> str:
        """Gera o próximo código sequencial para o entregador."""
        ...
