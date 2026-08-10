from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, require_role
from app.database.dependencies import get_db
from app.models.user import UserRole
from app.schemas.pagination import Page
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    # Gestão de usuários exige ADMIN ou superior.
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.post("/", response_model=UserResponse)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    return AuthService.create_user(db, company_id, data)


@router.get("/", response_model=Page[UserResponse])
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    company_id: int = Depends(get_current_company_id),
):
    items, total = AuthService.list_users(db, company_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
