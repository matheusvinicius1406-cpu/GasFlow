from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.client import ClientCreate
from app.services.client_service import ClientService
from app.database.dependencies import get_db

router = APIRouter(
    prefix="/clients",
    tags=["Clients"]
)


@router.post("/")
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    return ClientService.create(db, client)


@router.get("/")
def list_clients(db: Session = Depends(get_db)):
    return ClientService.get_all(db)


@router.get("/{codigo}")
def get_client(codigo: str, db: Session = Depends(get_db)):
    client = ClientService.get_by_code(db, codigo)

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado"
        )

    return client