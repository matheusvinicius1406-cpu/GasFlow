from app.models.company import Company
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    model = Company

    def last(self) -> Company | None:
        items, _ = self.list(limit=1, offset=0)
        return items[0] if items else None
