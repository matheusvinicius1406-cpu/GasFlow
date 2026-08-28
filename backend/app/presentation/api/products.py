"""
Product API Routes — Endpoints REST para produtos.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
from app.application.product.use_cases import (
    CreateProductUseCase,
    GetProductUseCase,
    ListProductsUseCase,
    UpdateProductUseCase,
    DisableProductUseCase,
)
from app.presentation.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


def _get_repository(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    return SQLAlchemyProductRepository(db, ctx.tenant_id)


@router.post("/", response_model=ProductResponse)
def create_product(
    product: ProductCreate,
    repository: SQLAlchemyProductRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = CreateProductUseCase(repository)
    return use_case.execute(product.model_dump())


@router.get("/", response_model=list[ProductResponse])
def list_products(
    repository: SQLAlchemyProductRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = ListProductsUseCase(repository)
    return use_case.execute()


@router.get("/{codigo}", response_model=ProductResponse)
def get_product(
    codigo: str,
    repository: SQLAlchemyProductRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = GetProductUseCase(repository)
    product = use_case.execute(codigo)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.put("/{codigo}", response_model=ProductResponse)
def update_product(
    codigo: str,
    data: ProductUpdate,
    repository: SQLAlchemyProductRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = UpdateProductUseCase(repository)
    product = use_case.execute(codigo, data.model_dump(exclude_unset=True))
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.patch("/{codigo}/disable", response_model=ProductResponse)
def disable_product(
    codigo: str,
    repository: SQLAlchemyProductRepository = Depends(_get_repository),
    ctx: TenantContext = Depends(get_tenant_context),
):
    use_case = DisableProductUseCase(repository)
    product = use_case.execute(codigo)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product
