"""
Client Repository Interface — Interface de repositório do Cliente.

Define o contrato para acesso a dados do cliente, sem depender
de implementação específica (SQLAlchemy, MongoDB, etc).
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from app.domain.client.entity import Client


class ClientRepository(ABC):
    """Interface abstrata para repositório de clientes."""

    @abstractmethod
    def criar(self, client: Client) -> Client:
        """Cria um novo cliente no banco."""
        ...

    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[Client]:
        """Busca um cliente pelo código único."""
        ...

    @abstractmethod
    def buscar_por_id(self, id: int) -> Optional[Client]:
        """Busca um cliente pelo ID."""
        ...

    @abstractmethod
    def buscar_por_telefone(self, telefone: str) -> Optional[Client]:
        """Busca um cliente pelo telefone."""
        ...

    @abstractmethod
    def listar_todos(self) -> List[Client]:
        """Lista todos os clientes ativos."""
        ...

    @abstractmethod
    def buscar(
        self,
        query: str = "",
        tipo: Optional[str] = None,
        ativo: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Client], int]:
        """Busca clientes com filtros, paginação e contagem total."""
        ...

    @abstractmethod
    def atualizar(self, client: Client) -> Client:
        """Atualiza os dados de um cliente."""
        ...

    @abstractmethod
    def desativar(self, codigo: str) -> Optional[Client]:
        """Desativa um cliente (soft delete)."""
        ...

    @abstractmethod
    def proximo_codigo(self) -> str:
        """Gera o próximo código sequencial para o cliente."""
        ...
