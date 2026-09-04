"""
Payment Service — GasFlow

Manages payment lifecycle with tenant isolation.
Each operation is tenant-scoped.

Architecture:
    API → PaymentService → PaymentRepository → Database
"""

from typing import Dict, List, Optional
from datetime import datetime
import threading
import time

from app.domain.payment.models import (
    Payment, PaymentMethod, PixConfig,
    PaymentStatus, PaymentType, PixKeyType,
)
from app.domain.payment.pix_service import (
    PixService, _sanitize_txid,
)


class PaymentService:
    """Payment service with database persistence.
    
    Supports two modes:
    - DB mode: when db session is provided, uses SQLAlchemy repositories
    - In-memory mode: fallback for tests
    """

    def __init__(self, db=None):
        self._db = db
        self._use_db = db is not None
        # In-memory fallback (for tests)
        self._payments: Dict[str, Payment] = {}
        self._methods: Dict[str, PaymentMethod] = {}
        self._pix_configs: Dict[str, PixConfig] = {}
        self._lock = threading.Lock()

    # ── DB Helpers ──────────────────────────────────────

    def _get_method_repo(self):
        from app.infrastructure.repositories.payment_repository import SQLAlchemyPaymentMethodRepository
        return SQLAlchemyPaymentMethodRepository(self._db)

    def _get_pix_repo(self):
        from app.infrastructure.repositories.payment_repository import SQLAlchemyPixConfigRepository
        return SQLAlchemyPixConfigRepository(self._db)

    def _get_payment_repo(self):
        from app.infrastructure.repositories.payment_repository import SQLAlchemyServicePaymentRepository
        return SQLAlchemyServicePaymentRepository(self._db)

    def _method_model_to_domain(self, model) -> PaymentMethod:
        return PaymentMethod(
            id=model.id, tenant_id=model.tenant_id, code=model.code,
            name=model.name, payment_type=PaymentType(model.payment_type),
            enabled=model.enabled, display_order=model.display_order,
            requires_confirmation=model.requires_confirmation,
            description=model.description, fee_type=model.fee_type,
            fee_value=model.fee_value, discount_type=model.discount_type,
            discount_value=model.discount_value,
            created_at=model.created_at.isoformat() if model.created_at else "",
            updated_at=model.updated_at.isoformat() if model.updated_at else "",
        )

    def _pix_model_to_domain(self, model) -> PixConfig:
        return PixConfig(
            id=model.id, tenant_id=model.tenant_id, key=model.key,
            key_type=PixKeyType(model.key_type),
            holder_name=model.holder_name, holder_document=model.holder_document,
            institution=model.institution, city=model.city,
            copy_paste_code=model.copy_paste_code, active=model.active,
            created_at=model.created_at.isoformat() if model.created_at else "",
            updated_at=model.updated_at.isoformat() if model.updated_at else "",
        )

    def _payment_model_to_domain(self, model) -> Payment:
        return Payment(
            id=model.id, tenant_id=model.tenant_id,
            order_id=model.order_id, order_codigo=model.order_codigo,
            customer_codigo=model.customer_codigo, amount=model.amount,
            method_code=model.method_code, method_name=model.method_name,
            status=PaymentStatus(model.status),
            pix_key_used=model.pix_key_used, pix_copy_paste=model.pix_copy_paste,
            confirmed_by=model.confirmed_by,
            confirmed_at=model.confirmed_at.isoformat() if model.confirmed_at else None,
            confirmation_notes=model.confirmation_notes,
            refunded_at=model.refunded_at.isoformat() if model.refunded_at else None,
            refund_reason=model.refund_reason,
            provider=model.provider, external_id=model.external_id,
            provider_status=model.provider_status,
            created_at=model.created_at.isoformat() if model.created_at else "",
            updated_at=model.updated_at.isoformat() if model.updated_at else "",
        )

    # ── Payment Methods ────────────────────────────────

    def get_methods(self, tenant_id: str) -> List[PaymentMethod]:
        """Get all payment methods for a tenant."""
        if self._use_db:
            models = self._get_method_repo().list_by_tenant(tenant_id)
            return [self._method_model_to_domain(m) for m in models]
        return [m for m in self._methods.values() if m.tenant_id == tenant_id]

    def get_enabled_methods(self, tenant_id: str) -> List[PaymentMethod]:
        """Get enabled payment methods for a tenant."""
        if self._use_db:
            models = self._get_method_repo().list_by_tenant(tenant_id, enabled_only=True)
            return [self._method_model_to_domain(m) for m in models]
        return [m for m in self._methods.values() if m.tenant_id == tenant_id and m.enabled]

    def get_method(self, method_id: str, tenant_id: str) -> Optional[PaymentMethod]:
        """Get a specific payment method (tenant-scoped)."""
        if self._use_db:
            model = self._get_method_repo().get_by_id(method_id)
            if model and model.tenant_id == tenant_id:
                return self._method_model_to_domain(model)
            return None
        method = self._methods.get(method_id)
        if method and method.tenant_id == tenant_id:
            return method
        return None

    def get_method_by_code(self, code: str, tenant_id: str) -> Optional[PaymentMethod]:
        """Get payment method by code (tenant-scoped)."""
        if self._use_db:
            model = self._get_method_repo().get_by_tenant_and_code(tenant_id, code)
            return self._method_model_to_domain(model) if model else None
        for m in self._methods.values():
            if m.tenant_id == tenant_id and m.code == code:
                return m
        return None

    def create_method(self, tenant_id: str, code: str, name: str,
                      payment_type: str = "CUSTOM", **kwargs) -> PaymentMethod:
        """Create a payment method for a tenant."""
        if self._use_db:
            model = self._get_method_repo().create(
                tenant_id=tenant_id, code=code, name=name,
                payment_type=payment_type, **kwargs,
            )
            return self._method_model_to_domain(model)
        method = PaymentMethod(
            tenant_id=tenant_id, code=code, name=name,
            payment_type=PaymentType(payment_type), **kwargs,
        )
        with self._lock:
            self._methods[method.id] = method
        return method

    def update_method(self, method_id: str, tenant_id: str, **kwargs) -> Optional[PaymentMethod]:
        """Update a payment method."""
        if self._use_db:
            model = self._get_method_repo().update(method_id, **kwargs)
            return self._method_model_to_domain(model) if model else None
        method = self.get_method(method_id, tenant_id)
        if not method:
            return None
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(method, key):
                    setattr(method, key, value)
            method.updated_at = datetime.utcnow().isoformat()
        return method

    def toggle_method(self, method_id: str, tenant_id: str) -> Optional[PaymentMethod]:
        """Enable/disable a payment method."""
        method = self.get_method(method_id, tenant_id)
        if not method:
            return None
        new_enabled = not method.enabled
        if self._use_db:
            model = self._get_method_repo().update(method_id, enabled=new_enabled)
            return self._method_model_to_domain(model) if model else None
        with self._lock:
            method.enabled = new_enabled
            method.updated_at = datetime.utcnow().isoformat()
        return method

    def delete_method(self, method_id: str, tenant_id: str) -> bool:
        """Delete a payment method."""
        method = self.get_method(method_id, tenant_id)
        if not method:
            return False
        if self._use_db:
            return self._get_method_repo().delete(method_id)
        with self._lock:
            del self._methods[method_id]
        return True

    # ── PIX Configuration ──────────────────────────────

    def get_pix_config(self, tenant_id: str) -> Optional[PixConfig]:
        """Get PIX configuration for a tenant."""
        if self._use_db:
            model = self._get_pix_repo().get_active_by_tenant(tenant_id)
            return self._pix_model_to_domain(model) if model else None
        for pc in self._pix_configs.values():
            if pc.tenant_id == tenant_id and pc.active:
                return pc
        return None

    def get_pix_configs(self, tenant_id: str) -> List[PixConfig]:
        """Get all PIX configurations for a tenant."""
        if self._use_db:
            models = self._get_pix_repo().list_by_tenant(tenant_id)
            return [self._pix_model_to_domain(m) for m in models]
        return [pc for pc in self._pix_configs.values() if pc.tenant_id == tenant_id]

    def _static_copy_paste(self, key: str, key_type: str,
                           holder_name: str = "", city: str = "") -> str:
        """BR Code estático (sem valor) para a config — '' se chave inválida."""
        if not key:
            return ""
        try:
            from app.domain.payment.pix_service import build_pix_copy_paste
            return build_pix_copy_paste(
                key=key, key_type=key_type,
                merchant_name=holder_name or "GasFlow",
                merchant_city=city or "SAO PAULO",
            )
        except ValueError:
            return ""

    def create_pix_config(self, tenant_id: str, key: str, key_type: str = "RANDOM",
                          holder_name: str = "", **kwargs) -> PixConfig:
        """Create PIX configuration for a tenant."""
        copy_paste = self._static_copy_paste(key, key_type, holder_name, kwargs.get("city", ""))
        if self._use_db:
            model = self._get_pix_repo().create(
                tenant_id=tenant_id, key=key, key_type=key_type,
                holder_name=holder_name, copy_paste_code=copy_paste, **kwargs,
            )
            return self._pix_model_to_domain(model)
        config = PixConfig(
            tenant_id=tenant_id, key=key, key_type=PixKeyType(key_type),
            holder_name=holder_name, copy_paste_code=copy_paste, **kwargs,
        )
        with self._lock:
            self._pix_configs[config.id] = config
        return config

    def update_pix_config(self, config_id: str, tenant_id: str, **kwargs) -> Optional[PixConfig]:
        """Update PIX configuration."""
        if self._use_db:
            model = self._get_pix_repo().get_by_id(config_id)
            if not model or model.tenant_id != tenant_id:
                return None
            # Recompute static BR Code when key/holder/city changed.
            new_key = kwargs.get("key", model.key)
            new_type = kwargs.get("key_type", model.key_type)
            new_holder = kwargs.get("holder_name", model.holder_name)
            new_city = kwargs.get("city", model.city)
            kwargs["copy_paste_code"] = self._static_copy_paste(
                new_key, new_type, new_holder, new_city,
            )
            updated = self._get_pix_repo().update(config_id, **kwargs)
            return self._pix_model_to_domain(updated) if updated else None
        config = self._pix_configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return None
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            config.copy_paste_code = self._static_copy_paste(
                config.key, config.key_type.value, config.holder_name, config.city,
            )
            config.updated_at = datetime.utcnow().isoformat()
        return config

    def delete_pix_config(self, config_id: str, tenant_id: str) -> bool:
        """Delete PIX configuration."""
        if self._use_db:
            model = self._get_pix_repo().get_by_id(config_id)
            if not model or model.tenant_id != tenant_id:
                return False
            return self._get_pix_repo().delete(config_id)
        config = self._pix_configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return False
        with self._lock:
            del self._pix_configs[config_id]
        return True

    # ── Payments ───────────────────────────────────────

    def _pix_txid(self, order_codigo: str) -> str:
        """TXID determinístico para um pedido (máx 25 alfanumérico)."""
        if order_codigo:
            txid = _sanitize_txid(f"GAS{order_codigo}")
            if txid:
                return txid
        return _sanitize_txid(f"GAS{int(time.time() * 1000)}")

    def generate_pix_payload(self, tenant_id: str, amount: float,
                             description: str = "", order_codigo: str = "") -> Optional[dict]:
        """Gera payload PIX (BR Code + QR) com a config ativa do tenant.

        Retorna None se o tenant não tem chave PIX ativa configurada.
        Lança ValueError se amount <= 0.
        """
        if amount <= 0:
            raise ValueError("Valor do PIX deve ser maior que zero")
        config = self.get_pix_config(tenant_id)
        if not config or not config.key:
            return None
        service = PixService()
        return service.generate_payload(
            amount=amount,
            description=description,
            key=config.key,
            key_type=config.key_type.value,
            merchant_name=config.holder_name or "GasFlow",
            merchant_city=config.city or "SAO PAULO",
            txid=self._pix_txid(order_codigo),
        )

    def create_payment(self, tenant_id: str, order_id: str, order_codigo: str,
                       customer_codigo: str, amount: float, method_code: str,
                       **kwargs) -> Payment:
        """Create a payment for an order."""
        method = self.get_method_by_code(method_code, tenant_id)
        method_name = method.name if method else method_code

        pix_key_used = ""
        pix_copy_paste = ""
        if method_code in ("PIX", "PIX_DYNAMIC"):
            pix_config = self.get_pix_config(tenant_id)
            if pix_config and pix_config.key:
                pix_key_used = pix_config.key
                try:
                    payload = self.generate_pix_payload(
                        tenant_id, amount, order_codigo=order_codigo,
                    )
                    if payload:
                        pix_copy_paste = payload["br_code"]
                except ValueError:
                    pass
            elif pix_config:
                pix_key_used = pix_config.key
                pix_copy_paste = pix_config.copy_paste_code

        if self._use_db:
            model = self._get_payment_repo().create(
                tenant_id=tenant_id, order_id=order_id,
                order_codigo=order_codigo, customer_codigo=customer_codigo,
                amount=amount, method_code=method_code, method_name=method_name,
                status="PENDING", pix_key_used=pix_key_used,
                pix_copy_paste=pix_copy_paste, **kwargs,
            )
            return self._payment_model_to_domain(model)

        payment = Payment(
            tenant_id=tenant_id, order_id=order_id,
            order_codigo=order_codigo, customer_codigo=customer_codigo,
            amount=amount, method_code=method_code, method_name=method_name,
            pix_key_used=pix_key_used, pix_copy_paste=pix_copy_paste,
            **kwargs,
        )
        with self._lock:
            self._payments[payment.id] = payment
        return payment

    def get_payment(self, payment_id: str, tenant_id: str) -> Optional[Payment]:
        """Get a specific payment (tenant-scoped)."""
        if self._use_db:
            model = self._get_payment_repo().get_by_id(payment_id)
            if model and model.tenant_id == tenant_id:
                return self._payment_model_to_domain(model)
            return None
        payment = self._payments.get(payment_id)
        if payment and payment.tenant_id == tenant_id:
            return payment
        return None

    def get_payments_for_order(self, order_id: str, tenant_id: str) -> List[Payment]:
        """Get all payments for an order."""
        if self._use_db:
            models = self._get_payment_repo().list_by_order(order_id, tenant_id)
            return [self._payment_model_to_domain(m) for m in models]
        return [p for p in self._payments.values()
                if p.order_id == order_id and p.tenant_id == tenant_id]

    def get_payments_for_tenant(self, tenant_id: str, status: str = None,
                                limit: int = 50) -> List[Payment]:
        """Get payments for a tenant."""
        if self._use_db:
            models = self._get_payment_repo().list_by_tenant(tenant_id, status, limit)
            return [self._payment_model_to_domain(m) for m in models]
        payments = [p for p in self._payments.values() if p.tenant_id == tenant_id]
        if status:
            payments = [p for p in payments if p.status.value == status]
        payments.sort(key=lambda p: p.created_at, reverse=True)
        return payments[:limit]

    def confirm_payment(self, payment_id: str, tenant_id: str,
                        confirmed_by: str = "", notes: str = "") -> Optional[Payment]:
        """Confirm a payment."""
        payment = self.get_payment(payment_id, tenant_id)
        if not payment:
            return None
        if self._use_db:
            now = datetime.utcnow()
            self._get_payment_repo().update(payment_id,
                status="CONFIRMED", confirmed_by=confirmed_by,
                confirmed_at=now, confirmation_notes=notes,
            )
            return self.get_payment(payment_id, tenant_id)
        with self._lock:
            payment.confirm(by=confirmed_by, notes=notes)
        return payment

    def cancel_payment(self, payment_id: str, tenant_id: str,
                       reason: str = "") -> Optional[Payment]:
        """Cancel a payment."""
        payment = self.get_payment(payment_id, tenant_id)
        if not payment:
            return None
        if self._use_db:
            self._get_payment_repo().update(payment_id, status="CANCELLED")
            return self.get_payment(payment_id, tenant_id)
        with self._lock:
            payment.cancel(reason)
        return payment

    def refund_payment(self, payment_id: str, tenant_id: str,
                       reason: str = "") -> Optional[Payment]:
        """Refund a payment."""
        payment = self.get_payment(payment_id, tenant_id)
        if not payment:
            return None
        if self._use_db:
            now = datetime.utcnow()
            self._get_payment_repo().update(payment_id,
                status="REFUNDED", refunded_at=now, refund_reason=reason,
            )
            return self.get_payment(payment_id, tenant_id)
        with self._lock:
            payment.refund(reason)
        return payment

    def get_payment_by_txid(self, txid: str) -> Optional[Payment]:
        """Find a payment by PIX txid (external_id or copy-paste reference).

        Used by the PSP webhook — the caller (bank) does not know the tenant,
        so the lookup is tenant-agnostic. External ids are unique per payment.
        """
        if not txid:
            return None
        if self._use_db:
            model = self._get_payment_repo().find_by_external_id(txid)
            if model:
                return self._payment_model_to_domain(model)
            # Fallback: BR Code copy-paste embeds the txid (payments created
            # before the external_id convention).
            model = self._get_payment_repo().find_by_copy_paste(txid)
            if model:
                return self._payment_model_to_domain(model)
            return None
        with self._lock:
            for payment in self._payments.values():
                if payment.external_id == txid or (
                    payment.pix_copy_paste and txid in payment.pix_copy_paste
                ):
                    return payment
        return None

    def get_order_total_paid(self, order_id: str, tenant_id: str) -> float:
        """Get total amount paid for an order."""
        if self._use_db:
            return self._get_payment_repo().sum_confirmed_by_order(order_id, tenant_id)
        payments = self.get_payments_for_order(order_id, tenant_id)
        return sum(p.amount for p in payments if p.status == PaymentStatus.CONFIRMED)

    def get_payment_summary(self, tenant_id: str) -> Dict:
        """Get payment summary for dashboard."""
        if self._use_db:
            return self._get_payment_repo().summary_by_tenant(tenant_id)
        payments = [p for p in self._payments.values() if p.tenant_id == tenant_id]
        confirmed = [p for p in payments if p.status == PaymentStatus.CONFIRMED]
        pending = [p for p in payments if p.status == PaymentStatus.PENDING]
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
            "total_payments": len(payments),
            "confirmed_count": len(confirmed),
            "pending_count": len(pending),
            "by_method": by_method,
        }


# Singleton
_payment_service: Optional[PaymentService] = None
_lock = threading.Lock()


def get_payment_service() -> PaymentService:
    global _payment_service
    with _lock:
        if _payment_service is None:
            try:
                from sqlalchemy.orm import Session as DBSession
                from app.infrastructure.database.init_db import engine
                db = DBSession(bind=engine)
                _payment_service = PaymentService(db=db)
            except Exception:
                _payment_service = PaymentService()
        return _payment_service
