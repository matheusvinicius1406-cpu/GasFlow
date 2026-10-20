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
from app.presentation.dependencies import get_tenant_context, require_permission
from app.domain.security.models import TenantContext


router = APIRouter(prefix="/clients", tags=["Clients"])


def _get_repository(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    return SQLAlchemyClientRepository(db, ctx.tenant_id)


@router.post("/", response_model=ClientResponse)
def create_client(
    client: ClientCreate,
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    _ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = CreateClientUseCase(repository)
    try:
        return use_case.execute(client.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/", response_model=ClientListResponse)
def list_clients(
    q: Optional[str] = Query(default=None, description="Busca por nome, código, telefone ou bairro"),
    tipo: Optional[str] = Query(default=None, description="Filtrar por tipo"),
    ativo: Optional[bool] = Query(default=None, description="Filtrar por status ativo"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    _ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = ListClientsUseCase(repository)
    return use_case.execute(query=q or "", tipo=tipo, ativo=ativo, page=page, page_size=page_size)


@router.get("/legacy", response_model=list[ClientResponse])
def list_clients_legacy(
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    _ctx: TenantContext = Depends(get_tenant_context),
):
    """Legacy endpoint — retorna todos os clientes ativos sem paginação."""
    use_case = ListClientsUseCase(repository)
    result = use_case.execute()
    return result["items"]


@router.get("/{codigo}", response_model=ClientResponse)
def get_client(
    codigo: str,
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    _ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = GetClientUseCase(repository)
    client = use_case.execute(codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.get("/{codigo}/360", response_model=Customer360Response)
def get_customer_360(
    codigo: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Customer 360 — visão consolidada com métricas CRM + financeiras."""
    client_repo = SQLAlchemyClientRepository(db, ctx.tenant_id)
    order_repo = SQLAlchemyOrderRepository(db, ctx.tenant_id)
    from app.infrastructure.repositories.financial_repositories import (
        SQLAlchemyReceivableRepository,
    )

    recv_repo = SQLAlchemyReceivableRepository(db, ctx.tenant_id)
    use_case = Customer360UseCase(client_repo, order_repo, receivable_repository=recv_repo)
    result = use_case.execute(codigo)
    if not result:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return result


@router.get("/{codigo}/orders", response_model=list)
def get_customer_orders(
    codigo: str,
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Lista pedidos do cliente."""
    client = repository.buscar_por_codigo(codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    order_repo = SQLAlchemyOrderRepository(db, ctx.tenant_id)
    orders = order_repo.get_customer_orders(codigo)
    return orders


@router.put("/{codigo}", response_model=ClientResponse)
def update_client(
    codigo: str,
    data: ClientUpdate,
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    _ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = UpdateClientUseCase(repository)
    try:
        client = use_case.execute(codigo, data.model_dump(exclude_unset=True))
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        return client
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.patch("/{codigo}/disable", response_model=ClientResponse)
def disable_client(
    codigo: str,
    repository: SQLAlchemyClientRepository = Depends(_get_repository),
    _ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = DisableClientUseCase(repository)
    client = use_case.execute(codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


# ── LGPD (D8) — portabilidade e exclusão/anonimização ──


def _audit_lgpd(db: Session, ctx: TenantContext, action: str, codigo: str, details: dict) -> None:
    """Auditoria da operação LGPD (rastreabilidade — art. 6, X). Só contagens, sem PII."""
    from app.infrastructure.repositories.auth_repository import SQLAlchemyAuditRepository

    SQLAlchemyAuditRepository(db).create(
        actor_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        action=action,
        resource="client",
        resource_id=codigo,
        details=details,
        platform="backend",
    )


@router.post("/{codigo}/export")
def export_client_data(
    codigo: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.write")),
):
    """LGPD art. 18, V — exportação (portabilidade) de todos os dados do titular.

    Permissão `customer.write` (admin/manager/operator): o pacote contém a PII
    completa do cliente — DRIVER e CUSTOMER ficam de fora. Registros de
    terceiros (ex.: quem o indicou) não são exportados.
    """
    from app.application.lgpd.use_cases import ExportClientDataUseCase

    repository = SQLAlchemyClientRepository(db, ctx.tenant_id)
    use_case = ExportClientDataUseCase(db, repository, ctx.tenant_id)
    result = use_case.execute(codigo)
    if result is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    counts = {key: len(value) for key, value in result.items() if isinstance(value, list)}
    _audit_lgpd(db, ctx, "LGPD_EXPORTED", codigo, {"secoes": counts})
    return result


@router.delete("/{codigo}/data")
def erase_client_data(
    codigo: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.*")),
):
    """LGPD art. 18, VI — anonimização da PII, preservando pedidos e fiscal.

    Permissão `customer.*` (admin/manager): a exclusão é destrutiva e
    irreversível; OPERATOR não pode executá-la. O `codigo` do cliente é
    mantido como chave estrutural — valores de pedidos/pagamentos ficam
    intactos. Idempotente.
    """
    from app.application.lgpd.use_cases import EraseClientDataUseCase

    repository = SQLAlchemyClientRepository(db, ctx.tenant_id)
    use_case = EraseClientDataUseCase(db, repository, ctx.tenant_id)
    result = use_case.execute(codigo)
    if result is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    _audit_lgpd(db, ctx, "LGPD_ERASED", codigo, {"registros_afetados": result["registros_afetados"]})
    return result
