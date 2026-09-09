"""
Settings Service — Quadro de Configurações Centralizado.

CRUD sobre system_settings com seed idempotente dos defaults.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.domain.settings.models import DEFAULT_SETTINGS
from app.infrastructure.repositories.settings_model import SystemSettingModel


class SettingsError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SettingsService:
    def __init__(self, db: DBSession, tenant_id: str = "default"):
        # system_settings é global (por deploy), mas mantemos tenant no service
        # para futuro multi-tenant de configurações.
        self.db = db
        self.tenant_id = tenant_id

    def seed_defaults(self) -> int:
        """Insere defaults ausentes (idempotente). Retorna quantos criou."""
        created = 0
        for key, category, value, description in DEFAULT_SETTINGS:
            exists = self.db.get(SystemSettingModel, key)
            if exists is None:
                self.db.add(
                    SystemSettingModel(
                        id=key,
                        category=category,
                        value=value,
                        description=description,
                        is_editable=True,
                        updated_by="system:seed",
                    )
                )
                created += 1
        self.db.commit()
        return created

    def ensure_seeded(self) -> None:
        """Garante seed na primeira leitura (lazy, safe para concorrência leve)."""
        if self.db.query(SystemSettingModel).count() == 0:
            self.seed_defaults()

    def list_all(self) -> List[SystemSettingModel]:
        self.ensure_seeded()
        return self.db.query(SystemSettingModel).order_by(SystemSettingModel.category, SystemSettingModel.id).all()

    def list_by_category(self, category: str) -> List[SystemSettingModel]:
        self.ensure_seeded()
        return (
            self.db.query(SystemSettingModel)
            .filter(SystemSettingModel.category == category)
            .order_by(SystemSettingModel.id)
            .all()
        )

    def get(self, key: str) -> Optional[SystemSettingModel]:
        return self.db.get(SystemSettingModel, key)

    def get_value(self, key: str, default: Any = None) -> Any:
        row = self.get(key)
        return row.value if row else default

    def update(self, key: str, value: Any, updated_by: str = "") -> SystemSettingModel:
        row = self.db.get(SystemSettingModel, key)
        if not row:
            raise SettingsError("NOT_FOUND", f"Configuração '{key}' não encontrada.", 404)
        if not row.is_editable:
            raise SettingsError("NOT_EDITABLE", f"Configuração '{key}' não é editável.", 403)
        row.value = value
        row.updated_by = updated_by
        self.db.commit()
        self.db.refresh(row)
        return row

    def grouped(self) -> Dict[str, List[dict]]:
        result: Dict[str, List[dict]] = {}
        for row in self.list_all():
            result.setdefault(row.category, []).append(self.to_dict(row))
        return result

    @staticmethod
    def to_dict(row: SystemSettingModel) -> dict:
        return {
            "key": row.id,
            "category": row.category,
            "value": row.value,
            "description": row.description,
            "is_editable": row.is_editable,
            "updated_by": row.updated_by,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
