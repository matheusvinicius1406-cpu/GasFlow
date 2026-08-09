
from app.models.order import Order
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    def last(self) -> Order | None:
        items, _ = self.list(limit=1, offset=0)
        return items[0] if items else None
