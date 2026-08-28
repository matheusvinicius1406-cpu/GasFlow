"""
Delivery API Routes — Endpoints REST para entregadores.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import hashlib

from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
from app.application.delivery.use_cases import (
    CreateDriverUseCase,
    GetDriverUseCase,
    ListDriversUseCase,
    DisableDriverUseCase,
)
from app.presentation.schemas.delivery import DeliveryDriverCreate, DeliveryDriverResponse
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext


router = APIRouter(
    prefix="/delivery-drivers",
    tags=["Delivery Drivers"]
)


def _get_repository(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    return SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)


@router.post("/", response_model=DeliveryDriverResponse)
def create_driver(
    driver: DeliveryDriverCreate,
    repository: SQLAlchemyDeliveryDriverRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    data = driver.model_dump()
    if driver.username:
        data["username"] = driver.username
    if driver.password:
        data["password_hash"] = hashlib.sha256(driver.password.encode()).hexdigest()
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
    use_case = GetDriverUseCase(repository)
    driver = use_case.execute(codigo)
    if not driver:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    return driver


@router.patch("/{codigo}/disable", response_model=DeliveryDriverResponse)
def disable_driver(
    codigo: str,
    repository: SQLAlchemyDeliveryDriverRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = DisableDriverUseCase(repository)
    driver = use_case.execute(codigo)
    if not driver:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    return driver
