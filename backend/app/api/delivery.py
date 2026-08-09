from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.delivery_driver import DeliveryDriverCreate, DeliveryDriverResponse
from app.schemas.pagination import Page
from app.services.delivery_driver_service import DeliveryDriverService

router = APIRouter(
    prefix="/delivery-drivers",
    tags=["Delivery Drivers"],
)


@router.post("/", response_model=DeliveryDriverResponse)
def create_driver(driver: DeliveryDriverCreate, db: Session = Depends(get_db)):
    return DeliveryDriverService.create(db, driver)


@router.get("/", response_model=Page[DeliveryDriverResponse])
def list_drivers(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = DeliveryDriverService.get_all(db, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=DeliveryDriverResponse)
def get_driver(codigo: str, db: Session = Depends(get_db)):
    driver = DeliveryDriverService.get_by_code(db, codigo)
    if not driver:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    return driver


@router.patch("/{codigo}/disable", response_model=DeliveryDriverResponse)
def disable_driver(codigo: str, db: Session = Depends(get_db)):
    driver = DeliveryDriverService.disable(db, codigo)
    if not driver:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    return driver
