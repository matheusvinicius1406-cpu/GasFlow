"""
Segmentation Repository — FASE 13.1

SQLAlchemy implementation for segment persistence and evaluation.
"""

import json
from typing import Optional, List
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.segmentation.entity import Segment, SegmentRule, SegmentStatus
from app.infrastructure.repositories.segmentation_model import SegmentModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemySegmentRepository(TenantMixin):
    """Repository for customer segments."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, model: SegmentModel) -> Segment:
        rules = []
        try:
            rules_data = json.loads(model.rules_json)
            rules = [SegmentRule.from_dict(r) for r in rules_data]
        except (json.JSONDecodeError, TypeError):
            pass

        return Segment(
            id=model.id,
            name=model.name,
            description=model.description or "",
            rules=rules,
            rule_logic=model.rule_logic or "AND",
            status=SegmentStatus(model.status),
            member_count=model.member_count or 0,
            last_evaluated_at=model.last_evaluated_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Segment) -> SegmentModel:
        if entity.id:
            model = self._filter_by_tenant(SegmentModel).filter(SegmentModel.id == entity.id).first()
            if model:
                model.name = entity.name
                model.description = entity.description
                model.rules_json = json.dumps([r.to_dict() for r in entity.rules], ensure_ascii=False)
                model.rule_logic = entity.rule_logic
                model.status = entity.status.value
                model.member_count = entity.member_count
                model.last_evaluated_at = entity.last_evaluated_at
                model.updated_at = datetime.utcnow()
                return model

        return SegmentModel(
            tenant_id=self.tenant_id,
            name=entity.name,
            description=entity.description,
            rules_json=json.dumps([r.to_dict() for r in entity.rules], ensure_ascii=False),
            rule_logic=entity.rule_logic,
            status=entity.status.value,
            member_count=entity.member_count,
            last_evaluated_at=entity.last_evaluated_at,
        )

    def find_by_id(self, segment_id: int) -> Optional[Segment]:
        model = self._filter_by_tenant(SegmentModel).filter(SegmentModel.id == segment_id).first()
        return self._to_entity(model) if model else None

    def list_all(self, status: Optional[str] = None) -> List[Segment]:
        query = self._filter_by_tenant(SegmentModel)
        if status:
            query = query.filter(SegmentModel.status == status)
        models = query.order_by(SegmentModel.created_at.desc()).all()
        return [self._to_entity(m) for m in models]

    def create(self, segment: Segment) -> Segment:
        model = self._to_model(segment)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def update(self, segment: Segment) -> Segment:
        model = self._to_model(segment)
        if model:
            self.db.commit()
            self.db.refresh(model)
        return self._to_entity(model)

    def delete(self, segment_id: int) -> bool:
        model = self._filter_by_tenant(SegmentModel).filter(SegmentModel.id == segment_id).first()
        if model:
            self.db.delete(model)
            self.db.commit()
            return True
        return False

    def update_member_count(self, segment_id: int, count: int) -> None:
        model = self._filter_by_tenant(SegmentModel).filter(SegmentModel.id == segment_id).first()
        if model:
            model.member_count = count
            model.last_evaluated_at = datetime.utcnow()
            model.updated_at = datetime.utcnow()
            self.db.commit()
