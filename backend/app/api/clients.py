from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from app.services.client_service import ClientService
from app.database.dependencies import get_db

router = APIRouter(
    prefix="/clients",
    tags=["Clients"]
)


@router.post("/", response_model=ClientResponse)
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    return ClientService.create(db, client)


@router.get("/", response_model=list[ClientResponse])
def list_clients(db: Session = Depends(get_db)):
    return ClientService.get_all(db)


@router.get("/{codigo}", response_model=ClientResponse)
def get_client(codigo: str, db: Session = Depends(get_db)):
    client = ClientService.get_by_code(db, codigo)

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado"
        )

    return client


@router.put("/{codigo}", response_model=ClientResponse)
def update_client(codigo: str, data: ClientUpdate, db: Session = Depends(get_db)):
    client = ClientService.update(db, codigo, data)

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado"
        )

    return client


@router.patch("/{codigo}/disable", response_model=ClientResponse)
def disable_client(codigo: str, db: Session = Depends(get_db)):
    client = ClientService.disable(db, codigo)

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado"
        )

    return client