from datetime import datetime
from sqlalchemy.orm import Session
from app.models.delivery_driver import DeliveryDriver


class DeliveryDriverService:

    @staticmethod
    def generate_code(db: Session) -> str:
        last = db.query(DeliveryDriver).order_by(DeliveryDriver.id.desc()).first()

        if not last:
            return "000001"

        next_id = int(last.codigo) + 1
        return f"{next_id:06d}"

    @staticmethod
    def create(db: Session, data):
        codigo = DeliveryDriverService.generate_code(db)

        driver = DeliveryDriver(
            codigo=codigo,
            nome=data.nome,
            telefone=data.telefone,
            placa=data.placa,
            ativo=True,
            created_at=datetime.utcnow(),
        )

        db.add(driver)
        db.commit()
        db.refresh(driver)

        return driver

    @staticmethod
    def get_all(db: Session):
        return db.query(DeliveryDriver).filter(DeliveryDriver.ativo == True).all()

    @staticmethod
    def get_by_code(db: Session, codigo: str):
        return db.query(DeliveryDriver).filter(DeliveryDriver.codigo == codigo).first()

    @staticmethod
    def disable(db: Session, codigo: str):
        driver = db.query(DeliveryDriver).filter(DeliveryDriver.codigo == codigo).first()

        if not driver:
            return None

        driver.ativo = False

        db.commit()
        db.refresh(driver)

        return driver