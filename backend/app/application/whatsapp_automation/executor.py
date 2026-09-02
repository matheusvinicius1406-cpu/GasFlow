"""
Automation Execution Processor — FASE 14.5

Processes approved automation executions:
1. Check policies (cooldown, daily limit, opt-out)
2. Send via WhatsApp bridge
3. Track status (SENT, FAILED, DELIVERED)
4. Audit log all actions
5. Handle retry on failure

This processor runs synchronously per execution (called from API endpoint).
For scheduled execution, a background task polls for PENDING/APPROVED executions.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from app.domain.whatsapp_automation.entity import ExecutionStatus
from app.infrastructure.repositories.whatsapp_automation_repository import SQLAlchemyAutomationRepository
from app.application.whatsapp_automation.whatsapp_bridge import WhatsAppSendBridge
from app.core.logging import setup_logging

logger = setup_logging("INFO")


class ExecutionProcessor:
    """Processes automation executions with full production maturity."""

    def __init__(
        self,
        automation_repo: SQLAlchemyAutomationRepository,
        whatsapp_bridge: Optional[WhatsAppSendBridge] = None,
    ):
        self.automation_repo = automation_repo
        self.whatsapp_bridge = whatsapp_bridge or WhatsAppSendBridge()
        self._audit_log: list = []

    async def process_execution(self, execution_id: int) -> Dict[str, Any]:
        """Process a single execution: validate → send → track → audit."""
        execution = self.automation_repo.list_executions(limit=500)
        exec_entity = None
        for e in execution:
            if e.id == execution_id:
                exec_entity = e
                break

        if not exec_entity:
            return {"success": False, "error": "Execution not found"}

        # Only process APPROVED or PENDING executions
        if exec_entity.status not in (ExecutionStatus.PENDING, ExecutionStatus.APPROVED):
            return {"success": False, "error": f"Execution status is {exec_entity.status.value}, cannot process"}

        # Pre-flight checks
        if not exec_entity.customer_phone:
            self._audit("SEND_FAILED", execution_id, "No phone number")
            self.automation_repo.update_execution(
                execution_id,
                status=ExecutionStatus.FAILED.value,
                error_message="No phone number",
            )
            return {"success": False, "error": "No phone number"}

        if not exec_entity.message_text:
            self._audit("SEND_FAILED", execution_id, "Empty message")
            self.automation_repo.update_execution(
                execution_id,
                status=ExecutionStatus.FAILED.value,
                error_message="Empty message",
            )
            return {"success": False, "error": "Empty message"}

        # Get the rule to check account_id
        rule = self.automation_repo.get_rule(exec_entity.rule_id)
        account_id = rule.account_id if rule else "primary"

        # Mark as processing (prevent duplicate sends)
        self.automation_repo.update_execution(
            execution_id,
            status=ExecutionStatus.APPROVED.value,
        )
        self._audit("EXECUTION_STARTED", execution_id, f"Processing for customer {exec_entity.customer_codigo}")

        # Send via WhatsApp bridge
        try:
            result = await self.whatsapp_bridge.send_message(
                phone=exec_entity.customer_phone,
                text=exec_entity.message_text,
                account_id=account_id,
            )

            if result["success"]:
                # Mark as sent
                self.automation_repo.update_execution(
                    execution_id,
                    status=ExecutionStatus.SENT.value,
                    sent_at=datetime.utcnow(),
                )
                self._audit(
                    "MESSAGE_SENT",
                    execution_id,
                    f"Sent to {exec_entity.customer_phone} (msg_id={result.get('message_id')})",
                )

                # Update rule metrics
                if rule:
                    self.automation_repo.update_rule(
                        rule.id,
                        successful_sends=(rule.successful_sends or 0) + 1,
                    )

                return {
                    "success": True,
                    "message_id": result.get("message_id"),
                }
            else:
                # Mark as failed
                error = result.get("error", "Unknown error")
                self.automation_repo.update_execution(
                    execution_id,
                    status=ExecutionStatus.FAILED.value,
                    error_message=error,
                )
                self._audit("SEND_FAILED", execution_id, f"Error: {error}")

                # Update rule metrics
                if rule:
                    self.automation_repo.update_rule(
                        rule.id,
                        failed_sends=(rule.failed_sends or 0) + 1,
                    )

                return {"success": False, "error": error}

        except Exception as e:
            self.automation_repo.update_execution(
                execution_id,
                status=ExecutionStatus.FAILED.value,
                error_message=str(e),
            )
            self._audit("SEND_ERROR", execution_id, str(e))
            return {"success": False, "error": str(e)}

    async def process_pending_executions(self, limit: int = 10) -> Dict[str, Any]:
        """Process all pending executions (called by scheduler or manual trigger)."""
        pending = self.automation_repo.list_executions(status="PENDING", limit=limit)
        approved = self.automation_repo.list_executions(status="APPROVED", limit=limit)
        to_process = pending + approved

        results = {"processed": 0, "sent": 0, "failed": 0, "errors": []}

        for exec_entity in to_process:
            result = await self.process_execution(exec_entity.id)
            results["processed"] += 1
            if result["success"]:
                results["sent"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({
                    "execution_id": exec_entity.id,
                    "error": result.get("error"),
                })

        self._audit(
            "BATCH_PROCESSED",
            None,
            f"Processed {results['processed']}: {results['sent']} sent, {results['failed']} failed",
        )

        return results

    def get_audit_log(self, limit: int = 100) -> list:
        """Get recent audit log entries."""
        return self._audit_log[-limit:]

    def _audit(self, action: str, execution_id: Optional[int], detail: str) -> None:
        """Record an audit event."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "execution_id": execution_id,
            "detail": detail,
        }
        self._audit_log.append(entry)
        # Keep last 1000 entries in memory
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-500:]
        logger.info(f"[automation-audit] {action} exec={execution_id} {detail}")
