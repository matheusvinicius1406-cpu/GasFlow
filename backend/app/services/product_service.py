from sqlalchemy.orm import Session

from app.models.product import Product
from app.repositories.product_repository import ProductRepository


class ProductService:

    @staticmethod
    def generate_code(db: Session, company_id: int) -> str:
        last = ProductRepository(db, company_id).last()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db: Session, company_id: int, data) -> Product:
        repo = ProductRepository(db, company_id)
        codigo = ProductService.generate_code(db, company_id)

        product = Product(
            company_id=company_id,
            codigo=codigo,
            nome=data.nome,
            tipo=data.tipo,
            preco=data.preco,
            estoque=data.estoque,
            ativo=True,
        )

        repo.add(product)
        return repo.commit_refresh(product)

    @staticmethod
    def get_all(
        db: Session, company_id: int, limit: int = 50, offset: int = 0
    ) -> tuple[list[Product], int]:
        return ProductRepository(db, company_id).list(limit=limit, offset=offset, ativo=True)

    @staticmethod
    def get_by_code(db: Session, company_id: int, codigo: str) -> Product | None:
        return ProductRepository(db, company_id).get_by_code(codigo)

    @staticmethod
    def update(db: Session, company_id: int, codigo: str, data) -> Product | None:
        repo = ProductRepository(db, company_id)
        product = repo.get_by_code(codigo)
        if not product:
            return None

        if data.nome is not None:
            product.nome = data.nome
        if data.tipo is not None:
            product.tipo = data.tipo
        if data.preco is not None:
            product.preco = data.preco
        if data.estoque is not None:
            product.estoque = data.estoque
        if data.ativo is not None:
            product.ativo = data.ativo

        return repo.commit_refresh(product)

    @staticmethod
    def disable(db: Session, company_id: int, codigo: str) -> Product | None:
        repo = ProductRepository(db, company_id)
        product = repo.get_by_code(codigo)
        if not product:
            return None

        product.ativo = False
        return repo.commit_refresh(product)
