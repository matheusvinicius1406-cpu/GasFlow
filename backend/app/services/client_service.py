from sqlalchemy.orm import Session

from app.models.client import Client
from app.repositories.client_repository import ClientRepository


class ClientService:

    @staticmethod
    def generate_code(db: Session, company_id: int) -> str:
        last = ClientRepository(db, company_id).last()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db: Session, company_id: int, data) -> Client:
        repo = ClientRepository(db, company_id)
        codigo = ClientService.generate_code(db, company_id)

        client = Client(
            company_id=company_id,
            codigo=codigo,
            nome=data.nome,
            telefone=data.telefone,
            telefone_secundario=data.telefone_secundario,
            rua=data.rua,
            numero=data.numero,
            complemento=data.complemento,
            referencia=data.referencia,
            bairro=data.bairro,
            observacoes=data.observacoes,
            ativo=True,
        )

        repo.add(client)
        return repo.commit_refresh(client)

    @staticmethod
    def get_all(
        db: Session, company_id: int, limit: int = 50, offset: int = 0
    ) -> tuple[list[Client], int]:
        return ClientRepository(db, company_id).list(limit=limit, offset=offset, ativo=True)

    @staticmethod
    def get_by_code(db: Session, company_id: int, codigo: str) -> Client | None:
        return ClientRepository(db, company_id).get_by_code(codigo)

    @staticmethod
    def update(db: Session, company_id: int, codigo: str, data) -> Client | None:
        repo = ClientRepository(db, company_id)
        client = repo.get_by_code(codigo)
        if not client:
            return None

        client.nome = data.nome
        client.telefone = data.telefone
        client.telefone_secundario = data.telefone_secundario
        client.rua = data.rua
        client.numero = data.numero
        client.complemento = data.complemento
        client.referencia = data.referencia
        client.bairro = data.bairro
        client.observacoes = data.observacoes

        return repo.commit_refresh(client)

    @staticmethod
    def disable(db: Session, company_id: int, codigo: str) -> Client | None:
        repo = ClientRepository(db, company_id)
        client = repo.get_by_code(codigo)
        if not client:
            return None

        client.ativo = False
        return repo.commit_refresh(client)

    @staticmethod
    def get_by_phone(db: Session, company_id: int, telefone: str) -> Client | None:
        return ClientRepository(db, company_id).get_by_phone(telefone)

    @staticmethod
    def format_crm_name(client: Client) -> str:
        return (
            f"{client.codigo}= {client.rua} Nº{client.numero} "
            f"({client.referencia or ''}) ({client.nome})"
        )
