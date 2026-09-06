"""
Inventory API Routes — Endpoints REST para inventário.

FASE 7: Inventory Core — stock management, movements, adjustments.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from sqlalchemy.orm import Session

from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
from app.application.inventory.use_cases import (
    GetInventoryUseCase,
    GetInventoryByProductUseCase,
    GetMovementsUseCase,
    AddStockUseCase,
    AdjustStockUseCase,
    LossStockUseCase,
    SetMinimumUseCase,
    ReconciliationService,
)
from app.presentation.schemas.inventory import (
    InventoryResponse,
    InventoryListResponse,
    StockMovementResponse,
    StockMovementListResponse,
    StockEntryRequest,
    StockAdjustRequest,
    StockLossRequest,
    SetMinimumRequest,
    StockOperationResponse,
    ReconciliationResponse,
)


router = APIRouter(prefix="/inventory", tags=["Inventory"])


def _get_inventory_repo(db: Session = Depends(get_db)):
    return SQLAlchemyInventoryRepository(db)


def _get_product_repo(db: Session = Depends(get_db)):
    return SQLAlchemyProductRepository(db)


# ── List Inventory ────────────────────────────────────────


@router.get("/", response_model=InventoryListResponse)
def list_inventory(
    stock_status: Optional[str] = Query(
        default=None, description="Filtrar por status: IN_STOCK, LOW_STOCK, OUT_OF_STOCK"
    ),
    product_type: Optional[str] = Query(default=None, description="Filtrar por tipo de produto"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Lista todos os itens de inventário com filtros."""
    inv_repo = SQLAlchemyInventoryRepository(db)
    prod_repo = SQLAlchemyProductRepository(db)

    use_case = GetInventoryUseCase(inv_repo)
    inventories = use_case.execute(stock_status=stock_status, product_type=product_type)

    # Enriquecer com dados do produto
    items = []
    for inv in inventories:
        product = prod_repo.buscar_por_codigo(inv.product_codigo)
        if product and product_type and product.tipo != product_type:
            continue
        items.append(
            InventoryResponse(
                product_codigo=inv.product_codigo,
                quantity=inv.quantity,
                minimum_quantity=inv.minimum_quantity,
                maximum_quantity=inv.maximum_quantity,
                stock_status=inv.stock_status.value,
                available_quantity=inv.available_quantity,
                updated_at=inv.updated_at,
            )
        )

    return InventoryListResponse(items=items, total=len(items))


# ── Get Inventory by Product ──────────────────────────────


@router.get("/{product_codigo}", response_model=InventoryResponse)
def get_inventory(
    product_codigo: str,
    repository: SQLAlchemyInventoryRepository = Depends(_get_inventory_repo),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Busca inventário de um produto específico."""
    use_case = GetInventoryByProductUseCase(repository)
    inventory = use_case.execute(product_codigo)
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    return InventoryResponse(
        product_codigo=inventory.product_codigo,
        quantity=inventory.quantity,
        minimum_quantity=inventory.minimum_quantity,
        maximum_quantity=inventory.maximum_quantity,
        stock_status=inventory.stock_status.value,
        available_quantity=inventory.available_quantity,
        updated_at=inventory.updated_at,
    )


# ── Get Movements by Product ──────────────────────────────


@router.get("/{product_codigo}/movements", response_model=StockMovementListResponse)
def get_movements(
    product_codigo: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    repository: SQLAlchemyInventoryRepository = Depends(_get_inventory_repo),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Lista movimentações de estoque de um produto."""
    use_case = GetMovementsUseCase(repository)
    result = use_case.execute(product_codigo, page=page, page_size=page_size)
    return StockMovementListResponse(
        items=[StockMovementResponse.model_validate(m) for m in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )


# ── Add Stock ─────────────────────────────────────────────


@router.post("/{product_codigo}/entries", response_model=StockOperationResponse)
def add_stock(
    product_codigo: str,
    data: StockEntryRequest,
    repository: SQLAlchemyInventoryRepository = Depends(_get_inventory_repo),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Registra entrada de estoque."""
    use_case = AddStockUseCase(repository)
    try:
        result = use_case.execute(
            product_codigo=product_codigo,
            quantity=data.quantity,
            reason=data.reason,
        )
        inv = result["inventory"]
        return StockOperationResponse(
            inventory=InventoryResponse(
                product_codigo=inv.product_codigo,
                quantity=inv.quantity,
                minimum_quantity=inv.minimum_quantity,
                maximum_quantity=inv.maximum_quantity,
                stock_status=inv.stock_status.value,
                available_quantity=inv.available_quantity,
                updated_at=inv.updated_at,
            ),
            movement=StockMovementResponse.model_validate(result["movement"]) if result["movement"] else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Adjust Stock ──────────────────────────────────────────


@router.post("/{product_codigo}/adjustments", response_model=StockOperationResponse)
def adjust_stock(
    product_codigo: str,
    data: StockAdjustRequest,
    repository: SQLAlchemyInventoryRepository = Depends(_get_inventory_repo),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Ajusta estoque (contagem física)."""
    use_case = AdjustStockUseCase(repository)
    try:
        result = use_case.execute(
            product_codigo=product_codigo,
            new_quantity=data.new_quantity,
            reason=data.reason,
        )
        inv = result["inventory"]
        return StockOperationResponse(
            inventory=InventoryResponse(
                product_codigo=inv.product_codigo,
                quantity=inv.quantity,
                minimum_quantity=inv.minimum_quantity,
                maximum_quantity=inv.maximum_quantity,
                stock_status=inv.stock_status.value,
                available_quantity=inv.available_quantity,
                updated_at=inv.updated_at,
            ),
            movement=StockMovementResponse.model_validate(result["movement"]) if result["movement"] else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Record Loss ──────────────────────────────────────────


@router.post("/{product_codigo}/losses", response_model=StockOperationResponse)
def record_loss(
    product_codigo: str,
    data: StockLossRequest,
    repository: SQLAlchemyInventoryRepository = Depends(_get_inventory_repo),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Registra perda de estoque."""
    use_case = LossStockUseCase(repository)
    try:
        result = use_case.execute(
            product_codigo=product_codigo,
            quantity=data.quantity,
            reason=data.reason,
        )
        inv = result["inventory"]
        return StockOperationResponse(
            inventory=InventoryResponse(
                product_codigo=inv.product_codigo,
                quantity=inv.quantity,
                minimum_quantity=inv.minimum_quantity,
                maximum_quantity=inv.maximum_quantity,
                stock_status=inv.stock_status.value,
                available_quantity=inv.available_quantity,
                updated_at=inv.updated_at,
            ),
            movement=StockMovementResponse.model_validate(result["movement"]) if result["movement"] else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Reconciliation ───────────────────────────────────────


@router.get("/reconciliation/check", response_model=list[ReconciliationResponse])
def reconciliation_check(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Verifica consistência entre inventory e ledger."""
    repo = SQLAlchemyInventoryRepository(db)
    service = ReconciliationService(repo)
    return service.check_all()


# ── Set Minimum ───────────────────────────────────────────


@router.patch("/{product_codigo}/minimum", response_model=InventoryResponse)
def set_minimum(
    product_codigo: str,
    data: SetMinimumRequest,
    repository: SQLAlchemyInventoryRepository = Depends(_get_inventory_repo),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Define estoque mínimo de um produto."""
    use_case = SetMinimumUseCase(repository)
    try:
        inventory = use_case.execute(product_codigo, data.minimum_quantity)
        if not inventory:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        return InventoryResponse(
            product_codigo=inventory.product_codigo,
            quantity=inventory.quantity,
            minimum_quantity=inventory.minimum_quantity,
            maximum_quantity=inventory.maximum_quantity,
            stock_status=inventory.stock_status.value,
            available_quantity=inventory.available_quantity,
            updated_at=inventory.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
