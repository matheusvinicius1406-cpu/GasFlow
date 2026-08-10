from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database.dependencies import get_db
from app.models.company import Company
from app.services.company_service import CompanyService


def get_current_company(
    x_company_id: str | None = Header(default=None, alias="X-Company-Id"),
    db: Session = Depends(get_db),
) -> Company:
    """Resolve a empresa (tenant) da requisição.

    - Com o header `X-Company-Id` (código da empresa): usa aquela empresa.
    - Sem o header: usa a empresa padrão (single-tenant / desenvolvimento).

    Na Fase 2 (auth) a empresa passará a vir do usuário autenticado; esta
    dependência é o único ponto a alterar.
    """
    if x_company_id:
        company = CompanyService.get_by_code(db, x_company_id)
        if not company or not company.ativo:
            raise NotFoundError("Empresa não encontrada ou inativa")
        return company

    return CompanyService.get_or_create_default(db)


def get_current_company_id(company: Company = Depends(get_current_company)) -> int:
    return company.id
