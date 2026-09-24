"""Audit trail financeiro — auth_audit_log nas mutações da Central Financeira.

Best-effort (nunca derruba a operação de negócio) — mesmo ritual de
`purchase_service._audit` e `contacts.organizer._audit`. O snapshot
antes/depois segue a convenção P0 3.3: sem segredos; Decimal e datetime
entram serializados (str/isoformat) porque a coluna é JSON.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def snapshot_value(value: Any) -> Any:
    """Serializa valores de snapshot para JSON (Decimal → str, datetime → iso)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: snapshot_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [snapshot_value(v) for v in value]
    return value


def log_finance_audit(
    db: Session,
    *,
    tenant_id: str,
    actor_id: str,
    action: str,
    resource: str,
    resource_id: str,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Grava a mutação financeira em auth_audit_log (best-effort)."""
    try:
        from app.infrastructure.repositories.auth_model import AuthAuditModel

        db.add(
            AuthAuditModel(
                id=str(uuid.uuid4()),
                actor_id=actor_id or "",
                actor_type="USER",
                tenant_id=tenant_id or "default",
                action=action,
                resource=resource,
                resource_id=str(resource_id),
                result="SUCCESS",
                timestamp=datetime.utcnow(),
                ip_address="",
                user_agent="",
                platform="web",
                before_json=snapshot_value(before) if before is not None else None,
                after_json=snapshot_value(after) if after is not None else None,
                details=snapshot_value(details) if details is not None else None,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover — audit nunca derruba o negócio
        db.rollback()
        logger.warning("finance.audit_failed", extra={"resource_id": resource_id, "action": action})
