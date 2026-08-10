from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.stock_movement import StockMovement, StockMovementType


class StockService:
    """Aplica e audita alterações de estoque.

    O produto deve ser carregado com lock de linha pelo chamador
    (`ProductRepository.get_for_update`) antes de vender/repor.
    """

    @staticmethod
    def _apply(
        db: Session,
        company_id: int,
        product: Product,
        delta: int,
        tipo: StockMovementType,
        order_id: int | None,
    ) -> StockMovement:
        product.estoque += delta
        movement = StockMovement(
            company_id=company_id,
            product_id=product.id,
            order_id=order_id,
            tipo=tipo.value,
            quantity=delta,
            estoque_after=product.estoque,
        )
        db.add(movement)
        return movement

    @staticmethod
    def sell(
        db: Session, company_id: int, product: Product, quantity: int, order_id: int | None
    ) -> StockMovement:
        return StockService._apply(
            db, company_id, product, -quantity, StockMovementType.SALE, order_id
        )

    @staticmethod
    def restock(
        db: Session, company_id: int, product: Product, quantity: int, order_id: int | None
    ) -> StockMovement:
        return StockService._apply(
            db, company_id, product, quantity, StockMovementType.RESTOCK, order_id
        )
