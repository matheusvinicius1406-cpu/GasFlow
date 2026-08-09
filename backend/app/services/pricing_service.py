from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.product_repository import ProductRepository


class PricingService:
    """Ponto único de precificação. Estender aqui para descontos/promoções."""

    @staticmethod
    def calculate(db: Session, product_codigo: str, quantity: int) -> float:
        product = ProductRepository(db).get_by_code(product_codigo)
        if not product:
            raise NotFoundError(f"Produto {product_codigo} não encontrado")
        return product.preco * quantity
