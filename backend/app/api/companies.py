from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_company
from app.models.company import Company
from app.schemas.company import CompanyResponse

router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)


@router.get("/me", response_model=CompanyResponse)
def get_my_company(company: Company = Depends(get_current_company)):
    """Retorna a empresa (depósito) do usuário autenticado.

    A criação de empresa é feita via `POST /auth/register` (cadastro self-serve).
    """
    return company
