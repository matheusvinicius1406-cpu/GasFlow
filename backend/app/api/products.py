from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.services.product_service import ProductService
from app.database.dependencies import get_db

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


@router.post("/", response_model=ProductResponse)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    return ProductService.create(db, product)


@router.get("/", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db)):
    return ProductService.get_all(db)


@router.get("/{codigo}", response_model=ProductResponse)
def get_product(codigo: str, db: Session = Depends(get_db)):
    product = ProductService.get_by_code(db, codigo)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Produto não encontrado"
        )

    return product


@router.put("/{codigo}", response_model=ProductResponse)
def update_product(codigo: str, data: ProductUpdate, db: Session = Depends(get_db)):
    product = ProductService.update(db, codigo, data)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Produto não encontrado"
        )

    return product


@router.patch("/{codigo}/disable", response_model=ProductResponse)
def disable_product(codigo: str, db: Session = Depends(get_db)):
    product = ProductService.disable(db, codigo)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Produto não encontrado"
        )

    return product