"""
Client API Routes — Endpoints REST para clientes.

FASE 6: Adicionado search, pagination, Customer 360 e CRM.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.application.client.use_cases import (
    CreateClientUseCase,
    GetClientUseCase,
    ListClientsUseCase,
    UpdateClientUseCase,
    DisableClientUseCase,
    Customer360UseCase,
)
from app.presentation.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientListResponse,
    Customer360Response,
)


router = APIRouter(
    prefix="/clients",
    tags=["Clients"]
)


def _get_repository(db: Session = Depends(get_db)):
    return SQLAlchemyClientRepository(db)


@router.post("/", response_model=ClientResponse)
def create_client(
    client: ClientCreate,
    repository: SQLAlchemyClientRepository = Depends(_get_repository)
):
    use_case = CreateClientUseCase(repository)
    try:
        return use_case.execute(client.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/", response_model=ClientListResponse)
def list_clients(
    q: Optional[str] = Query(default=None, description="Busca por nome, código, telefone ou bairro"),
    tipo: Optional[str] = Query(default=None, description="Filtrar por tipo"),
    ativo: Optional[bool] = Query(default=None, description="Filtrar por status ativo"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    repository: SQLAlchemyClientRepository = Depends(_get_repository)
):
    use_case = ListClientsUseCase(repository)
    return use_case.execute(
        query=q or "",
        tipo=tipo,
        ativo=ativo,
        page=page,
        page_size=page_size
    )


@router.get("/legacy", response_model=list[ClientResponse])
def list_clients_legacy(
    repository: SQLAlchemyClientRepository = Depends(_get_repository)
):
    """Legacy endpoint — retorna todos os clientes ativos sem paginação."""
    use_case = ListClientsUseCase(repository)
    result = use_case.execute()
    return result["items"]


@router.get("/{codigo}", response_model=ClientResponse)
def get_client(
    codigo: str,
    repository: SQLAlchemyClientRepository = Depends(_get_repository)
):
    use_case = GetClientUseCase(repository)
    client = use_case.execute(codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.get("/{codigo}/360", response_model=Customer360Response)
def get_customer_360(
    codigo: str,
    db: Session = Depends(get_db)
):
    """Customer 360 — visão consolidada com métricas CRM."""
    client_repo = SQLAlchemyClientRepository(db)
    order_repo = SQLAlchemyOrderRepository(db)
    use_case = Customer360UseCase(client_repo, order_repo)
    result = use_case.execute(codigo)
    if not result:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return result


@router.get("/{codigo}/orders", response_model=list)
def get_customer_orders(
    codigo: str,
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    db: Session = Depends(get_db)
):
    """Lista pedidos do cliente."""
    # Verify client exists
    client = repository.buscar_por_codigo(codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    order_repo = SQLAlchemyOrderRepository(db)
    orders = order_repo.get_customer_orders(codigo)
    return orders


@router.put("/{codigo}", response_model=ClientResponse)
def update_client(
    codigo: str,
    data: ClientUpdate,
    repository: SQLAlchemyClientRepository = Depends(_get_repository)
):
    use_case = UpdateClientUseCase(repository)
    try:
        client = use_case.execute(codigo, data.model_dump(exclude_unset=True))
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        return client
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/{codigo}/disable", response_model=ClientResponse)
def disable_client(
    codigo: str,
    repository: SQLAlchemyClientRepository = Depends(_get_repository)
):
    use_case = DisableClientUseCase(repository)
    client = use_case.execute(codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client
