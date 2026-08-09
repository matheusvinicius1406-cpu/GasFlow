from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.schemas.pagination import Page
from app.services.client_service import ClientService

router = APIRouter(
    prefix="/clients",
    tags=["Clients"],
)


@router.post("/", response_model=ClientResponse)
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    return ClientService.create(db, client)


@router.get("/", response_model=Page[ClientResponse])
def list_clients(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = ClientService.get_all(db, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{codigo}", response_model=ClientResponse)
def get_client(codigo: str, db: Session = Depends(get_db)):
    client = ClientService.get_by_code(db, codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.put("/{codigo}", response_model=ClientResponse)
def update_client(codigo: str, data: ClientUpdate, db: Session = Depends(get_db)):
    client = ClientService.update(db, codigo, data)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.patch("/{codigo}/disable", response_model=ClientResponse)
def disable_client(codigo: str, db: Session = Depends(get_db)):
    client = ClientService.disable(db, codigo)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client
