
from sqlalchemy import select

from app.models.product import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    model = Product

    def get_for_update(self, codigo: str) -> Product | None:
        """Carrega o produto com lock de linha para atualização de estoque."""
        stmt = select(Product).where(Product.codigo == codigo).with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def last(self) -> Product | None:
        items, _ = self.list(limit=1, offset=0)
        return items[0] if items else None
