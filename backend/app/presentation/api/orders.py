"""
Order API Routes — Endpoints REST para pedidos.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.infrastructure.repositories.order_item_repository import SQLAlchemyOrderItemRepository
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
from app.application.order.use_cases import (
    CreateOrderUseCase,
    GetOrderUseCase,
    ListOrdersUseCase,
    UpdateOrderStatusUseCase,
    AssignDriverUseCase,
)
from app.presentation.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderDetailResponse,
    OrderStatusUpdate,
    AssignDriverRequest,
)


router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


def _get_repositories(db: Session = Depends(get_db)):
    return {
        "order": SQLAlchemyOrderRepository(db),
        "order_item": SQLAlchemyOrderItemRepository(db),
        "client": SQLAlchemyClientRepository(db),
        "product": SQLAlchemyProductRepository(db),
        "delivery": SQLAlchemyDeliveryDriverRepository(db),
    }


@router.post("/", response_model=OrderResponse)
def create_order(
    order: OrderCreate,
    repos: dict = Depends(_get_repositories)
):
    try:
        use_case = CreateOrderUseCase(
            order_repo=repos["order"],
            order_item_repo=repos["order_item"],
            client_repo=repos["client"],
            product_repo=repos["product"],
        )
        return use_case.execute(order.model_dump())
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/", response_model=list[OrderResponse])
def list_orders(
    status: Optional[str] = Query(default=None),
    repos: dict = Depends(_get_repositories)
):
    use_case = ListOrdersUseCase(repos["order"])
    return use_case.execute(status=status)


@router.get("/{codigo}", response_model=OrderDetailResponse)
def get_order(
    codigo: str,
    repos: dict = Depends(_get_repositories)
):
    use_case = GetOrderUseCase(
        order_repo=repos["order"],
        order_item_repo=repos["order_item"],
    )
    order = use_case.execute(codigo)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.patch("/{codigo}/status", response_model=OrderResponse)
def update_order_status(
    codigo: str,
    data: OrderStatusUpdate,
    repos: dict = Depends(_get_repositories)
):
    try:
        use_case = UpdateOrderStatusUseCase(repos["order"])
        order = use_case.execute(codigo, data.status)
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        return order
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{codigo}/assign-driver", response_model=OrderResponse)
def assign_driver(
    codigo: str,
    data: AssignDriverRequest,
    repos: dict = Depends(_get_repositories)
):
    try:
        use_case = AssignDriverUseCase(
            order_repo=repos["order"],
            driver_repo=repos["delivery"],
        )
        order = use_case.execute(codigo, data.delivery_driver_codigo)
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        return order
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
