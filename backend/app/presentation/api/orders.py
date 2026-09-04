"""
Order API Routes — FASE 7.1

Passes inventory_repo to use cases for atomic stock operations.
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
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
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
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from app.domain.events.event_bus import (
    EventType,
    publish_order_event,
)


router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


def _get_repositories(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    return {
        "order": SQLAlchemyOrderRepository(db, ctx.tenant_id),
        "order_item": SQLAlchemyOrderItemRepository(db, ctx.tenant_id),
        "client": SQLAlchemyClientRepository(db, ctx.tenant_id),
        "product": SQLAlchemyProductRepository(db, ctx.tenant_id),
        "delivery": SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id),
        "inventory": SQLAlchemyInventoryRepository(db, ctx.tenant_id),
    }


@router.post("/", response_model=OrderResponse)
def create_order(
    order: OrderCreate,
    repos: dict = Depends(_get_repositories),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        use_case = CreateOrderUseCase(
            order_repo=repos["order"],
            order_item_repo=repos["order_item"],
            client_repo=repos["client"],
            product_repo=repos["product"],
            inventory_repo=repos["inventory"],
        )
        created = use_case.execute(order.model_dump())
        # Notify operators in realtime: new order appears on the dashboard.
        publish_order_event(
            EventType.ORDER_CREATED,
            created.codigo,
            ctx.tenant_id,
            data={
                "codigo": created.codigo,
                "status": created.status.value,
                "total": created.total,
                "client_codigo": created.client_codigo,
                "item_count": len(created.items) if created.items else 0,
            },
        )
        return created
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/", response_model=list[OrderResponse])
def list_orders(
    status: Optional[str] = Query(default=None),
    repos: dict = Depends(_get_repositories),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = ListOrdersUseCase(repos["order"])
    return use_case.execute(status=status)


@router.get("/{codigo}", response_model=OrderDetailResponse)
def get_order(
    codigo: str,
    repos: dict = Depends(_get_repositories),
    ctx: TenantContext = Depends(get_tenant_context),
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
    repos: dict = Depends(_get_repositories),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        use_case = UpdateOrderStatusUseCase(
            repository=repos["order"],
            inventory_repo=repos["inventory"],
            order_item_repo=repos["order_item"],
        )
        order = use_case.execute(codigo, data.status)
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        publish_order_event(
            EventType.ORDER_UPDATED,
            order.codigo,
            ctx.tenant_id,
            data={
                "codigo": order.codigo,
                "status": order.status.value,
                "total": order.total,
                "client_codigo": order.client_codigo,
            },
        )
        return order
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{codigo}/assign-driver", response_model=OrderResponse)
def assign_driver(
    codigo: str,
    data: AssignDriverRequest,
    repos: dict = Depends(_get_repositories),
    ctx: TenantContext = Depends(get_tenant_context),
):
    try:
        use_case = AssignDriverUseCase(
            order_repo=repos["order"],
            driver_repo=repos["delivery"],
        )
        order = use_case.execute(codigo, data.delivery_driver_codigo)
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        publish_order_event(
            EventType.ORDER_UPDATED,
            order.codigo,
            ctx.tenant_id,
            data={
                "codigo": order.codigo,
                "status": order.status.value,
                "delivery_driver_codigo": order.delivery_driver_codigo,
            },
        )
        return order
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
