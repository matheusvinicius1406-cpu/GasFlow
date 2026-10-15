"""
Agent Engine — FASE 12

Plans and executes agent runs with:
- Tool allowlist enforcement
- Risk ceiling enforcement
- Step limit enforcement
- Approval gates
- Deterministic fallback when LLM unavailable
"""

from typing import Any, Dict, List, Optional
from app.domain.automation.agents import (
    AgentDefinition,
    AgentRun,
    AgentStep,
    AgentStatus,
    AgentScope,
    AGENT_SCOPE_CONFIGS,
)
from app.domain.automation.policy import PolicyEngine, ApprovalEngine
from app.domain.ai.tools import ToolRegistry


class AgentEngine:
    """Plans and executes agent runs."""

    MAX_AGENT_STEPS = 10

    def __init__(
        self,
        policy_engine: PolicyEngine,
        approval_engine: ApprovalEngine,
        tool_registry: ToolRegistry,
    ):
        self.policy = policy_engine
        self.approvals = approval_engine
        self.tools = tool_registry
        self._definitions: Dict[str, AgentDefinition] = {}
        self._runs: List[AgentRun] = []
        self._steps: List[AgentStep] = []
        # Métricas por tenant (P0 multiempresa).
        self._metrics: Dict[str, Dict[str, int]] = {}

    @staticmethod
    def _empty_metrics() -> Dict[str, int]:
        return {
            "agents_started": 0,
            "agents_completed": 0,
            "agents_failed": 0,
            "tool_calls": 0,
            "tool_blocked": 0,
        }

    def get_metrics(self, tenant_id: str = "default") -> Dict[str, Any]:
        return dict(self._metrics.get(tenant_id, self._empty_metrics()))

    def register_agent(self, definition: AgentDefinition):
        self._definitions[definition.id] = definition

    def get_agent(self, agent_id: str) -> Optional[AgentDefinition]:
        return self._definitions.get(agent_id)

    def list_agents(self) -> List[AgentDefinition]:
        return list(self._definitions.values())

    def create_default_agents(self):
        """Create the standard agent set."""
        for scope, config in AGENT_SCOPE_CONFIGS.items():
            agent = AgentDefinition(
                name=scope.value.replace("_", " ").title(),
                description=config["description"],
                scope=scope,
                allowed_tools=config["allowed_tools"],
                risk_ceiling=config["risk_ceiling"],
            )
            self.register_agent(agent)

    def execute_agent(
        self,
        agent_id: str,
        goal: str,
        context: Dict[str, Any],
        correlation_id: Optional[str] = None,
        trigger_event_id: Optional[str] = None,
        dry_run: bool = False,
        tenant_id: str = "default",
    ) -> AgentRun:
        """Execute an agent run (escopo do run = tenant_id do chamador)."""
        agent_def = self._definitions.get(agent_id)
        if not agent_def:
            run = AgentRun(agent_id=agent_id, tenant_id=tenant_id, goal=goal, context=context)
            run.fail(f"Agent '{agent_id}' not found")
            return run

        if not agent_def.enabled:
            run = AgentRun(agent_id=agent_id, tenant_id=tenant_id, goal=goal, context=context)
            run.fail(f"Agent '{agent_id}' is disabled")
            return run

        run = AgentRun(
            agent_id=agent_id,
            tenant_id=tenant_id,
            agent_version=agent_def.version,
            goal=goal,
            context=context,
            correlation_id=correlation_id,
            trigger_event_id=trigger_event_id,
        )

        if dry_run:
            run.context["_dry_run"] = True

        run.start()
        self._runs.append(run)
        self._inc_metric("agents_started", run.tenant_id)

        # Generate plan (deterministic for now)
        plan = self._generate_plan(agent_def, goal, context)
        run.plan = plan
        run.begin_execution()

        # Execute steps
        for i, step_plan in enumerate(plan):
            if i >= agent_def.max_steps:
                run.fail(f"Exceeded max steps ({agent_def.max_steps})")
                self._inc_metric("agents_failed", run.tenant_id)
                break

            self._run_plan_step(run, agent_def, agent_id, dry_run, i, step_plan)

        if run.status == AgentStatus.EXECUTING:
            run.complete(
                {"steps_completed": len([s for s in self._steps if s.run_id == run.id and s.status == "COMPLETED"])}
            )
            self._inc_metric("agents_completed", run.tenant_id)

        return run

    def _run_plan_step(
        self,
        run: AgentRun,
        agent_def: AgentDefinition,
        agent_id: str,
        dry_run: bool,
        step_index: int,
        step_plan: Dict[str, Any],
    ) -> None:
        """Executa UM item do plan: valida permissão/risco/aprovação ou roda a ferramenta."""
        step = AgentStep(
            run_id=run.id,
            step_number=step_index + 1,
            description=step_plan.get("description", ""),
            tool_name=step_plan.get("tool"),
            arguments=step_plan.get("arguments", {}),
        )

        # Validate tool permission
        if step.tool_name and step.tool_name not in agent_def.allowed_tools:
            step.fail(f"Tool '{step.tool_name}' not in allowed tools for {agent_def.scope.value}")
            self._inc_metric("tool_blocked", run.tenant_id)
            self._steps.append(step)
            return

        # Check risk ceiling
        policy_check = self.policy.check_permission(
            step.tool_name or "READ", agent_def.scope.value, tenant_id=run.tenant_id
        )
        risk = policy_check.get("risk_level", "LOW")
        ceiling = agent_def.risk_ceiling
        risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        if risk_order.get(risk, 0) > risk_order.get(ceiling, 0):
            step.fail(f"Risk '{risk}' exceeds ceiling '{ceiling}'")
            self._inc_metric("tool_blocked", run.tenant_id)
            self._steps.append(step)
            return

        # Check approval requirement
        if policy_check.get("requires_approval") and not dry_run:
            self.approvals.create_approval(
                action=step.tool_name or "",
                arguments=step.arguments,
                actor=f"agent:{agent_id}",
                risk_level=risk,
                tenant_id=run.tenant_id,
            )
            self._inc_metric("tool_blocked", run.tenant_id)  # temporarily blocked
            step.status = "WAITING_APPROVAL"
            step.status = "WAITING_APPROVAL"
            self._steps.append(step)
            return

        # Execute tool
        if dry_run:
            step.complete({"dry_run": True, "tool": step.tool_name, "args": step.arguments})
        else:
            step.start()
            result = self._execute_tool(step.tool_name, step.arguments)
            if result.get("success"):
                step.complete(result.get("data"))
                run.context.update(result.get("data", {}))
            else:
                step.fail(result.get("error", "Tool failed"))
            self._inc_metric("tool_calls", run.tenant_id)

        self._steps.append(step)

    def _generate_plan(self, agent_def: AgentDefinition, _goal: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate a deterministic plan based on agent scope and goal."""
        plan = []

        if agent_def.scope == AgentScope.CUSTOMER_AGENT:
            plan.append({"description": "Lookup customer", "tool": "get_customer", "arguments": context})
            plan.append({"description": "Get customer 360", "tool": "get_customer_360", "arguments": context})

        elif agent_def.scope == AgentScope.SALES_AGENT:
            plan.append({"description": "Search products", "tool": "search_products", "arguments": {"query": ""}})
            plan.append({"description": "Check inventory", "tool": "get_inventory_summary", "arguments": {}})

        elif agent_def.scope == AgentScope.INVENTORY_AGENT:
            plan.append({"description": "Check low stock", "tool": "get_low_stock", "arguments": {}})
            plan.append({"description": "Inventory summary", "tool": "get_inventory_summary", "arguments": {}})

        elif agent_def.scope == AgentScope.FINANCE_AGENT:
            plan.append({"description": "Financial summary", "tool": "get_financial_summary", "arguments": {}})
            plan.append({"description": "Sales summary", "tool": "get_sales_summary", "arguments": {}})

        elif agent_def.scope == AgentScope.SUPPORT_AGENT:
            plan.append({"description": "Lookup customer", "tool": "get_customer", "arguments": context})
            plan.append({"description": "Check orders", "tool": "get_order", "arguments": context})

        return plan

    def _execute_tool(self, tool_name: Optional[str], arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not tool_name or self.tools is None:
            return {
                "success": False,
                "error": "No tool registry available" if not tool_name else "Tool registry not configured",
            }
        tool = self.tools.get(tool_name)
        if not tool or not tool.handler:
            return {"success": False, "error": f"Tool '{tool_name}' not available"}
        try:
            result = tool.handler(arguments)
            return {"success": result.success, "data": result.data, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_agent(self, run_id: str, tenant_id: str = "default") -> bool:
        for run in self._runs:
            if (
                run.id == run_id
                and run.tenant_id == tenant_id
                and run.status in (AgentStatus.EXECUTING, AgentStatus.PLANNING)
            ):
                run.stop()
                return True
        return False

    def get_run(self, run_id: str, tenant_id: Optional[str] = None) -> Optional[AgentRun]:
        for r in self._runs:
            if r.id == run_id and (tenant_id is None or r.tenant_id == tenant_id):
                return r
        return None

    def get_runs(self, agent_id: Optional[str] = None, tenant_id: Optional[str] = None) -> List[AgentRun]:
        runs = list(self._runs)
        if tenant_id is not None:
            runs = [r for r in runs if r.tenant_id == tenant_id]
        if agent_id:
            return [r for r in runs if r.agent_id == agent_id]
        return runs

    def get_steps(self, run_id: str) -> List[AgentStep]:
        return [s for s in self._steps if s.run_id == run_id]

    def _inc_metric(self, key: str, tenant_id: str = "default"):
        bucket = self._metrics.setdefault(tenant_id, self._empty_metrics())
        if key in bucket:
            bucket[key] += 1
