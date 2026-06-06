from datetime import datetime

from app.models.client import Client

clients_db = []


class ClientService:

    @staticmethod
    def generate_code() -> str:
        next_id = len(clients_db) + 1
        return f"{next_id:06d}"

    @staticmethod
    def create(data):

        codigo = ClientService.generate_code()

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

        clients_db.append(client)

        return client

    @staticmethod
    def get_all():
        return clients_db

    @staticmethod
    def get_by_code(codigo: str):

        for client in clients_db:

            if client.codigo == codigo:
                return client

        return None