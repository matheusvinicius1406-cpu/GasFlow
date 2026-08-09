from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.pagination import Page
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services.product_service import ProductService

router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


@router.post("/", response_model=ProductResponse)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    return ProductService.create(db, product)


@router.get("/", response_model=Page[ProductResponse])
def list_products(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = ProductService.get_all(db, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=ProductResponse)
def get_product(codigo: str, db: Session = Depends(get_db)):
    product = ProductService.get_by_code(db, codigo)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.put("/{codigo}", response_model=ProductResponse)
def update_product(codigo: str, data: ProductUpdate, db: Session = Depends(get_db)):
    product = ProductService.update(db, codigo, data)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.patch("/{codigo}/disable", response_model=ProductResponse)
def disable_product(codigo: str, db: Session = Depends(get_db)):
    product = ProductService.disable(db, codigo)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product
