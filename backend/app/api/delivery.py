from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, require_role
from app.database.dependencies import get_db
from app.models.user import UserRole
from app.schemas.delivery_driver import DeliveryDriverCreate, DeliveryDriverResponse
from app.schemas.pagination import Page
from app.services.delivery_driver_service import DeliveryDriverService

router = APIRouter(
    prefix="/delivery-drivers",
    tags=["Delivery Drivers"],
)

# Cadastro de entregadores exige ADMIN ou superior.
_admin = Depends(require_role(UserRole.ADMIN))


@router.post("/", response_model=DeliveryDriverResponse, dependencies=[_admin])
def create_driver(
    driver: DeliveryDriverCreate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    return DeliveryDriverService.create(db, company_id, driver)


@router.get("/", response_model=Page[DeliveryDriverResponse])
def list_drivers(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    items, total = DeliveryDriverService.get_all(db, company_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=DeliveryDriverResponse)
def get_driver(
    codigo: str,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    driver = DeliveryDriverService.get_by_code(db, company_id, codigo)
    if not driver:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    return driver


@router.patch("/{codigo}/disable", response_model=DeliveryDriverResponse, dependencies=[_admin])
def disable_driver(
    codigo: str,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    driver = DeliveryDriverService.disable(db, company_id, codigo)
    if not driver:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    return driver
