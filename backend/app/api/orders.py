
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.order import (
    AssignDriverRequest,
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate,
)
from app.schemas.pagination import Page
from app.services.order_service import OrderService

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


@router.post("/", response_model=OrderResponse)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    # Erros de domínio são tratados pelo handler global (ver app.main).
    return OrderService.create(db, order)


@router.get("/", response_model=Page[OrderResponse])
def list_orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = OrderService.get_all(db, status=status, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=OrderResponse)
def get_order(codigo: str, db: Session = Depends(get_db)):
    order = OrderService.get_by_code(db, codigo)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.patch("/{codigo}/status", response_model=OrderResponse)
def update_order_status(codigo: str, data: OrderStatusUpdate, db: Session = Depends(get_db)):
    order = OrderService.update_status(db, codigo, data.status)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.patch("/{codigo}/assign-driver", response_model=OrderResponse)
def assign_driver(codigo: str, data: AssignDriverRequest, db: Session = Depends(get_db)):
    order = OrderService.assign_driver(db, codigo, data.delivery_driver_codigo)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order
