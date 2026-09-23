"""
Delivery API Routes — Endpoints REST para entregadores.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import bcrypt

from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
from app.application.delivery.use_cases import (
    CreateDriverUseCase,
    DeleteDriverUseCase,
    DriverInRouteError,
    ListDriversUseCase,
    UpdateDriverUseCase,
)
from app.presentation.schemas.delivery import (
    DeliveryDriverCreate,
    DeliveryDriverResponse,
    DeliveryDriverUpdate,
)
from app.presentation.dependencies import get_tenant_context, require_admin
from app.domain.security.models import TenantContext


router = APIRouter(prefix="/delivery-drivers", tags=["Delivery Drivers"])


def _get_repository(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    return SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)


@router.post("/", response_model=DeliveryDriverResponse)
def create_driver(
    driver: DeliveryDriverCreate,
    repository: SQLAlchemyDeliveryDriverRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    data = driver.model_dump()
    # Check username uniqueness
    if driver.username:
        existing = repository.find_by_username(driver.username)
        if existing:
            raise HTTPException(409, detail="Username already exists")
        data["username"] = driver.username
    if driver.password:
        data["password_hash"] = bcrypt.hashpw(driver.password.encode(), bcrypt.gensalt()).decode()
    use_case = CreateDriverUseCase(repository)
    return use_case.execute(data)


@router.get("/", response_model=list[DeliveryDriverResponse])
def list_drivers(
    repository: SQLAlchemyDeliveryDriverRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = ListDriversUseCase(repository)
    return use_case.execute()


@router.get("/{codigo}", response_model=DeliveryDriverResponse)
def get_driver(
    codigo: str,
    repository: SQLAlchemyDeliveryDriverRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Retrato do entregador — mesmos campos que o `PUT` devolve.

    Antes devolvia a entidade de domínio, que não tem `document`/`vehicle_id`/
    `status`: a tela de edição lia o registro e **perdia** esses campos. Lendo do
    model, o `GET` e o `PUT` falam o mesmo contrato.
    """
    snapshot = repository.snapshot(codigo)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    return snapshot


@router.put("/{codigo}", response_model=DeliveryDriverResponse)
def update_driver(
    codigo: str,
    body: DeliveryDriverUpdate,
    repository: SQLAlchemyDeliveryDriverRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(require_admin),
):
    """Edita os campos editáveis do entregador (\u00e1rea admin).

    `codigo` vem só pela URL e é **imutável** \u2014 o schema rejeita o campo no
    corpo com 422 (ele é a identidade gravada em `delivery_records`,
    `driver_locations` e no histórico).

    O escopo é o tenant do contexto: entregador de outro tenant responde **404**,
    nunca 403, para não vazar a existência do registro.
    """
    updated = UpdateDriverUseCase(repository).execute(codigo, body.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Entregador n\u00e3o encontrado")
    return updated


@router.patch("/{codigo}/disable", response_model=DeliveryDriverResponse)
def disable_driver(
    codigo: str,
    repository: SQLAlchemyDeliveryDriverRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(require_admin),
):
    """Inativa o entregador \u2014 **alias** de `DELETE /admin/drivers/{id}`.

    Antes só derrubava `ativo`: ficavam dois "excluir" com efeitos diferentes
    (um matava sessão e link público, o outro não). Agora delega ao
    `DeleteDriverUseCase`, a mesma implementação do admin.
    """
    return _soft_delete(repository.db, ctx, codigo, repository)


def _soft_delete(db, ctx: TenantContext, codigo: str, repository: SQLAlchemyDeliveryDriverRepository):
    """Traduz o resultado do `DeleteDriverUseCase` para HTTP.

    A regra vive no use case; aqui só o mapeamento: em rota → 409, inexistente
    → 404, resto → o retrato já desativado.
    """
    try:
        result = DeleteDriverUseCase(db, ctx.tenant_id, actor_id=ctx.user_id or "").execute(codigo)
    except DriverInRouteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Entregador n\u00e3o encontrado")
    return repository.snapshot(codigo)
