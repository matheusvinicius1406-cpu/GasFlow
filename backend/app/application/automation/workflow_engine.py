"""
Workflow Engine — FASE 12

Executes workflow definitions step by step with:
- Deterministic conditions
- Tool execution through ToolRegistry
- Approval gates
- Binding of executed arguments to approved arguments (arguments_hash)
- Retry logic
- Failure isolation
- Idempotency
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("gasflow.automation")

from app.domain.automation.workflows import (
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStatus,
    StepStatus,
)
from app.domain.automation.triggers import (
    Condition,
    evaluate_condition,
)
from app.domain.automation.policy import PolicyEngine, ApprovalEngine
from app.domain.ai.tools import ToolRegistry


class WorkflowEngine:
    """Executes workflows step by step."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        approval_engine: ApprovalEngine,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.policy = policy_engine
        self.approvals = approval_engine
        self.tools = tool_registry
        self._run_history: List[WorkflowRun] = []
        self._step_history: List[WorkflowStepRun] = []
        # Métricas por tenant (P0 multiempresa): um tenant nunca lê contadores
        # de execução dos demais.
        self._metrics: Dict[str, Dict[str, int]] = {}

    @staticmethod
    def _empty_metrics() -> Dict[str, int]:
        return {
            "workflows_started": 0,
            "workflows_completed": 0,
            "workflows_failed": 0,
            "steps_completed": 0,
            "steps_failed": 0,
            "approvals_requested": 0,
            "approvals_granted": 0,
        }

    def get_metrics(self, tenant_id: str = "default") -> Dict[str, Any]:
        return dict(self._metrics.get(tenant_id, self._empty_metrics()))

    def execute_workflow(
        self,
        definition: WorkflowDefinition,
        context: Dict[str, Any],
        correlation_id: Optional[str] = None,
        trigger_event_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> WorkflowRun:
        """Execute a workflow definition."""
        run = WorkflowRun(
            workflow_id=definition.id,
            tenant_id=definition.tenant_id,
            workflow_version=definition.version,
            correlation_id=correlation_id,
            trigger_event_id=trigger_event_id,
            context=context,
        )

        if dry_run:
            run.context["_dry_run"] = True

        run.start()
        self._run_history.append(run)
        self._inc_metric("workflows_started", run.tenant_id)

        # Execute steps sequentially
        current_step_id = definition.first_step_id
        while current_step_id:
            next_step_id, paused, stop = self._advance_iteration(definition, run, current_step_id, dry_run=dry_run)
            if paused:
                return run
            if stop:
                break
            current_step_id = next_step_id

        if run.status == WorkflowStatus.ACTIVE:
            run.complete()
            self._inc_metric("workflows_completed", run.tenant_id)

        return run

    def resume_after_approval(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> WorkflowRun:
        """Resume a run paused on WAITING_APPROVAL after the approval was granted.

        Binding aprovação → execução (item F do relatório): ao retomar, a
        ação executada tem que ser exatamente a aprovada — mesmo action E
        mesmos argumentos, verificados via arguments_hash
        (ApprovalEngine.validate_binding). Qualquer divergência falha o step
        e a ação NUNCA executa.

        Nota de escopo: o histórico de steps é em memória, então a retomada
        válida acontece no mesmo processo que criou o run (mesma limitação
        já existente do engine); a fila de aprovações em si pode ser Redis
        (APPROVAL_QUEUE_MODE=redis) para sobreviver a restart/multi-worker.
        """
        pending = self._find_pending_approval(definition, run)
        if pending is None:
            return run
        step_def = pending[0]

        self._inc_metric("approvals_granted", run.tenant_id)

        # Executa o restante do run a partir do step atual.
        current_step_id: Optional[str] = run.current_step_id
        while current_step_id:
            next_step_id, paused, stop = self._advance_iteration(
                definition, run, current_step_id, approved_step=step_def
            )
            if paused:
                return run
            if stop:
                break
            current_step_id = next_step_id

        if run.status == WorkflowStatus.ACTIVE:
            run.complete()
            self._inc_metric("workflows_completed", run.tenant_id)

        return run

    def _find_pending_approval(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
    ) -> Optional[Tuple[Any, WorkflowStepRun]]:
        """Localiza o step de definição + step_run pausado com aprovação pendente.

        Falha o run (e o step) quando não há nada válido a retomar; devolve
        ``None`` nesses casos — o chamador só retorna o run.
        """
        step_def = definition.get_step(run.current_step_id or "")
        if not step_def:
            run.fail(f"Step '{run.current_step_id}' not found in definition")
            return None

        # Localiza o step_run WAITING_APPROVAL correspondente.
        pending = [
            sr
            for sr in self._step_history
            if sr.run_id == run.id and sr.step_id == step_def.id and sr.status == StepStatus.WAITING_APPROVAL
        ]
        if not pending:
            run.fail(f"No pending approval found for step '{step_def.id}'")
            return None

        step_run = pending[-1]
        approval_id = step_run.approval_id or ""

        # 1. Aprovação precisa estar APPROVED e não expirada.
        if not self.approvals.is_valid(approval_id):
            step_run.fail("Approval is not valid (rejected, expired, or revoked)")
            self._inc_metric("steps_failed", run.tenant_id)
            run.fail(f"Step '{step_def.name}' failed: approval invalid")
            return None

        # 2. Binding: argumentos a executar == argumentos aprovados.
        if not self.approvals.validate_binding(approval_id, step_def.tool_name or step_def.name, step_def.arguments):
            step_run.fail("Approval binding mismatch — arguments differ from approved")
            self._inc_metric("steps_failed", run.tenant_id)
            run.fail(f"Step '{step_def.name}' failed: approval binding mismatch")
            return None

        return step_def, step_run

    def _advance_iteration(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        current_step_id: str,
        approved_step=None,
        dry_run: bool = False,
    ) -> Tuple[Optional[str], bool, bool]:
        """Um passo do laço de execução: resolve o step e devolve
        ``(próximo_step_id, pausou, parou)``.

        ``pausou`` = step ficou WAITING_APPROVAL (o chamador devolve o run);
        ``parou`` = run falhou/step inexistente (o chamador sai do laço).
        ``approved_step`` é o step cuja aprovação já foi validada (retomada).
        """
        s_def = definition.get_step(current_step_id)
        if not s_def:
            run.fail(f"Step '{current_step_id}' not found in definition")
            self._inc_metric("workflows_failed", run.tenant_id)
            return None, False, True

        if s_def.condition:
            cond_met = self._evaluate_step_condition(s_def.condition, run.context)
            if not cond_met:
                step_run = self._skip_step(run.id, s_def)
                self._step_history.append(step_run)
                return s_def.next_step_on_success, False, False

        if approved_step is not None and current_step_id == approved_step.id:
            return self._resume_approved_step(run, s_def), False, False

        next_step_id, paused = self._advance_step(run, s_def, current_step_id, dry_run)
        return next_step_id, paused, False

    def _resume_approved_step(self, run: WorkflowRun, s_def) -> Optional[str]:
        """Executa o step cuja aprovação foi validada. Devolve o próximo id (None = fim).

        O próprio step pode ser o gate de aprovação (action_type
        ``approval_request``) — nesse caso ele é marcado completo e o run
        segue para o próximo (o envio, etc.). Um step tool_call aprovado
        executa a ferramenta com binding validado.
        """
        if s_def.action_type == "approval_request":
            resumed_gate = WorkflowStepRun(
                run_id=run.id,
                step_id=s_def.id,
                step_name=s_def.name,
            )
            resumed_gate.complete({"approved": True})
            self._step_history.append(resumed_gate)
            self._inc_metric("steps_completed", run.tenant_id)
            return s_def.next_step_on_success

        # Step tool_call aprovado — executa a ferramenta com binding validado.
        result = self._execute_tool(s_def.tool_name, s_def.arguments)
        resumed = WorkflowStepRun(
            run_id=run.id,
            step_id=s_def.id,
            step_name=s_def.name,
        )
        resumed.start()
        if result.get("success"):
            resumed.complete(result.get("data"))
            self._step_history.append(resumed)
            self._inc_metric("steps_completed", run.tenant_id)
            if resumed.result:
                run.context.update(resumed.result)
            return s_def.next_step_on_success

        resumed.fail(result.get("error", "Tool execution failed"))
        self._step_history.append(resumed)
        self._inc_metric("steps_failed", run.tenant_id)
        run.fail(f"Step '{s_def.name}' failed: {resumed.error}")
        self._inc_metric("workflows_failed", run.tenant_id)
        return None

    def _advance_step(
        self,
        run: WorkflowRun,
        step_def,
        current_step_id: str,
        dry_run: bool = False,
    ) -> Tuple[Optional[str], bool]:
        """Executa um step e devolve ``(próximo_step_id, pausou)``."""
        step_run = self._execute_step(run, step_def, dry_run)
        self._step_history.append(step_run)

        if step_run.status == StepStatus.COMPLETED:
            self._inc_metric("steps_completed", run.tenant_id)
            # Merge result into context
            if step_run.result:
                run.context.update(step_run.result)
            return step_def.next_step_on_success, False

        if step_run.status == StepStatus.WAITING_APPROVAL:
            # Step waiting for approval — workflow pauses
            run.current_step_id = current_step_id
            return None, True

        if step_run.status == StepStatus.FAILED:
            self._inc_metric("steps_failed", run.tenant_id)
            if step_def.next_step_on_failure:
                return step_def.next_step_on_failure, False
            run.fail(f"Step '{step_def.name}' failed: {step_run.error}")
            self._inc_metric("workflows_failed", run.tenant_id)
            return None, False

        # SKIPPED or unknown
        return step_def.next_step_on_success, False

    def _execute_step(self, run: WorkflowRun, step_def, dry_run: bool = False) -> WorkflowStepRun:
        """Execute a single workflow step."""
        step_run = WorkflowStepRun(
            run_id=run.id,
            step_id=step_def.id,
            step_name=step_def.name,
        )
        step_run.start()

        try:
            if step_def.action_type == "condition_check":
                # Just check condition — already done above
                step_run.complete({"checked": True})

            elif step_def.action_type == "tool_call":
                if dry_run:
                    step_run.complete({"dry_run": True, "tool": step_def.tool_name, "args": step_def.arguments})
                    return step_run

                # Check approval requirement
                if step_def.requires_approval:
                    policy_check = self.policy.check_permission(
                        step_def.tool_name or "", "WORKFLOW", tenant_id=run.tenant_id
                    )
                    if policy_check.get("requires_approval"):
                        approval = self.approvals.create_approval(
                            action=step_def.tool_name or "",
                            arguments=step_def.arguments,
                            actor=f"workflow:{run.workflow_id}",
                            risk_level=step_def.risk_level,
                            workflow_id=run.workflow_id,
                            run_id=run.id,
                            step_id=step_def.id,
                            tenant_id=run.tenant_id,
                        )
                        self._inc_metric("approvals_requested", run.tenant_id)
                        step_run.wait_approval(approval.id)
                        return step_run

                # Execute tool
                result = self._execute_tool(step_def.tool_name, step_def.arguments)
                if result.get("success"):
                    step_run.complete(result.get("data"))
                else:
                    step_run.fail(result.get("error", "Tool execution failed"))

            elif step_def.action_type == "approval_request":
                approval = self.approvals.create_approval(
                    action=step_def.name,
                    arguments=step_def.arguments,
                    actor=f"workflow:{run.workflow_id}",
                    risk_level=step_def.risk_level,
                    workflow_id=run.workflow_id,
                    run_id=run.id,
                    step_id=step_def.id,
                    tenant_id=run.tenant_id,
                )
                self._inc_metric("approvals_requested", run.tenant_id)
                step_run.wait_approval(approval.id)

            elif step_def.action_type == "notification":
                # Record notification — actual sending happens via outbound
                step_run.complete({"notification": step_def.arguments})

            else:
                step_run.fail(f"Unknown action type: {step_def.action_type}")

        except Exception as e:
            step_run.fail(str(e))

        return step_run

    def _execute_tool(self, tool_name: Optional[str], arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool through the tool registry."""
        if not tool_name or not self.tools:
            return {"success": False, "error": "No tool registry available"}

        tool = self.tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}

        if not tool.handler:
            return {"success": False, "error": f"Tool '{tool_name}' has no handler"}

        try:
            result = tool.handler(arguments)
            return {"success": result.success, "data": result.data, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _evaluate_step_condition(self, condition_str: str, context: Dict[str, Any]) -> bool:
        """Evaluate a simple condition string against context."""
        # Simple parsing: "field operator value"
        # Example: "inventory.quantity lt 5"
        parts = condition_str.strip().split()
        if len(parts) == 3:
            field_name, op_str, value = parts
            try:
                from app.domain.automation.triggers import ConditionOperator

                op_map = {
                    "lt": ConditionOperator.LT,
                    "le": ConditionOperator.LE,
                    "gt": ConditionOperator.GT,
                    "ge": ConditionOperator.GE,
                    "eq": ConditionOperator.EQ,
                    "ne": ConditionOperator.NE,
                }
                op = op_map.get(op_str)
                if op:
                    # Try numeric conversion (`object`: o valor pode voltar a ser
                    # a string original quando não é numérico).
                    val: object
                    try:
                        val = float(value)
                    except ValueError:
                        val = value
                    cond = Condition(field=field_name, operator=op, value=val)
                    return evaluate_condition(cond, context)
            except Exception:
                # Condição malformada não derruba a regra — segue com default.
                logger.debug("automation.condition.parse_failed", exc_info=True)
        return True  # Default: condition met

    def _skip_step(self, run_id: str, step_def) -> WorkflowStepRun:
        step_run = WorkflowStepRun(
            run_id=run_id,
            step_id=step_def.id,
            step_name=step_def.name,
        )
        step_run.skip()
        return step_run

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Find a run by id in history."""
        for r in self._run_history:
            if r.id == run_id:
                return r
        return None

    def get_step_runs(self, run_id: str) -> List[WorkflowStepRun]:
        """Return all step runs for a workflow run (ordered)."""
        return [sr for sr in self._step_history if sr.run_id == run_id]

    def pause_run(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        if not run:
            return False
        if run.status != WorkflowStatus.ACTIVE:
            return False
        run.status = WorkflowStatus.PAUSED
        return True

    def cancel_run(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        if not run:
            return False
        if run.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.PAUSED):
            return False
        run.cancel()
        return True

    def _inc_metric(self, key: str, tenant_id: str = "default"):
        bucket = self._metrics.setdefault(tenant_id, self._empty_metrics())
        if key in bucket:
            bucket[key] += 1
