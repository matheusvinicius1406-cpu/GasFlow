from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.delivery_driver import DeliveryDriverCreate, DeliveryDriverResponse
from app.services.delivery_driver_service import DeliveryDriverService
from app.database.dependencies import get_db

router = APIRouter(
    prefix="/delivery-drivers",
    tags=["Delivery Drivers"]
)


@router.post("/", response_model=DeliveryDriverResponse)
def create_driver(driver: DeliveryDriverCreate, db: Session = Depends(get_db)):
    return DeliveryDriverService.create(db, driver)


@router.get("/", response_model=list[DeliveryDriverResponse])
def list_drivers(db: Session = Depends(get_db)):
    return DeliveryDriverService.get_all(db)


@router.get("/{codigo}", response_model=DeliveryDriverResponse)
def get_driver(codigo: str, db: Session = Depends(get_db)):
    driver = DeliveryDriverService.get_by_code(db, codigo)

    if not driver:
        raise HTTPException(
            status_code=404,
            detail="Entregador não encontrado"
        )

    return driver