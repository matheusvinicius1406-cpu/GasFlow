"""
Payment Service Persistence Repository — SQLAlchemy implementation.

Replaces in-memory PaymentService storage with database persistence.
Single source of truth for payment methods, PIX config, and payments.
"""

from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from app.infrastructure.repositories.payment_model import PaymentMethodRecord, PixConfigRecord, PaymentServiceRecord


class SQLAlchemyPaymentMethodRepository:
    """Repository for payment methods — replaces in-memory _methods dict."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, method_id: str) -> Optional[PaymentMethodRecord]:
        return self.db.query(PaymentMethodRecord).filter(PaymentMethodRecord.id == method_id).first()

    def get_by_tenant_and_code(self, tenant_id: str, code: str) -> Optional[PaymentMethodRecord]:
        return (
            self.db.query(PaymentMethodRecord)
            .filter(
                PaymentMethodRecord.tenant_id == tenant_id,
                PaymentMethodRecord.code == code,
            )
            .first()
        )

    def list_by_tenant(self, tenant_id: str, enabled_only: bool = False) -> List[PaymentMethodRecord]:
        q = self.db.query(PaymentMethodRecord).filter(PaymentMethodRecord.tenant_id == tenant_id)
        if enabled_only:
            q = q.filter(PaymentMethodRecord.enabled == True)
        return q.order_by(PaymentMethodRecord.display_order).all()

    def create(self, **kwargs) -> PaymentMethodRecord:
        import uuid as _uuid

        if "id" not in kwargs or not kwargs["id"]:
            kwargs["id"] = str(_uuid.uuid4())
        model = PaymentMethodRecord(**kwargs)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def update(self, method_id: str, **kwargs) -> Optional[PaymentMethodRecord]:
        model = self.get_by_id(method_id)
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        model.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return model

    def delete(self, method_id: str) -> bool:
        model = self.get_by_id(method_id)
        if not model:
            return False
        self.db.delete(model)
        self.db.commit()
        return True


class SQLAlchemyPixConfigRepository:
    """Repository for PIX configs — replaces in-memory _pix_configs dict."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, config_id: str) -> Optional[PixConfigRecord]:
        return self.db.query(PixConfigRecord).filter(PixConfigRecord.id == config_id).first()

    def get_active_by_tenant(self, tenant_id: str) -> Optional[PixConfigRecord]:
        return (
            self.db.query(PixConfigRecord)
            .filter(
                PixConfigRecord.tenant_id == tenant_id,
                PixConfigRecord.active == True,
            )
            .first()
        )

    def list_by_tenant(self, tenant_id: str) -> List[PixConfigRecord]:
        return self.db.query(PixConfigRecord).filter(PixConfigRecord.tenant_id == tenant_id).all()

    def create(self, **kwargs) -> PixConfigRecord:
        import uuid as _uuid

        if "id" not in kwargs or not kwargs["id"]:
            kwargs["id"] = str(_uuid.uuid4())
        model = PixConfigRecord(**kwargs)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def update(self, config_id: str, **kwargs) -> Optional[PixConfigRecord]:
        model = self.get_by_id(config_id)
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        model.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return model

    def delete(self, config_id: str) -> bool:
        model = self.get_by_id(config_id)
        if not model:
            return False
        self.db.delete(model)
        self.db.commit()
        return True


class SQLAlchemyServicePaymentRepository:
    """Repository for payments — replaces in-memory _payments dict."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, payment_id: str) -> Optional[PaymentServiceRecord]:
        return self.db.query(PaymentServiceRecord).filter(PaymentServiceRecord.id == payment_id).first()

    def list_by_tenant(self, tenant_id: str, status: str = None, limit: int = 50) -> List[PaymentServiceRecord]:
        q = self.db.query(PaymentServiceRecord).filter(PaymentServiceRecord.tenant_id == tenant_id)
        if status:
            q = q.filter(PaymentServiceRecord.status == status)
        return q.order_by(PaymentServiceRecord.created_at.desc()).limit(limit).all()

    def list_by_order(self, order_id: str, tenant_id: str) -> List[PaymentServiceRecord]:
        return (
            self.db.query(PaymentServiceRecord)
            .filter(
                PaymentServiceRecord.order_id == order_id,
                PaymentServiceRecord.tenant_id == tenant_id,
            )
            .all()
        )

    def find_by_external_id(self, external_id: str) -> Optional[PaymentServiceRecord]:
        """Tenant-agnostic lookup by PSP external id (webhook confirmation)."""
        return self.db.query(PaymentServiceRecord).filter(PaymentServiceRecord.external_id == external_id).first()

    def find_by_copy_paste(self, txid: str) -> Optional[PaymentServiceRecord]:
        """Tenant-agnostic lookup by txid embedded in the BR Code copy-paste.

        Fallback for payments created before the external_id convention.
        """
        return self.db.query(PaymentServiceRecord).filter(PaymentServiceRecord.pix_copy_paste.like(f"%{txid}%")).first()

    def create(self, **kwargs) -> PaymentServiceRecord:
        import uuid as _uuid

        if "id" not in kwargs or not kwargs["id"]:
            kwargs["id"] = str(_uuid.uuid4())
        model = PaymentServiceRecord(**kwargs)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def update(self, payment_id: str, **kwargs) -> Optional[PaymentServiceRecord]:
        model = self.get_by_id(payment_id)
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        model.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return model

    def sum_confirmed_by_order(self, order_id: str, tenant_id: str) -> float:
        from sqlalchemy import func

        result = (
            self.db.query(func.sum(PaymentServiceRecord.amount))
            .filter(
                PaymentServiceRecord.order_id == order_id,
                PaymentServiceRecord.tenant_id == tenant_id,
                PaymentServiceRecord.status == "CONFIRMED",
            )
            .scalar()
        )
        return float(result or 0.0)

    def summary_by_tenant(self, tenant_id: str) -> Dict:
        all_payments = self.db.query(PaymentServiceRecord).filter(PaymentServiceRecord.tenant_id == tenant_id).all()

        confirmed = [p for p in all_payments if p.status == "CONFIRMED"]
        pending = [p for p in all_payments if p.status == "PENDING"]

        total_received = sum(p.amount for p in confirmed)
        total_pending = sum(p.amount for p in pending)

        by_method = {}
        for p in confirmed:
            method = p.method_code or "UNKNOWN"
            if method not in by_method:
                by_method[method] = {"count": 0, "total": 0}
            by_method[method]["count"] += 1
            by_method[method]["total"] += p.amount

        return {
            "total_received": total_received,
            "total_pending": total_pending,
            "total_payments": len(all_payments),
            "confirmed_count": len(confirmed),
            "pending_count": len(pending),
            "by_method": by_method,
        }
