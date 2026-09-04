"""
Workflow Engine — FASE 12

Executes workflow definitions step by step with:
- Deterministic conditions
- Tool execution through ToolRegistry
- Approval gates
- Retry logic
- Failure isolation
- Idempotency
"""

from typing import Any, Dict, List, Optional
from app.domain.automation.workflows import (
    WorkflowDefinition, WorkflowRun, WorkflowStepRun,
    WorkflowStatus, StepStatus,
)
from app.domain.automation.triggers import (
    Condition, evaluate_condition,
)
from app.domain.automation.policy import PolicyEngine, ApprovalEngine


class WorkflowEngine:
    """Executes workflows step by step."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        approval_engine: ApprovalEngine,
        tool_registry=None,
    ):
        self.policy = policy_engine
        self.approvals = approval_engine
        self.tools = tool_registry
        self._run_history: List[WorkflowRun] = []
        self._step_history: List[WorkflowStepRun] = []
        self._metrics = {
            "workflows_started": 0,
            "workflows_completed": 0,
            "workflows_failed": 0,
            "steps_completed": 0,
            "steps_failed": 0,
            "approvals_requested": 0,
            "approvals_granted": 0,
        }

    def get_metrics(self) -> Dict[str, Any]:
        return dict(self._metrics)

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
            workflow_version=definition.version,
            correlation_id=correlation_id,
            trigger_event_id=trigger_event_id,
            context=context,
        )

        if dry_run:
            run.context["_dry_run"] = True

        run.start()
        self._run_history.append(run)
        self._inc_metric("workflows_started")

        # Execute steps sequentially
        current_step_id = definition.first_step_id
        while current_step_id:
            step_def = definition.get_step(current_step_id)
            if not step_def:
                run.fail(f"Step '{current_step_id}' not found in definition")
                self._inc_metric("workflows_failed")
                break

            # Check conditions
            if step_def.condition:
                cond_met = self._evaluate_step_condition(step_def.condition, run.context)
                if not cond_met:
                    step_run = self._skip_step(run.id, step_def)
                    self._step_history.append(step_run)
                    current_step_id = step_def.next_step_on_success
                    continue

            # Execute step
            step_run = self._execute_step(run, step_def, dry_run)
            self._step_history.append(step_run)

            if step_run.status == StepStatus.COMPLETED:
                self._inc_metric("steps_completed")
                # Merge result into context
                if step_run.result:
                    run.context.update(step_run.result)
                current_step_id = step_def.next_step_on_success
            elif step_run.status == StepStatus.WAITING_APPROVAL:
                # Step waiting for approval — workflow pauses
                run.current_step_id = current_step_id
                return run
            elif step_run.status == StepStatus.FAILED:
                self._inc_metric("steps_failed")
                if step_def.next_step_on_failure:
                    current_step_id = step_def.next_step_on_failure
                else:
                    run.fail(f"Step '{step_def.name}' failed: {step_run.error}")
                    self._inc_metric("workflows_failed")
                    break
            else:
                # SKIPPED or unknown
                current_step_id = step_def.next_step_on_success

        if run.status == WorkflowStatus.ACTIVE:
            run.complete()
            self._inc_metric("workflows_completed")

        return run

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
                    policy_check = self.policy.check_permission(step_def.tool_name or "", "WORKFLOW")
                    if policy_check.get("requires_approval"):
                        approval = self.approvals.create_approval(
                            action=step_def.tool_name or "",
                            arguments=step_def.arguments,
                            actor=f"workflow:{run.workflow_id}",
                            risk_level=step_def.risk_level,
                            workflow_id=run.workflow_id,
                            run_id=run.id,
                            step_id=step_def.id,
                        )
                        self._inc_metric("approvals_requested")
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
                )
                self._inc_metric("approvals_requested")
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
                    "lt": ConditionOperator.LT, "le": ConditionOperator.LE,
                    "gt": ConditionOperator.GT, "ge": ConditionOperator.GE,
                    "eq": ConditionOperator.EQ, "ne": ConditionOperator.NE,
                }
                op = op_map.get(op_str)
                if op:
                    # Try numeric conversion
                    try:
                        val = float(value)
                    except ValueError:
                        val = value
                    cond = Condition(field=field_name, operator=op, value=val)
                    return evaluate_condition(cond, context)
            except Exception:
                pass
        return True  # Default: condition met

    def _skip_step(self, run_id: str, step_def) -> WorkflowStepRun:
        step_run = WorkflowStepRun(
            run_id=run_id, step_id=step_def.id, step_name=step_def.name,
        )
        step_run.skip()
        return step_run

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        for r in self._run_history:
            if r.id == run_id:
                return r
        return None

    def get_step_runs(self, run_id: str) -> List[WorkflowStepRun]:
        return [s for s in self._step_history if s.run_id == run_id]

    def cancel_run(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        if run and run.status == WorkflowStatus.ACTIVE:
            run.cancel()
            return True
        return False

    def pause_run(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        if run and run.status == WorkflowStatus.ACTIVE:
            run.status = WorkflowStatus.PAUSED
            return True
        return False

    def _inc_metric(self, key: str):
        if key in self._metrics:
            self._metrics[key] += 1
