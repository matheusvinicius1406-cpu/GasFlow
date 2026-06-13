from datetime import datetime
from sqlalchemy.orm import Session
from app.models.product import Product


class ProductService:

    @staticmethod
    def generate_code(db: Session) -> str:
        last = db.query(Product).order_by(Product.id.desc()).first()

        if not last:
            return "000001"

        next_id = int(last.codigo) + 1
        return f"{next_id:06d}"

    @staticmethod
    def create(db: Session, data):
        codigo = ProductService.generate_code(db)

        product = Product(
            codigo=codigo,
            nome=data.nome,
            tipo=data.tipo,
            preco=data.preco,
            estoque=data.estoque,
            ativo=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(product)
        db.commit()
        db.refresh(product)

        return product

    @staticmethod
    def get_all(db: Session):
        return db.query(Product).filter(Product.ativo == True).all()

    @staticmethod
    def get_by_code(db: Session, codigo: str):
        return db.query(Product).filter(Product.codigo == codigo).first()

    @staticmethod
    def update(db: Session, codigo: str, data):
        product = db.query(Product).filter(Product.codigo == codigo).first()

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

        product.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(product)

        return product