"""
DeliveryDriver Repository Implementation — Implementação SQLAlchemy do repositório de entregadores.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.domain.delivery.entity import DeliveryDriver
from app.domain.delivery.repository import DeliveryDriverRepository
from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyDeliveryDriverRepository(TenantMixin, DeliveryDriverRepository):
    """Implementação do repositório de entregadores usando SQLAlchemy."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, model: DeliveryDriverModel) -> DeliveryDriver:
        return DeliveryDriver(
            id=model.id,
            codigo=model.codigo,
            nome=model.nome,
            telefone=model.telefone,
            placa=model.placa,
            ativo=model.ativo,
            created_at=model.created_at,
        )

    def set_credentials(self, codigo: str, username: str, password_hash: str):
        """Set login credentials for a driver."""
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if model:
            model.username = username
            model.password_hash = password_hash
            self.db.commit()

    def find_by_username(self, username: str):
        """Find an active driver by username."""
        model = (
            self._filter_by_tenant(DeliveryDriverModel)
            .filter(
                DeliveryDriverModel.username == username,
                DeliveryDriverModel.ativo == True,
            )
            .first()
        )
        return model

    def find_by_id_as_model(self, codigo: str):
        """Find driver model by codigo (returns SQLAlchemy model, not entity)."""
        return self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()

    def _to_model(self, entity: DeliveryDriver) -> DeliveryDriverModel:
        if entity.id:
            model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.id == entity.id).first()
            if model:
                model.codigo = entity.codigo
                model.nome = entity.nome
                model.telefone = entity.telefone
                model.placa = entity.placa
                model.ativo = entity.ativo
                return model

        return DeliveryDriverModel(
            tenant_id=self.tenant_id,
            codigo=entity.codigo,
            nome=entity.nome,
            telefone=entity.telefone,
            placa=entity.placa,
            ativo=entity.ativo,
        )

    def criar(self, driver: DeliveryDriver) -> DeliveryDriver:
        model = self._to_model(driver)
        model.tenant_id = self.tenant_id
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def buscar_por_codigo(self, codigo: str) -> Optional[DeliveryDriver]:
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        return self._to_entity(model) if model else None

    def listar_todos(self) -> List[DeliveryDriver]:
        models = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.ativo == True).all()
        return [self._to_entity(m) for m in models]

    def desativar(self, codigo: str) -> Optional[DeliveryDriver]:
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if not model:
            return None
        model.ativo = False
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def proximo_codigo(self) -> str:
        last = self._filter_by_tenant(DeliveryDriverModel).order_by(DeliveryDriverModel.id.desc()).first()
        if not last:
            return "000001"
        next_id = int(last.codigo) + 1
        return f"{next_id:06d}"
