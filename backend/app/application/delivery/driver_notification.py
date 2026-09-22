"""
Driver Assignment Notification — F3

Envia o "zap do entregador" quando uma entrega é atribuída, reaproveitando
o executor de automações existente (ExecutionProcessor): a notification é
gravada como AutomationExecution PENDING e o fluxo já existente
(POST /whatsapp-automation/process-pending ou o poller em background,
AUTOMATION_POLL_SECONDS) envia via ponte WhatsApp com pacing/anti-ban.
Nenhuma fila paralela é criada.

Idempotência: 1 execução por (delivery_id, driver_id). Reatribuição para o
mesmo entregador não duplica; mudança de entregador cria nova execução.
A dedup usa o trigger_context da execução (tipo + chaves), consultando as
executions do rule dedicado. (Fallback F5 do plano — o executor não tem
constraint nativa de unicidade; a checagem por list_executions cobre o caso
prático de atribuição serial.)
"""

import logging
from typing import Any, Dict, Optional

from app.domain.whatsapp_automation.entity import (
    AutomationExecution,
    AutomationRule,
    AutomationStatus,
    AutomationTriggerType,
    ExecutionStatus,
)

logger = logging.getLogger("gasflow.driver_notification")

# Identidade fixa da regra de notificação de atribuição (criada on-demand,
# uma por tenant, e reaproveitada em todas as atribuições).
RULE_NAME = "driver_assignment_notification"
RULE_DESCRIPTION = (
    "Zap do entregador na atribuição de entrega (F3). Disparado pelo AssignmentService; envio pelo executor existente."
)
DEFAULT_TEMPLATE = (
    "Olá {{driver_name}}! Nova entrega atribuída: pedido {{order_ref}} "
    "para {{customer_name}} — {{address}}. Bom trabalho!"
)
VARIABLES = ("{{driver_name}}", "{{order_ref}}", "{{customer_name}}", "{{address}}")

# Nomes no nível do módulo para permitir monkeypatch nos testes.
from app.infrastructure.database.init_db import engine as _engine  # noqa: E402
from app.infrastructure.repositories.whatsapp_automation_repository import (  # noqa: E402
    SQLAlchemyAutomationRepository,
)
from app.application.whatsapp_automation.executor import ExecutionProcessor  # noqa: E402


def load_delivery_context(automation_repo, delivery_id: str, tenant_id: str) -> Dict[str, str]:
    """
    F3.5: extrai order_ref/customer_name/address da delivery persistida.

    Falha (delivery inexistente ou erro de infra) NUNCA quebra a notificação:
    retorna placeholders vazios + log warning — mensagem segue com o que houver.
    """
    ctx = {"order_ref": "", "customer_name": "", "address": ""}
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository,
        )

        repo = SQLAlchemyDeliveryPersistenceRepository(automation_repo.db, tenant_id)
        record = repo.get_delivery(delivery_id)
        if record is None:
            logger.warning(
                "driver_notification_delivery_not_found",
                extra={"delivery_id": delivery_id, "tenant": tenant_id},
            )
            return ctx
        ctx["order_ref"] = str(record.order_id or "")
        ctx["customer_name"] = str(record.customer_name or "")
        parts = [record.address_street, record.address_number, record.address_neighborhood]
        ctx["address"] = ", ".join(p for p in (str(x or "").strip() for x in parts) if p)
    except Exception:
        logger.warning("driver_notification_delivery_lookup_failed", exc_info=True)
    return ctx


def drain_pending_notifications(tenant_id: str = "default", limit: int = 10) -> Dict[str, Any]:
    """
    F3.5: drena a fila de automações uma vez (envio imediato pós-atribuição).

    Reaproveita o ExecutionProcessor existente (pacing/anti-ban/audit) —
    não cria fila paralela. Garante o critério "zap em <30s" mesmo com
    AUTOMATION_POLL_SECONDS=0. Erros são logados, nunca propagados.
    """
    import asyncio

    from sqlalchemy.orm import Session as _Session

    session = _Session(bind=_engine)
    try:
        repo = SQLAlchemyAutomationRepository(session, tenant_id)
        processor = ExecutionProcessor(repo)
        try:
            # Pode já haver um event loop rodando (assign chamado de dentro
            # de um handler async, ex.: FastAPI com session async) — nesse
            # caso roda a corotina no loop existente; senão, cria o seu.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, processor.process_pending_executions(limit=limit)).result(
                        timeout=25
                    )
            return asyncio.run(processor.process_pending_executions(limit=limit))
        except Exception:
            logger.warning("driver_notification_drain_failed", exc_info=True)
            return {"processed": 0, "sent": 0, "failed": 0, "errors": []}
    finally:
        session.close()


def render_assignment_message(payload: Dict[str, Any], template: str = DEFAULT_TEMPLATE) -> str:
    """Renderiza o template da notificação com o payload da atribuição."""
    result = template
    for var in VARIABLES:
        key = var.strip("{} ")
        value = str(payload.get(key, "") or "")
        result = result.replace(var, value)
    return result


class DriverAssignmentNotifier:
    """Enfila a notificação WhatsApp do entregador na atribuição de entrega."""

    def __init__(self, automation_repo):
        self.automation_repo = automation_repo

    # ── Rule dedicada (on-demand, 1 por tenant) ───────────────

    def _get_or_create_rule(self) -> Optional[AutomationRule]:
        """Retorna a rule de notificação de atribuição, criando se necessário."""
        for rule in self.automation_repo.list_rules(status=AutomationStatus.ACTIVE.value):
            if rule.name == RULE_NAME:
                return rule
        # Pode existir em outro status (ex.: DRAFT criado e pausado) — procura geral
        for rule in self.automation_repo.list_rules():
            if rule.name == RULE_NAME:
                return rule
        return self.automation_repo.create_rule(
            AutomationRule(
                name=RULE_NAME,
                description=RULE_DESCRIPTION,
                trigger_type=AutomationTriggerType.MANUAL,
                status=AutomationStatus.ACTIVE,
                message_template=DEFAULT_TEMPLATE,
                account_id="primary",
                requires_approval=False,
            )
        )

    # ── Idempotência por (delivery_id, driver_id) ─────────────

    def _exists_execution(self, rule_id: int, delivery_id: str, driver_codigo: str) -> bool:
        for exec_entity in self.automation_repo.list_executions(rule_id=rule_id, limit=500):
            ctx = exec_entity.trigger_context or {}
            if (
                ctx.get("type") == RULE_NAME
                and ctx.get("delivery_id") == delivery_id
                and ctx.get("driver_codigo") == driver_codigo
            ):
                return True
            if exec_entity.customer_codigo == f"DRIVER:{driver_codigo}" and (ctx.get("delivery_id") == delivery_id):
                return True
        return False

    # ── API principal ─────────────────────────────────────────

    def notify_assignment(
        self,
        delivery_id: str,
        driver_codigo: str,
        payload: Optional[Dict[str, Any]] = None,
        template: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Enfila 1 execução de notificação para (delivery_id, driver_codigo).

        payload esperado (o que houver é interpolado no template):
            driver_name, order_ref, customer_name, address, customer_phone
        """
        payload = payload or {}
        # F3.5: completa o payload com dados da delivery persistida
        # (order_ref, customer_name, address) — placeholders vazios se ausente.
        tenant_id = getattr(self.automation_repo, "tenant_id", "default") or "default"
        for key, value in load_delivery_context(self.automation_repo, delivery_id, tenant_id).items():
            if not payload.get(key):
                payload[key] = value
        rule = self._get_or_create_rule()
        if not rule or not rule.id:
            return {"success": False, "error": "rule_unavailable"}

        if self._exists_execution(rule.id, delivery_id, driver_codigo):
            return {"success": True, "idempotent_replay": True, "created": False}

        message = render_assignment_message(payload, template or rule.message_template)
        execution = AutomationExecution(
            rule_id=rule.id,
            customer_codigo=f"DRIVER:{driver_codigo}",
            customer_nome=str(payload.get("driver_name", "") or ""),
            customer_phone=str(payload.get("customer_phone", "") or ""),
            message_text=message,
            status=ExecutionStatus.PENDING,
            trigger_context={
                "type": RULE_NAME,
                "delivery_id": delivery_id,
                "driver_codigo": driver_codigo,
                **{k: v for k, v in payload.items() if k not in ("customer_phone",)},
            },
        )
        created = self.automation_repo.create_execution(execution)
        self.automation_repo.update_rule(
            rule.id,
            total_executions=(rule.total_executions or 0) + 1,
        )
        logger.info(
            "driver_notification.queued",
            extra={"delivery_id": delivery_id, "driver": driver_codigo, "execution_id": created.id},
        )
        return {"success": True, "created": True, "execution_id": created.id}
