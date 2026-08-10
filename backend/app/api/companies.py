from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.company import CompanyCreate, CompanyResponse
from app.schemas.pagination import Page
from app.services.company_service import CompanyService

router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)


@router.post("/", response_model=CompanyResponse)
def create_company(company: CompanyCreate, db: Session = Depends(get_db)):
    # Nota: operação administrativa. Será restrita a super-admin na Fase 2 (auth).
    return CompanyService.create(db, company)


@router.get("/", response_model=Page[CompanyResponse])
def list_companies(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = CompanyService.get_all(db, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=CompanyResponse)
def get_company(codigo: str, db: Session = Depends(get_db)):
    company = CompanyService.get_by_code(db, codigo)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company
