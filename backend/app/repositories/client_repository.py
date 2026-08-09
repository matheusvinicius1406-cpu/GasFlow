
from app.models.client import Client
from app.repositories.base import BaseRepository


class ClientRepository(BaseRepository[Client]):
    model = Client

    def get_by_phone(self, telefone: str) -> Client | None:
        return self.get_by(telefone=telefone)

    def last(self) -> Client | None:
        items, _ = self.list(limit=1, offset=0)
        return items[0] if items else None
