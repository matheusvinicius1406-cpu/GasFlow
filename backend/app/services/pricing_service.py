from sqlalchemy.orm import Session
from app.models.product import Product


class PricingService:

    @staticmethod
    def calculate(db: Session, product_codigo: str, quantity: int) -> float:
        product = db.query(Product).filter(Product.codigo == product_codigo).first()

        if not product:
            raise Exception(f"Produto {product_codigo} não encontrado")

        return product.preco * quantity