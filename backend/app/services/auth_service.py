from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import (
    REFRESH_TOKEN,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.company import Company
from app.models.user import User, UserRole
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository
from app.schemas.company import CompanyCreate
from app.services.company_service import CompanyService


class AuthService:

    @staticmethod
    def register(db: Session, data) -> tuple[User, str, str]:
        """Cadastro self-serve: cria empresa + usuário OWNER e emite tokens."""
        users = UserRepository(db)
        if users.get_by_email(data.email):
            raise ConflictError("Email já cadastrado")

        # Cria a empresa do novo cliente (depósito).
        company = CompanyService.create(
            db,
            CompanyCreate(nome=data.empresa_nome, responsavel=data.nome, plano="FREE"),
        )

        user = User(
            company_id=company.id,
            nome=data.nome,
            email=data.email,
            senha_hash=hash_password(data.senha),
            role=UserRole.OWNER.value,
            ativo=True,
        )
        users.add(user)
        users.commit_refresh(user)

        return AuthService._issue_tokens(user)

    @staticmethod
    def authenticate(db: Session, email: str, senha: str) -> tuple[User, str, str]:
        user = UserRepository(db).get_by_email(email)
        if not user or not verify_password(senha, user.senha_hash):
            raise UnauthorizedError("Credenciais inválidas")
        if not user.ativo:
            raise UnauthorizedError("Usuário inativo")

        return AuthService._issue_tokens(user)

    @staticmethod
    def refresh(db: Session, refresh_token: str) -> tuple[User, str, str]:
        payload = decode_token(refresh_token, REFRESH_TOKEN)
        user = UserRepository(db).get(int(payload["sub"]))
        if not user or not user.ativo:
            raise UnauthorizedError("Usuário inválido")

        return AuthService._issue_tokens(user)

    @staticmethod
    def create_user(db: Session, company_id: int, data) -> User:
        """Cria um usuário dentro de uma empresa (OWNER/ADMIN)."""
        users = UserRepository(db)
        if users.get_by_email(data.email):
            raise ConflictError("Email já cadastrado")

        user = User(
            company_id=company_id,
            nome=data.nome,
            email=data.email,
            senha_hash=hash_password(data.senha),
            role=data.role,
            ativo=True,
        )
        users.add(user)
        return users.commit_refresh(user)

    @staticmethod
    def list_users(
        db: Session, company_id: int, limit: int = 50, offset: int = 0
    ) -> tuple[list[User], int]:
        return UserRepository(db, company_id).list(limit=limit, offset=offset)

    @staticmethod
    def get_company(db: Session, company_id: int) -> Company:
        company = CompanyRepository(db).get(company_id)
        if not company:
            raise NotFoundError("Empresa não encontrada")
        return company

    @staticmethod
    def _issue_tokens(user: User) -> tuple[User, str, str]:
        access = create_access_token(user.id, user.company_id, user.role)
        refresh = create_refresh_token(user.id)
        return user, access, refresh
