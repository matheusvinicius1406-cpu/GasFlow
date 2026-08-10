from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, require_role
from app.database.dependencies import get_db
from app.models.user import UserRole
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.schemas.pagination import Page
from app.services.client_service import ClientService

router = APIRouter(
    prefix="/clients",
    tags=["Clients"],
)

# Escrita de clientes exige ATTENDANT ou superior.
_attendant = Depends(require_role(UserRole.ATTENDANT))


@router.post("/", response_model=ClientResponse, dependencies=[_attendant])
def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    return ClientService.create(db, company_id, client)


@router.get("/", response_model=Page[ClientResponse])
def list_clients(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    items, total = ClientService.get_all(db, company_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=ClientResponse)
def get_client(
    codigo: str,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    client = ClientService.get_by_code(db, company_id, codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.put("/{codigo}", response_model=ClientResponse, dependencies=[_attendant])
def update_client(
    codigo: str,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    client = ClientService.update(db, company_id, codigo, data)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.patch("/{codigo}/disable", response_model=ClientResponse, dependencies=[_attendant])
def disable_client(
    codigo: str,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    client = ClientService.disable(db, company_id, codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client
