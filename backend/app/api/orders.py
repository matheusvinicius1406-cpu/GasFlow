from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, require_role
from app.database.dependencies import get_db
from app.models.user import UserRole
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

# Operação de pedidos exige ATTENDANT ou superior.
_attendant = Depends(require_role(UserRole.ATTENDANT))


@router.post("/", response_model=OrderResponse, dependencies=[_attendant])
def create_order(
    order: OrderCreate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    # Erros de domínio são tratados pelo handler global (ver app.main).
    return OrderService.create(db, company_id, order)


@router.get("/", response_model=Page[OrderResponse])
def list_orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    items, total = OrderService.get_all(
        db, company_id, status=status, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=OrderResponse)
def get_order(
    codigo: str,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    order = OrderService.get_by_code(db, company_id, codigo)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.patch("/{codigo}/status", response_model=OrderResponse, dependencies=[_attendant])
def update_order_status(
    codigo: str,
    data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    order = OrderService.update_status(db, company_id, codigo, data.status)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.patch("/{codigo}/assign-driver", response_model=OrderResponse, dependencies=[_attendant])
def assign_driver(
    codigo: str,
    data: AssignDriverRequest,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    order = OrderService.assign_driver(db, company_id, codigo, data.delivery_driver_codigo)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order
