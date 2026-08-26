"""
Product Repository Interface — Interface de repositório do Produto.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from app.domain.product.entity import Product


class ProductRepository(ABC):
    """Interface abstrata para repositório de produtos."""

    @abstractmethod
    def criar(self, product: Product) -> Product:
        """Cria um novo produto no banco."""
        ...

    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[Product]:
        """Busca um produto pelo código único."""
        ...

    @abstractmethod
    def buscar_por_id(self, id: int) -> Optional[Product]:
        """Busca um produto pelo ID."""
        ...

    @abstractmethod
    def listar_todos(self) -> List[Product]:
        """Lista todos os produtos ativos."""
        ...

    @abstractmethod
    def atualizar(self, product: Product) -> Product:
        """Atualiza os dados de um produto."""
        ...

    @abstractmethod
    def desativar(self, codigo: str) -> Optional[Product]:
        """Desativa um produto (soft delete)."""
        ...

    @abstractmethod
    def proximo_codigo(self) -> str:
        """Gera o próximo código sequencial para o produto."""
        ...
