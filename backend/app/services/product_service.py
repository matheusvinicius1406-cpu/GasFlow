
from sqlalchemy.orm import Session

from app.models.product import Product
from app.repositories.product_repository import ProductRepository


class ProductService:

    @staticmethod
    def generate_code(db: Session) -> str:
        last = ProductRepository(db).last()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db: Session, data) -> Product:
        repo = ProductRepository(db)
        codigo = ProductService.generate_code(db)

        product = Product(
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
    def get_all(db: Session, limit: int = 50, offset: int = 0) -> tuple[list[Product], int]:
        return ProductRepository(db).list(limit=limit, offset=offset, ativo=True)

    @staticmethod
    def get_by_code(db: Session, codigo: str) -> Product | None:
        return ProductRepository(db).get_by_code(codigo)

    @staticmethod
    def update(db: Session, codigo: str, data) -> Product | None:
        repo = ProductRepository(db)
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
    def disable(db: Session, codigo: str) -> Product | None:
        repo = ProductRepository(db)
        product = repo.get_by_code(codigo)
        if not product:
            return None

        product.ativo = False
        return repo.commit_refresh(product)
