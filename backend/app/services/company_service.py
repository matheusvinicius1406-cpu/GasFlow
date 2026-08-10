from sqlalchemy.orm import Session

from app.models.company import Company
from app.repositories.company_repository import CompanyRepository

DEFAULT_COMPANY_CODIGO = "000001"


class CompanyService:

    @staticmethod
    def generate_code(db: Session) -> str:
        last = CompanyRepository(db).last()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db: Session, data) -> Company:
        repo = CompanyRepository(db)
        codigo = CompanyService.generate_code(db)

        company = Company(
            codigo=codigo,
            nome=data.nome,
            cnpj=data.cnpj,
            telefone=data.telefone,
            responsavel=data.responsavel,
            plano=data.plano,
            ativo=True,
        )

        repo.add(company)
        return repo.commit_refresh(company)

    @staticmethod
    def get_all(db: Session, limit: int = 50, offset: int = 0) -> tuple[list[Company], int]:
        return CompanyRepository(db).list(limit=limit, offset=offset, ativo=True)

    @staticmethod
    def get_by_code(db: Session, codigo: str) -> Company | None:
        return CompanyRepository(db).get_by_code(codigo)

    @staticmethod
    def get_or_create_default(db: Session) -> Company:
        """Empresa padrão para uso single-tenant / desenvolvimento.

        Enquanto a autenticação (Fase 2) não injeta a empresa a partir do
        usuário, requisições sem `X-Company-Id` operam sob esta empresa.
        """
        repo = CompanyRepository(db)
        company = repo.get_by_code(DEFAULT_COMPANY_CODIGO)
        if company:
            return company

        company = Company(
            codigo=DEFAULT_COMPANY_CODIGO,
            nome="Depósito Padrão",
            plano="FREE",
            ativo=True,
        )
        repo.add(company)
        return repo.commit_refresh(company)
