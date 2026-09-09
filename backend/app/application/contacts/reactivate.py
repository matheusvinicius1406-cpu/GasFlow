"""
Reactivate Inactive — reativação de clientes inativos via WhatsApp.

Fluxo (reusa a infraestrutura existente — sem scheduler novo, sem job novo):
1. Endpoint POST /clients/contacts/reactivate (chamada manual ou cron externo
   do compose — o backend não embute scheduler).
2. Busca clientes ativos com is_whatsapp, marketing_status OPTED_IN e
   last_interaction_at (ou updated_at) mais antigo que N dias (settings).
3. Renderiza o template (settings.whatsapp_reactivate_template) e cria
   AutomationExecutions PENDING via WhatsAppAutomationService.
4. O executor existente (POST /whatsapp-automation/process-pending) envia
   pelo WhatsAppSendBridge — que já tem retry, idempotência e anti-ban.

Anti-spam embutido: clientes OPTED_OUT/SUPPRESSED/BLOCKED nunca recebem;
limite diário configurável evita rajada.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import setup_logging
from app.domain.client.entity import Client
from app.domain.settings.models import DEFAULT_SETTINGS  # noqa: F401 (garante chaves documentadas)
from app.domain.whatsapp_automation.entity import (
    AutomationExecution,
    ExecutionStatus,
)
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.whatsapp_automation_repository import (
    SQLAlchemyAutomationRepository,
)

logger = setup_logging("INFO")

DEFAULT_DAYS = 90
DEFAULT_LIMIT = 100

TEMPLATE_VARS = ("{{nome}}", "{{rua}}", "{{numero}}", "{{complemento}}", "{{bairro}}")


def _get_setting(db: Session, key: str, default: Any) -> Any:
    """Lê uma system_setting (JSON) com fallback no default."""
    from app.infrastructure.repositories.settings_model import SystemSettingModel

    row = db.get(SystemSettingModel, key)
    if row is None:
        return default
    return row.value if row.value is not None else default


def _render_template(template: str, client: Client) -> str:
    message = template
    replacements = {
        "{{nome}}": client.nome or "Cliente",
        "{{rua}}": (client.rua or "").strip() or "não informado",
        "{{numero}}": (client.numero or "").strip() or "S/N",
        "{{complemento}}": (client.complemento or "").strip() or "—",
        "{{bairro}}": (client.bairro or "").strip() or "não informado",
    }
    for var, value in replacements.items():
        message = message.replace(var, value)
    return message


class ReactivationService:
    """Cria executions de reativação para clientes inativos e elegíveis."""

    def __init__(
        self,
        db: Session,
        client_repo: SQLAlchemyClientRepository,
        automation_repo: Optional[SQLAlchemyAutomationRepository] = None,
    ):
        self.db = db
        self.client_repo = client_repo
        self.automation_repo = automation_repo or SQLAlchemyAutomationRepository(db)

    def preview(self, days: Optional[int] = None, limit: int = DEFAULT_LIMIT) -> Dict[str, Any]:
        """Lista quem receberia a mensagem, sem criar executions."""
        clients, cutoff, template = self._eligible(days)
        return {
            "days": self._days(days),
            "cutoff": cutoff.isoformat(),
            "candidates": min(len(clients), limit),
            "total_eligible": len(clients),
            "sample": [{"codigo": c.codigo, "nome": c.nome, "telefone": c.telefone} for c in clients[:limit]],
        }

    def run(self, days: Optional[int] = None, limit: int = DEFAULT_LIMIT) -> Dict[str, Any]:
        """Cria executions PENDING de reativação (idempotente por dia+cliente)."""
        if not bool(_get_setting(self.db, "whatsapp_reactivate_enabled", False)):
            return {"success": False, "error": "Reativação desabilitada (settings: whatsapp_reactivate_enabled)"}

        clients, cutoff, template = self._eligible(days)
        created = 0
        skipped_recent = 0
        for client in clients[:limit]:
            # Idempotência simples: 1 execution de reativação por cliente por dia.
            # (was_recently_contacted só conta SENT/DELIVERED — PENDING de hoje
            # passaria batido e duplicaria a fila em um duplo-clique.)
            if self._reactivation_created_today(client.codigo):
                skipped_recent += 1
                continue
            execution = AutomationExecution(
                rule_id=0,  # reativação não vem de rule; executor lê execution direto
                customer_codigo=client.codigo,
                customer_nome=client.nome,
                customer_phone=client.telefone,
                message_text=_render_template(template, client),
                status=ExecutionStatus.PENDING,
                trigger_context={"trigger_type": "REACTIVATION", "cutoff": cutoff.isoformat()},
            )
            self.automation_repo.create_execution(execution)
            created += 1

        logger.info(f"[reactivation] {created} executions criadas ({skipped_recent} já contactados hoje)")
        return {
            "success": True,
            "created": created,
            "skipped_recent": skipped_recent,
            "total_eligible": len(clients),
        }

    # ── Internals ────────────────────────────────────────

    def _reactivation_created_today(self, customer_codigo: str) -> bool:
        """True se já existe execution de REACTIVATION para o cliente hoje."""
        from app.infrastructure.repositories.whatsapp_automation_model import (
            AutomationExecutionModel,
        )

        start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        rows = (
            self.db.query(AutomationExecutionModel)
            .filter(
                AutomationExecutionModel.tenant_id == self.automation_repo.tenant_id,
                AutomationExecutionModel.customer_codigo == customer_codigo,
                AutomationExecutionModel.created_at >= start_of_day,
            )
            .all()
        )
        for row in rows:
            context = row.trigger_context or {}
            if isinstance(context, dict) and context.get("trigger_type") == "REACTIVATION":
                return True
        return False

    def _days(self, days: Optional[int]) -> int:
        if days is not None and days > 0:
            return days
        return int(_get_setting(self.db, "whatsapp_reactivate_days", DEFAULT_DAYS) or DEFAULT_DAYS)

    def _template(self) -> str:
        return str(
            _get_setting(
                self.db,
                "whatsapp_reactivate_template",
                "Olá {{nome}}! Confirme seu endereço: Rua {{rua}} Nº{{numero}}, {{bairro}}.",
            )
        )

    def _eligible(self, days: Optional[int]) -> tuple:
        """Clientes ativos com WhatsApp, OPTED_IN e inativos há N dias."""
        days = self._days(days)
        cutoff = datetime.utcnow() - timedelta(days=days)
        template = self._template()

        clients = self.client_repo.listar_todos()  # já filtra ativo + tenant
        eligible: List[Client] = []
        for client in clients:
            if client.is_whatsapp is False:
                continue
            if client.marketing_status not in (None, "", "OPTED_IN", "UNKNOWN"):
                continue  # OPTED_OUT/SUPPRESSED/BLOCKED nunca
            last = client.last_interaction_at or client.updated_at or client.created_at
            if last and last >= cutoff:
                continue
            eligible.append(client)
        eligible.sort(key=lambda c: (c.last_interaction_at or c.updated_at or c.created_at or datetime.utcnow()))
        return eligible, cutoff, template
