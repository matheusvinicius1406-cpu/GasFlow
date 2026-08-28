"""
Payment Domain Models — GasFlow

Defines payment methods, payment lifecycle, and PIX configuration.
Each tenant configures their own payment methods and PIX keys.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class PaymentType(str, Enum):
    CASH = "CASH"
    PIX = "PIX"
    PIX_DYNAMIC = "PIX_DYNAMIC"
    DEBIT_CARD = "DEBIT_CARD"
    CREDIT_CARD = "CREDIT_CARD"
    TRANSFER = "TRANSFER"
    BANK_SLIP = "BANK_SLIP"
    ON_ACCOUNT = "ON_ACCOUNT"
    CUSTOM = "CUSTOM"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PixKeyType(str, Enum):
    CPF = "CPF"
    CNPJ = "CNPJ"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    RANDOM = "RANDOM"
    OTHER = "OTHER"


@dataclass
class PaymentMethod:
    """Configurable payment method per tenant."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "default"
    code: str = ""  # e.g., "PIX", "CASH"
    name: str = ""
    payment_type: PaymentType = PaymentType.CUSTOM
    enabled: bool = True
    display_order: int = 0
    requires_confirmation: bool = False  # Manual confirmation needed
    description: str = ""

    # Fees and discounts
    fee_type: str = "NONE"  # NONE, PERCENTAGE, FIXED
    fee_value: float = 0.0
    discount_type: str = "NONE"  # NONE, PERCENTAGE, FIXED
    discount_value: float = 0.0

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def calculate_amount(self, base_amount: float) -> float:
        """Calculate final amount after fees and discounts."""
        amount = base_amount

        # Apply discount
        if self.discount_type == "PERCENTAGE":
            amount -= amount * (self.discount_value / 100)
        elif self.discount_type == "FIXED":
            amount -= self.discount_value

        # Apply fee
        if self.fee_type == "PERCENTAGE":
            amount += amount * (self.fee_value / 100)
        elif self.fee_type == "FIXED":
            amount += self.fee_value

        return max(0, round(amount, 2))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "code": self.code,
            "name": self.name,
            "payment_type": self.payment_type.value,
            "enabled": self.enabled,
            "display_order": self.display_order,
            "requires_confirmation": self.requires_confirmation,
            "description": self.description,
            "fee_type": self.fee_type,
            "fee_value": self.fee_value,
            "discount_type": self.discount_type,
            "discount_value": self.discount_value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PixConfig:
    """PIX configuration per tenant."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "default"
    key: str = ""  # PIX key value
    key_type: PixKeyType = PixKeyType.RANDOM
    holder_name: str = ""
    holder_document: str = ""  # CPF/CNPJ
    institution: str = ""  # Bank name
    city: str = ""
    copy_paste_code: str = ""  # Static PIX copy-paste
    active: bool = True

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "key": self.key,
            "key_type": self.key_type.value,
            "holder_name": self.holder_name,
            "holder_document": self.holder_document,
            "institution": self.institution,
            "city": self.city,
            "copy_paste_code": self.copy_paste_code,
            "active": self.active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Payment:
    """Payment record for an order."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "default"
    order_id: str = ""
    order_codigo: str = ""
    customer_codigo: str = ""

    # Payment details
    amount: float = 0.0
    method_code: str = ""  # References PaymentMethod.code
    method_name: str = ""
    status: PaymentStatus = PaymentStatus.PENDING

    # PIX specific
    pix_key_used: str = ""
    pix_copy_paste: str = ""

    # Confirmation
    confirmed_by: str = ""  # user_id who confirmed
    confirmed_at: Optional[str] = None
    confirmation_notes: str = ""

    # Refund
    refunded_at: Optional[str] = None
    refund_reason: str = ""

    # External provider
    provider: str = ""  # e.g., "manual", "mercadopago"
    external_id: str = ""
    provider_status: str = ""

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def confirm(self, by: str = "", notes: str = "") -> bool:
        """Confirm payment (manual or automatic)."""
        if self.status != PaymentStatus.PENDING:
            return False
        self.status = PaymentStatus.CONFIRMED
        self.confirmed_by = by
        self.confirmed_at = datetime.utcnow().isoformat()
        self.confirmation_notes = notes
        self.updated_at = datetime.utcnow().isoformat()
        return True

    def cancel(self, reason: str = "") -> bool:
        """Cancel payment."""
        if self.status in (PaymentStatus.CONFIRMED, PaymentStatus.REFUNDED):
            return False
        self.status = PaymentStatus.CANCELLED
        self.updated_at = datetime.utcnow().isoformat()
        return True

    def refund(self, reason: str = "") -> bool:
        """Refund payment."""
        if self.status != PaymentStatus.CONFIRMED:
            return False
        self.status = PaymentStatus.REFUNDED
        self.refunded_at = datetime.utcnow().isoformat()
        self.refund_reason = reason
        self.updated_at = datetime.utcnow().isoformat()
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "order_id": self.order_id,
            "order_codigo": self.order_codigo,
            "customer_codigo": self.customer_codigo,
            "amount": self.amount,
            "method_code": self.method_code,
            "method_name": self.method_name,
            "status": self.status.value,
            "pix_key_used": self.pix_key_used,
            "pix_copy_paste": self.pix_copy_paste,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "confirmation_notes": self.confirmation_notes,
            "refunded_at": self.refunded_at,
            "refund_reason": self.refund_reason,
            "provider": self.provider,
            "external_id": self.external_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
