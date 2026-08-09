from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Acesso a dados genérico com CRUD e paginação.

    Serviços usam repositórios em vez de montar queries diretamente, mantendo
    a lógica de acesso a dados em um único lugar e facilitando testes.
    """

    model: type[ModelType]

    def __init__(self, db: Session):
        self.db = db

    def get(self, id_: int) -> ModelType | None:
        return self.db.get(self.model, id_)

    def get_by(self, **filters) -> ModelType | None:
        stmt = select(self.model).filter_by(**filters)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, codigo: str) -> ModelType | None:
        return self.get_by(codigo=codigo)

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by=None,
        **filters,
    ) -> tuple[list[ModelType], int]:
        """Retorna (itens da página, total de itens que casam os filtros)."""

        base = select(self.model).filter_by(**filters)

        total = self.db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        if order_by is None:
            order_by = self.model.id.desc()

        items = list(
            self.db.execute(base.order_by(order_by).limit(limit).offset(offset))
            .scalars()
            .all()
        )
        return items, total

    def add(self, entity: ModelType) -> ModelType:
        self.db.add(entity)
        self.db.flush()
        return entity

    def commit_refresh(self, entity: ModelType) -> ModelType:
        self.db.commit()
        self.db.refresh(entity)
        return entity
