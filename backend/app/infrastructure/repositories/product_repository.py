"""
Product Repository Implementation — Implementação SQLAlchemy do repositório de produtos.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.domain.product.entity import Product
from app.domain.product.repository import ProductRepository
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyProductRepository(TenantMixin, ProductRepository):
    """Implementação do repositório de produtos usando SQLAlchemy."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, model: ProductModel) -> Product:
        return Product(
            id=model.id,
            codigo=model.codigo,
            nome=model.nome,
            tipo=model.tipo,
            preco=model.preco,
            estoque=model.estoque,
            ativo=model.ativo,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Product) -> ProductModel:
        if entity.id:
            model = self._filter_by_tenant(ProductModel).filter(ProductModel.id == entity.id).first()
            if model:
                model.codigo = entity.codigo
                model.nome = entity.nome
                model.tipo = entity.tipo
                model.preco = entity.preco
                model.estoque = entity.estoque
                model.ativo = entity.ativo
                return model

        return ProductModel(
            tenant_id=self.tenant_id,
            codigo=entity.codigo,
            nome=entity.nome,
            tipo=entity.tipo,
            preco=entity.preco,
            estoque=entity.estoque,
            ativo=entity.ativo,
        )

    def criar(self, product: Product) -> Product:
        model = self._to_model(product)
        model.tenant_id = self.tenant_id
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def buscar_por_codigo(self, codigo: str) -> Optional[Product]:
        model = self._filter_by_tenant(ProductModel).filter(ProductModel.codigo == codigo).first()
        return self._to_entity(model) if model else None

    def buscar_por_id(self, id: int) -> Optional[Product]:
        model = self._filter_by_tenant(ProductModel).filter(ProductModel.id == id).first()
        return self._to_entity(model) if model else None

    def listar_todos(self) -> List[Product]:
        models = self._filter_by_tenant(ProductModel).filter(ProductModel.ativo == True).all()
        return [self._to_entity(m) for m in models]

    def atualizar(self, product: Product) -> Product:
        model = self._to_model(product)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def desativar(self, codigo: str) -> Optional[Product]:
        model = self._filter_by_tenant(ProductModel).filter(ProductModel.codigo == codigo).first()
        if not model:
            return None
        model.ativo = False
        model.updated_at = __import__("datetime").datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def proximo_codigo(self) -> str:
        last = self._filter_by_tenant(ProductModel).order_by(ProductModel.id.desc()).first()
        if not last:
            return "000001"
        next_id = int(last.codigo) + 1
        return f"{next_id:06d}"
