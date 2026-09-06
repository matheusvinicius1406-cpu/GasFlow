"""
Client Use Cases — Casos de uso do Cliente.

FASE 6: Adicionado search, pagination, Customer 360 e CRM metrics.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from app.domain.client.entity import Client, normalize_phone
from app.domain.client.repository import ClientRepository


class CreateClientUseCase:
    """Caso de uso: Criar um novo cliente."""

    def __init__(self, repository: ClientRepository):
        self.repository = repository

    def execute(self, data: dict) -> Client:
        """Executa a criação de um cliente."""
        # Check for duplicate phone
        telefone = normalize_phone(data.get("telefone", ""))
        if telefone:
            existing = self.repository.buscar_por_telefone(telefone)
            if existing:
                raise ValueError(f"Já existe cliente com telefone {telefone} (código: {existing.codigo})")

        codigo = self.repository.proximo_codigo()

        client = Client(
            codigo=codigo,
            nome=data["nome"],
            telefone=data["telefone"],
            telefone_secundario=data.get("telefone_secundario"),
            rua=data["rua"],
            numero=data["numero"],
            complemento=data.get("complemento"),
            referencia=data.get("referencia"),
            bairro=data["bairro"],
            observacoes=data.get("observacoes"),
            tipo=data.get("tipo"),
            email=data.get("email"),
            ativo=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        return self.repository.criar(client)


class GetClientUseCase:
    """Caso de uso: Buscar cliente por código."""

    def __init__(self, repository: ClientRepository):
        self.repository = repository

    def execute(self, codigo: str) -> Optional[Client]:
        """Executa a busca de um cliente."""
        return self.repository.buscar_por_codigo(codigo)


class ListClientsUseCase:
    """Caso de uso: Listar clientes com busca e paginação."""

    def __init__(self, repository: ClientRepository):
        self.repository = repository

    def execute(
        self,
        query: str = "",
        tipo: Optional[str] = None,
        ativo: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Lista clientes com filtros e paginação."""
        items, total = self.repository.buscar(query=query, tipo=tipo, ativo=ativo, page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


class UpdateClientUseCase:
    """Caso de uso: Atualizar cliente."""

    def __init__(self, repository: ClientRepository):
        self.repository = repository

    def execute(self, codigo: str, data: dict) -> Optional[Client]:
        """Atualiza os dados de um cliente."""
        client = self.repository.buscar_por_codigo(codigo)
        if not client:
            return None

        client.nome = data.get("nome", client.nome)
        new_phone = data.get("telefone")
        if new_phone:
            normalized = normalize_phone(new_phone)
            # Check duplicate phone (excluding self)
            existing = self.repository.buscar_por_telefone(normalized)
            if existing and existing.codigo != client.codigo:
                raise ValueError(f"Já existe cliente com telefone {normalized} (código: {existing.codigo})")
            client.telefone = new_phone

        client.telefone_secundario = data.get("telefone_secundario", client.telefone_secundario)
        client.rua = data.get("rua", client.rua)
        client.numero = data.get("numero", client.numero)
        client.complemento = data.get("complemento", client.complemento)
        client.referencia = data.get("referencia", client.referencia)
        client.bairro = data.get("bairro", client.bairro)
        client.observacoes = data.get("observacoes", client.observacoes)
        client.tipo = data.get("tipo", client.tipo)
        client.email = data.get("email", client.email)
        client.updated_at = datetime.utcnow()

        return self.repository.atualizar(client)


class DisableClientUseCase:
    """Caso de uso: Desativar cliente."""

    def __init__(self, repository: ClientRepository):
        self.repository = repository

    def execute(self, codigo: str) -> Optional[Client]:
        """Desativa um cliente (soft delete)."""
        return self.repository.desativar(codigo)


class Customer360UseCase:
    """Caso de uso: Customer 360 — visão consolidada do cliente com métricas.

    FASE 8: Added financial metrics (outstanding_balance, pending_amount)
    derived from Payment + Receivable.
    """

    def __init__(
        self,
        client_repository: ClientRepository,
        order_repository=None,
        payment_repository=None,
        receivable_repository=None,
    ):
        self.client_repository = client_repository
        self.order_repository = order_repository
        self.payment_repository = payment_repository
        self.receivable_repository = receivable_repository

    def execute(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Retorna visão 360 do cliente com métricas derivadas dos pedidos."""
        client = self.client_repository.buscar_por_codigo(codigo)
        if not client:
            return None

        # Client data
        result = {
            "codigo": client.codigo,
            "nome": client.nome,
            "telefone": client.telefone,
            "telefone_secundario": client.telefone_secundario,
            "email": client.email,
            "tipo": client.tipo,
            "ativo": client.ativo,
            "rua": client.rua,
            "numero": client.numero,
            "bairro": client.bairro,
            "complemento": client.complemento,
            "referencia": client.referencia,
            "observacoes": client.observacoes,
            "created_at": client.created_at,
            "updated_at": client.updated_at,
            # CRM metrics (defaults)
            "total_orders": 0,
            "total_spent": 0.0,
            "average_ticket": 0.0,
            "first_order_at": None,
            "last_order_at": None,
            "days_since_last_order": None,
            "favorite_product": None,
            # FASE 8: Financial metrics (derived from Payment/Receivable)
            "paid_amount": 0.0,
            "outstanding_balance": 0.0,
            "pending_amount": 0.0,
        }

        # Calculate CRM metrics from orders if repository available
        if self.order_repository:
            metrics = self.order_repository.get_customer_metrics(codigo)
            result.update(metrics)

        # FASE 8: Calculate financial metrics (derived, not persisted)
        # Use receivable for outstanding (single query, no N+1)
        if self.receivable_repository:
            outstanding = self.receivable_repository.total_outstanding_for_customer(codigo)
            result["outstanding_balance"] = float(outstanding)
            result["pending_amount"] = float(outstanding)

        # paid_amount = total_spent - outstanding_balance
        # (derived from existing CRM total_spent + financial outstanding)
        total_spent = result.get("total_spent", 0.0)
        outstanding = result.get("outstanding_balance", 0.0)
        result["paid_amount"] = round(total_spent - outstanding, 2) if total_spent >= outstanding else 0.0

        return result
