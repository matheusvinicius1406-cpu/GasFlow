from fastapi import APIRouter, HTTPException

from app.schemas.client import ClientCreate
from app.services.client_service import ClientService

router = APIRouter(
    prefix="/clients",
    tags=["Clients"]
)


@router.post("/")
def create_client(client: ClientCreate):

    created = ClientService.create(client)

    return created


@router.get("/")
def list_clients():

    return ClientService.get_all()


@router.get("/{codigo}")
def get_client(codigo: str):

    client = ClientService.get_by_code(codigo)

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado"
        )

    return client