from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, require_role
from app.database.dependencies import get_db
from app.models.user import UserRole
from app.schemas.pagination import Page
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services.product_service import ProductService

router = APIRouter(
    prefix="/products",
    tags=["Products"],
)

# Gestão de catálogo/estoque exige ADMIN ou superior.
_admin = Depends(require_role(UserRole.ADMIN))


@router.post("/", response_model=ProductResponse, dependencies=[_admin])
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    return ProductService.create(db, company_id, product)


@router.get("/", response_model=Page[ProductResponse])
def list_products(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    items, total = ProductService.get_all(db, company_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=ProductResponse)
def get_product(
    codigo: str,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    product = ProductService.get_by_code(db, company_id, codigo)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.put("/{codigo}", response_model=ProductResponse, dependencies=[_admin])
def update_product(
    codigo: str,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    product = ProductService.update(db, company_id, codigo, data)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.patch("/{codigo}/disable", response_model=ProductResponse, dependencies=[_admin])
def disable_product(
    codigo: str,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    product = ProductService.disable(db, company_id, codigo)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product
