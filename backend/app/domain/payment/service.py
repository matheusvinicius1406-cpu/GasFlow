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

from app.domain.payment.models import (
    Payment, PaymentMethod, PixConfig,
    PaymentStatus, PaymentType, PixKeyType,
)


class PaymentService:
    """Payment service with in-memory storage (development)."""

    def __init__(self):
        self._payments: Dict[str, Payment] = {}
        self._methods: Dict[str, PaymentMethod] = {}
        self._pix_configs: Dict[str, PixConfig] = {}
        self._lock = threading.Lock()

    # ── Payment Methods ────────────────────────────────

    def get_methods(self, tenant_id: str) -> List[PaymentMethod]:
        """Get all payment methods for a tenant."""
        return [
            m for m in self._methods.values()
            if m.tenant_id == tenant_id
        ]

    def get_enabled_methods(self, tenant_id: str) -> List[PaymentMethod]:
        """Get enabled payment methods for a tenant."""
        return [
            m for m in self._methods.values()
            if m.tenant_id == tenant_id and m.enabled
        ]

    def get_method(self, method_id: str, tenant_id: str) -> Optional[PaymentMethod]:
        """Get a specific payment method (tenant-scoped)."""
        method = self._methods.get(method_id)
        if method and method.tenant_id == tenant_id:
            return method
        return None

    def get_method_by_code(self, code: str, tenant_id: str) -> Optional[PaymentMethod]:
        """Get payment method by code (tenant-scoped)."""
        for m in self._methods.values():
            if m.tenant_id == tenant_id and m.code == code:
                return m
        return None

    def create_method(self, tenant_id: str, code: str, name: str,
                      payment_type: str = "CUSTOM", **kwargs) -> PaymentMethod:
        """Create a payment method for a tenant."""
        method = PaymentMethod(
            tenant_id=tenant_id,
            code=code,
            name=name,
            payment_type=PaymentType(payment_type),
            **kwargs,
        )
        with self._lock:
            self._methods[method.id] = method
        return method

    def update_method(self, method_id: str, tenant_id: str, **kwargs) -> Optional[PaymentMethod]:
        """Update a payment method."""
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
        with self._lock:
            method.enabled = not method.enabled
            method.updated_at = datetime.utcnow().isoformat()
        return method

    def delete_method(self, method_id: str, tenant_id: str) -> bool:
        """Delete a payment method."""
        method = self.get_method(method_id, tenant_id)
        if not method:
            return False
        with self._lock:
            del self._methods[method_id]
        return True

    # ── PIX Configuration ──────────────────────────────

    def get_pix_config(self, tenant_id: str) -> Optional[PixConfig]:
        """Get PIX configuration for a tenant."""
        for pc in self._pix_configs.values():
            if pc.tenant_id == tenant_id and pc.active:
                return pc
        return None

    def get_pix_configs(self, tenant_id: str) -> List[PixConfig]:
        """Get all PIX configurations for a tenant."""
        return [
            pc for pc in self._pix_configs.values()
            if pc.tenant_id == tenant_id
        ]

    def create_pix_config(self, tenant_id: str, key: str, key_type: str = "RANDOM",
                          holder_name: str = "", **kwargs) -> PixConfig:
        """Create PIX configuration for a tenant."""
        config = PixConfig(
            tenant_id=tenant_id,
            key=key,
            key_type=PixKeyType(key_type),
            holder_name=holder_name,
            **kwargs,
        )
        with self._lock:
            self._pix_configs[config.id] = config
        return config

    def update_pix_config(self, config_id: str, tenant_id: str, **kwargs) -> Optional[PixConfig]:
        """Update PIX configuration."""
        config = self._pix_configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return None
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            config.updated_at = datetime.utcnow().isoformat()
        return config

    def delete_pix_config(self, config_id: str, tenant_id: str) -> bool:
        """Delete PIX configuration."""
        config = self._pix_configs.get(config_id)
        if not config or config.tenant_id != tenant_id:
            return False
        with self._lock:
            del self._pix_configs[config_id]
        return True

    # ── Payments ───────────────────────────────────────

    def create_payment(self, tenant_id: str, order_id: str, order_codigo: str,
                       customer_codigo: str, amount: float, method_code: str,
                       **kwargs) -> Payment:
        """Create a payment for an order."""
        method = self.get_method_by_code(method_code, tenant_id)

        payment = Payment(
            tenant_id=tenant_id,
            order_id=order_id,
            order_codigo=order_codigo,
            customer_codigo=customer_codigo,
            amount=amount,
            method_code=method_code,
            method_name=method.name if method else method_code,
            **kwargs,
        )

        # Get PIX config if PIX payment
        if method_code in ("PIX", "PIX_DYNAMIC"):
            pix_config = self.get_pix_config(tenant_id)
            if pix_config:
                payment.pix_key_used = pix_config.key
                payment.pix_copy_paste = pix_config.copy_paste_code

        with self._lock:
            self._payments[payment.id] = payment
        return payment

    def get_payment(self, payment_id: str, tenant_id: str) -> Optional[Payment]:
        """Get a specific payment (tenant-scoped)."""
        payment = self._payments.get(payment_id)
        if payment and payment.tenant_id == tenant_id:
            return payment
        return None

    def get_payments_for_order(self, order_id: str, tenant_id: str) -> List[Payment]:
        """Get all payments for an order."""
        return [
            p for p in self._payments.values()
            if p.order_id == order_id and p.tenant_id == tenant_id
        ]

    def get_payments_for_tenant(self, tenant_id: str, status: str = None,
                                limit: int = 50) -> List[Payment]:
        """Get payments for a tenant."""
        payments = [
            p for p in self._payments.values()
            if p.tenant_id == tenant_id
        ]
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
        with self._lock:
            payment.confirm(by=confirmed_by, notes=notes)
        return payment

    def cancel_payment(self, payment_id: str, tenant_id: str,
                       reason: str = "") -> Optional[Payment]:
        """Cancel a payment."""
        payment = self.get_payment(payment_id, tenant_id)
        if not payment:
            return None
        with self._lock:
            payment.cancel(reason)
        return payment

    def refund_payment(self, payment_id: str, tenant_id: str,
                       reason: str = "") -> Optional[Payment]:
        """Refund a payment."""
        payment = self.get_payment(payment_id, tenant_id)
        if not payment:
            return None
        with self._lock:
            payment.refund(reason)
        return payment

    def get_order_total_paid(self, order_id: str, tenant_id: str) -> float:
        """Get total amount paid for an order."""
        payments = self.get_payments_for_order(order_id, tenant_id)
        return sum(p.amount for p in payments if p.status == PaymentStatus.CONFIRMED)

    def get_payment_summary(self, tenant_id: str) -> Dict:
        """Get payment summary for dashboard."""
        payments = [
            p for p in self._payments.values()
            if p.tenant_id == tenant_id
        ]
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
            _payment_service = PaymentService()
        return _payment_service
