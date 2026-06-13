from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.order import OrderCreate, OrderResponse, OrderStatusUpdate, AssignDriverRequest
from app.services.order_service import OrderService
from app.database.dependencies import get_db


router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


@router.post("/", response_model=OrderResponse)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    return OrderService.create(db, order)


@router.get("/", response_model=List[OrderResponse])
def list_orders(db: Session = Depends(get_db)):
    return OrderService.get_all(db)


@router.get("/{codigo}", response_model=OrderResponse)
def get_order(codigo: str, db: Session = Depends(get_db)):

    order = OrderService.get_by_code(db, codigo)

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado"
        )

    return order


@router.patch("/{codigo}/status", response_model=OrderResponse)
def update_order_status(codigo: str, data: OrderStatusUpdate, db: Session = Depends(get_db)):
    order = OrderService.update_status(db, codigo, data.status)

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado"
        )

    return order


@router.patch("/{codigo}/assign-driver", response_model=OrderResponse)
def assign_driver(codigo: str, data: AssignDriverRequest, db: Session = Depends(get_db)):
    try:
        order = OrderService.assign_driver(db, codigo, data.delivery_driver_codigo)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado"
        )

    return order