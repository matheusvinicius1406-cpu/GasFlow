
from sqlalchemy.orm import Session

from app.models.delivery_driver import DeliveryDriver
from app.repositories.delivery_driver_repository import DeliveryDriverRepository


class DeliveryDriverService:

    @staticmethod
    def generate_code(db: Session) -> str:
        last = DeliveryDriverRepository(db).last()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    @staticmethod
    def create(db: Session, data) -> DeliveryDriver:
        repo = DeliveryDriverRepository(db)
        codigo = DeliveryDriverService.generate_code(db)

        driver = DeliveryDriver(
            codigo=codigo,
            nome=data.nome,
            telefone=data.telefone,
            placa=data.placa,
            ativo=True,
        )

        repo.add(driver)
        return repo.commit_refresh(driver)

    @staticmethod
    def get_all(
        db: Session, limit: int = 50, offset: int = 0
    ) -> tuple[list[DeliveryDriver], int]:
        return DeliveryDriverRepository(db).list(limit=limit, offset=offset, ativo=True)

    @staticmethod
    def get_by_code(db: Session, codigo: str) -> DeliveryDriver | None:
        return DeliveryDriverRepository(db).get_by_code(codigo)

    @staticmethod
    def disable(db: Session, codigo: str) -> DeliveryDriver | None:
        repo = DeliveryDriverRepository(db)
        driver = repo.get_by_code(codigo)
        if not driver:
            return None

        driver.ativo = False
        return repo.commit_refresh(driver)
