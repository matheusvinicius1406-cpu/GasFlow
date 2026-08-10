from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import ACCESS_TOKEN, decode_token
from app.database.dependencies import get_db
from app.models.company import Company
from app.models.user import ROLE_LEVELS, User, UserRole
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository

# auto_error=False para devolvermos 401 (via UnauthorizedError) em vez de 403.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Autenticação necessária")

    payload = decode_token(credentials.credentials, ACCESS_TOKEN)
    user = UserRepository(db).get(int(payload["sub"]))
    if not user or not user.ativo:
        raise UnauthorizedError("Usuário inválido ou inativo")
    return user


def get_current_company_id(user: User = Depends(get_current_user)) -> int:
    """Empresa (tenant) da requisição, derivada do usuário autenticado."""
    return user.company_id


def get_current_company(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Company:
    company = CompanyRepository(db).get(user.company_id)
    if not company:
        raise UnauthorizedError("Empresa não encontrada")
    return company


def require_role(minimum: UserRole):
    """Fábrica de dependência: exige papel >= `minimum` na hierarquia."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if ROLE_LEVELS.get(user.role, 0) < ROLE_LEVELS[minimum.value]:
            raise ForbiddenError("Permissão insuficiente para esta operação")
        return user

    return dependency
