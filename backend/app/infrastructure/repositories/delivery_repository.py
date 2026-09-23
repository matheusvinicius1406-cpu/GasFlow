"""
DeliveryDriver Repository Implementation — Implementação SQLAlchemy do repositório de entregadores.
"""

from datetime import datetime
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

    def get_tracking_epoch(self, codigo: str) -> int:
        """Epoch de revogação do link público (0 quando não configurada)."""
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if not model:
            return 0
        return int(model.tracking_epoch or 0)

    def bump_tracking_epoch(self, codigo: str) -> int:
        """Incrementa a epoch — invalida todos os links já emitidos."""
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if not model:
            return 0
        model.tracking_epoch = int(model.tracking_epoch or 0) + 1
        self.db.commit()
        return int(model.tracking_epoch)

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

    def set_status(self, codigo: str, status: str) -> bool:
        """Grava o status do entregador ("AVAILABLE", "BUSY", "OFFLINE"...).

        O campo `status` existe no **model**; a entidade devolvida por
        `buscar_por_codigo` é um dataclass desconectado (só codigo/nome/
        telefone/placa/ativo), então mutar a entidade não chega ao banco. Foi a
        origem de vários 500 em `delivery_ops` (chamadas a `set_busy()`,
        `set_available()` etc. que a entidade não tem).
        """
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if not model:
            return False
        model.status = status
        model.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def update_profile(self, codigo: str, nome: str, telefone: str, placa: Optional[str]) -> bool:
        """Grava os campos de cadastro (nome/telefone/placa) no model.

        Mesmo motivo do `set_status`: a entidade devolvida por
        `buscar_por_codigo` é um dataclass desconectado — mutar nela não chega ao
        banco, e o `__post_init__` dela valida codigo/nome/telefone.
        """
        if not nome or not nome.strip():
            raise ValueError("nome é obrigatório")
        if not telefone or not telefone.strip():
            raise ValueError("telefone é obrigatório")

        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if not model:
            return False
        model.nome = nome.strip()
        model.telefone = telefone.strip()
        model.placa = placa
        model.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def set_vehicle_and_document(self, codigo: str, document: Optional[str], vehicle_id: Optional[str]) -> bool:
        """Grava CNH/documento e veículo — colunas do model sem par na entidade.

        A entidade `DeliveryDriver` modela só codigo/nome/telefone/placa/ativo; o
        `document` (CPF/CNH) e o `vehicle_id` vivem apenas no model. Sem isto, a
        criação aceitaria os campos no request e os descartaria em silêncio.
        """
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if not model:
            return False
        if document is not None:
            model.document = document
        if vehicle_id is not None:
            model.vehicle_id = vehicle_id
        model.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def snapshot(self, codigo: str) -> Optional[dict]:
        """Retrato do entregador lido do model — o que as respostas de API devolvem."""
        model = self._filter_by_tenant(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if not model:
            return None
        return {
            "codigo": model.codigo,
            "nome": model.nome,
            "telefone": model.telefone,
            "placa": model.placa,
            "document": model.document,
            "vehicle_id": model.vehicle_id,
            "ativo": bool(model.ativo),
            "status": model.status or "AVAILABLE",
            "tenant_id": model.tenant_id,
            "created_at": model.created_at,
        }

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
