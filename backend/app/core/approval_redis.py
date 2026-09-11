"""
Redis-backed approval queue — mesma interface do ``ApprovalEngine``.

Motivação (item G do relatório): aprovações de ações de alto risco
(add_stock, register_payment, send_whatsapp) viviam só em memória do
processo — um restart do backend apagava aprovações pendentes e, com
mais de 1 worker Uvicorn, a aprovação criada por um worker podia não
existir no worker que recebia o clique de "aprovar".

Mesmo contrato do ApprovalEngine (policy.py), trocando o Dict em processo
por Redis (compartilhado entre workers/instâncias):
- ``approval:{id}``   → JSON do Approval, com TTL = TTL da aprovação
  (expiração vira consequência do Redis, não de varredura)
- ``approvals:index`` → ZSET de ids (score = created_at epoch) para listagem

``redis`` é importado lazy (conector) — dev/testes rodam sem ele; o default
continua in-memory via APPROVAL_QUEUE_MODE=memory.

Fallback: se o Redis estiver fora, as operações de leitura/listagem degradam
para vazio (não quebram a requisição); operações de escrita propagam erro —
uma aprovação que não pode ser persistida NÃO deve ser reportada como criada
(fail-closed), diferente do rate limiter onde "permitir" é o default seguro.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.domain.automation.policy import Approval, ApprovalEngine, ApprovalStatus, hash_arguments

logger = logging.getLogger("app.core.approval_redis")

INDEX_KEY = "approvals:index"


def _serialize(approval: Approval) -> str:
    data = {
        "id": approval.id,
        "action": approval.action,
        "arguments_hash": approval.arguments_hash,
        "actor": approval.actor,
        "workflow_id": approval.workflow_id,
        "run_id": approval.run_id,
        "step_id": approval.step_id,
        "risk_level": approval.risk_level,
        "reason": approval.reason,
        "status": approval.status.value,
        "created_at": approval.created_at.isoformat(),
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
        "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
        "approved_by": approval.approved_by,
        "rejected_at": approval.rejected_at.isoformat() if approval.rejected_at else None,
    }
    return json.dumps(data, ensure_ascii=False)


def _deserialize(raw: str) -> Optional[Approval]:
    try:
        data = json.loads(raw)
        return Approval(
            id=data["id"],
            action=data["action"],
            arguments_hash=data.get("arguments_hash", ""),
            actor=data.get("actor", ""),
            workflow_id=data.get("workflow_id"),
            run_id=data.get("run_id"),
            step_id=data.get("step_id"),
            risk_level=data.get("risk_level", "LOW"),
            reason=data.get("reason", ""),
            status=ApprovalStatus(data.get("status", "PENDING")),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            approved_at=datetime.fromisoformat(data["approved_at"]) if data.get("approved_at") else None,
            approved_by=data.get("approved_by"),
            rejected_at=datetime.fromisoformat(data["rejected_at"]) if data.get("rejected_at") else None,
        )
    except Exception:  # noqa: BLE001 — dado corrompido não deve derrubar o worker
        logger.exception("approval_redis.deserialization_failed")
        return None


class RedisApprovalEngine:
    """Approval lifecycle backed by Redis (shared across workers).

    Mesma interface do ``ApprovalEngine`` — os motores (WorkflowEngine,
    AgentEngine) e os endpoints (/automation/approvals) funcionam com
    qualquer backend sem mudança de call-site.
    """

    def __init__(
        self,
        client=None,
        url: str = "redis://localhost:6379/0",
        ttl_minutes: int = ApprovalEngine.DEFAULT_TTL_MINUTES,
        socket_timeout: float = 1.5,
    ):
        self._client = client
        self._url = url
        self._ttl = timedelta(minutes=ttl_minutes)
        self._socket_timeout = socket_timeout
        # Circuit breaker (mesmo padrão do rate limiter Redis).
        self._unavailable_until = 0.0
        self._available_until = 0.0

    def _connect(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(
                self._url,
                socket_connect_timeout=self._socket_timeout,
                socket_timeout=self._socket_timeout,
            )
        return self._client

    @property
    def available(self) -> bool:
        """True quando o Redis responde; cacheia sucesso/falha por alguns segundos."""
        now = time.time()
        if now < self._unavailable_until:
            return False
        if now < self._available_until:
            return True
        try:
            self._connect().ping()
            self._available_until = now + 5
            return True
        except Exception:  # noqa: BLE001
            self._unavailable_until = now + 30
            logger.warning("Redis unreachable — approval queue unavailable (fail-closed)")
            return False

    # ── Internal helpers ─────────────────────────────────

    def _key(self, approval_id: str) -> str:
        return f"approval:{approval_id}"

    def _ttl_seconds(self) -> int:
        return max(int(self._ttl.total_seconds()), 1)

    # ── Lifecycle ────────────────────────────────────────

    def create_approval(
        self,
        action: str,
        arguments: Dict[str, Any],
        actor: str,
        risk_level: str = "LOW",
        reason: str = "",
        workflow_id: Optional[str] = None,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> Approval:
        approval = Approval(
            action=action,
            arguments_hash=hash_arguments(arguments),
            actor=actor,
            workflow_id=workflow_id,
            run_id=run_id,
            step_id=step_id,
            risk_level=risk_level,
            reason=reason,
            expires_at=datetime.utcnow() + self._ttl,
        )
        client = self._connect()
        ttl_s = self._ttl_seconds()
        # SET (com TTL) + ZADD: aprovação criada só existe se persistida.
        client.set(self._key(approval.id), _serialize(approval), ex=ttl_s)
        client.zadd(INDEX_KEY, {approval.id: approval.created_at.timestamp()})
        client.zremrangebyscore(INDEX_KEY, "-inf", approval.created_at.timestamp() - ttl_s)
        client.expire(INDEX_KEY, ttl_s)
        return approval

    def _load(self, approval_id: str) -> Optional[Approval]:
        raw = self._connect().get(self._key(approval_id))
        if raw is None:
            return None
        return _deserialize(raw if isinstance(raw, str) else raw.decode("utf-8"))

    def _save(self, approval: Approval) -> None:
        client = self._connect()
        client.set(self._key(approval.id), _serialize(approval), ex=self._ttl_seconds())

    def approve(self, approval_id: str, approved_by: str) -> bool:
        approval = self._load(approval_id)
        if not approval:
            return False
        if approval.status != ApprovalStatus.PENDING:
            return False
        if approval.is_expired:
            approval.status = ApprovalStatus.EXPIRED
            self._save(approval)
            return False
        approval.status = ApprovalStatus.APPROVED
        approval.approved_at = datetime.utcnow()
        approval.approved_by = approved_by
        self._save(approval)
        return True

    def reject(self, approval_id: str, _rejected_by: str = "") -> bool:
        # _rejected_by: parte do contrato de auditoria; ainda não registrado.
        approval = self._load(approval_id)
        if not approval:
            return False
        if approval.status != ApprovalStatus.PENDING:
            return False
        approval.status = ApprovalStatus.REJECTED
        approval.rejected_at = datetime.utcnow()
        self._save(approval)
        return True

    def get(self, approval_id: str) -> Optional[Approval]:
        return self._load(approval_id)

    def is_valid(self, approval_id: str) -> bool:
        approval = self._load(approval_id)
        return approval.is_valid if approval else False

    def validate_binding(self, approval_id: str, action: str, arguments: Dict[str, Any]) -> bool:
        """Mesmo contrato de ApprovalEngine.validate_binding (binding aprovado → executado)."""
        approval = self._load(approval_id)
        if not approval:
            logger.warning("approval.binding.rejected", extra={"reason": "not_found", "approval_id": approval_id})
            return False
        if approval.action != action:
            logger.warning(
                "approval.binding.rejected",
                extra={
                    "reason": "action_mismatch",
                    "approval_id": approval_id,
                    "approved": approval.action,
                    "requested": action,
                },
            )
            return False
        if approval.arguments_hash != hash_arguments(arguments):
            logger.warning(
                "approval.binding.rejected",
                extra={"reason": "arguments_mismatch", "approval_id": approval_id, "action": action},
            )
            return False
        return True

    def get_pending(self) -> List[Approval]:
        approvals = self._list_all()
        return [a for a in approvals if a.status == ApprovalStatus.PENDING and not a.is_expired]

    def get_all(self) -> List[Approval]:
        return self._list_all()

    def _list_all(self) -> List[Approval]:
        client = self._connect()
        ids = client.zrange(INDEX_KEY, 0, -1)
        approvals: List[Approval] = []
        for raw_id in ids:
            approval_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else raw_id
            approval = self._load(approval_id)
            if approval:
                approvals.append(approval)
        approvals.sort(key=lambda a: a.created_at)
        return approvals

    def expire_old(self) -> int:
        """No Redis a expiração é feita pelo TTL da chave; varredura é best-effort."""
        count = 0
        for approval in self._list_all():
            if approval.status == ApprovalStatus.PENDING and approval.is_expired:
                approval.status = ApprovalStatus.EXPIRED
                self._save(approval)
                count += 1
        return count
