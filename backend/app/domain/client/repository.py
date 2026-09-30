"""
Client Repository Interface — Interface de repositório do Cliente.

Define o contrato para acesso a dados do cliente, sem depender
de implementação específica (SQLAlchemy, MongoDB, etc).
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Tuple
from app.domain.client.entity import Client, normalize_phone


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

    def buscar_por_telefones(self, telefones: List[str]) -> Dict[str, Client]:
        """Busca vários clientes em UMA consulta, indexados por telefone normalizado.

        Otimização de importação em lote (§18 etapa 4): sem ela, importar N
        contatos custa N SELECTs. Implementações que não souberem fazer isso
        em uma consulta herdam o fallback linha a linha abaixo — o resultado
        é o mesmo, só mais lento.
        """
        found: Dict[str, Client] = {}
        for telefone in telefones:
            client = self.buscar_por_telefone(telefone)
            if client:
                found[normalize_phone(telefone)] = client
        return found

    def salvar_lote(self, criar: List[Client], atualizar: List[Client]) -> None:
        """Grava criações e atualizações em UMA transação.

        Fallback linha a linha para implementações sem bulk real: cada
        criação/atualização commita por conta própria, como antes.
        """
        for client in criar:
            self.criar(client)
        for client in atualizar:
            self.atualizar(client)

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
