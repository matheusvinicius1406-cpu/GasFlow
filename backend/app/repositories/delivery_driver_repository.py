
from app.models.delivery_driver import DeliveryDriver
from app.repositories.base import BaseRepository


class DeliveryDriverRepository(BaseRepository[DeliveryDriver]):
    model = DeliveryDriver

    def last(self) -> DeliveryDriver | None:
        items, _ = self.list(limit=1, offset=0)
        return items[0] if items else None
