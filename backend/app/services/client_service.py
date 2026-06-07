from datetime import datetime
from sqlalchemy.orm import Session
from app.models.client import Client


class ClientService:

    @staticmethod
    def generate_code(db: Session) -> str:
        last_client = (
            db.query(Client)
            .order_by(Client.id.desc())
            .first()
        )

        if not last_client:
            return "000001"

        next_id = int(last_client.codigo) + 1
        return f"{next_id:06d}"

    @staticmethod
    def create(db: Session, data):

        codigo = ClientService.generate_code(db)

        client = Client(
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(client)
        db.commit()
        db.refresh(client)

        return client

    @staticmethod
    def get_all(db: Session):
        return db.query(Client).all()

    @staticmethod
    def get_by_code(db: Session, codigo: str):
        return db.query(Client).filter(Client.codigo == codigo).first()

    @staticmethod
    def update(db: Session, codigo: str, data):

        client = db.query(Client).filter(Client.codigo == codigo).first()

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
        client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(client)

        return client

    @staticmethod
    def get_by_phone(db: Session, telefone: str):

        return db.query(Client).filter(Client.telefone == telefone).first()

    @staticmethod
    def format_crm_name(client: Client) -> str:
        return f"{client.codigo}= {client.rua} Nº{client.numero} ({client.referencia or ''}) ({client.nome})"