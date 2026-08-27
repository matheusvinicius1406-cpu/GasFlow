# FASE 12 — CONTROLLED AUTOMATION + AGENT RUNTIME
# FINAL VALIDATION

## STATUS: **APPROVED**

## BASELINE

- Branch: main
- Commit before: e08e6fc (Phase 11)

## ARCHITECTURE

```
EVENT → TRIGGER → POLICY ENGINE → WORKFLOW/AGENT
→ TOOL → USE CASE → DOMAIN → DATABASE → EVENT
```

**Never:** Agent → DB directly | Agent → SQL | Agent → Repository

## COMPONENTS

### Domain Layer
| Component | Purpose |
|-----------|---------|
| DomainEvent | Immutable event with contract |
| EventBus | In-process pub/sub with handler registration |
| OutboxStore | Transactional event persistence |
| WorkflowDefinition | Blueprint with steps, triggers, conditions |
| WorkflowRun | Execution instance |
| WorkflowStepRun | Step execution with status |
| Trigger | Event/schedule/manual/webhook triggers |
| Condition | Deterministic conditions (no eval) |
| PolicyEngine | Risk assessment + kill switch |
| ApprovalEngine | One-time, bound, expiring approvals |
| AgentDefinition | Agent blueprint with scope + permissions |
| AgentRun | Agent execution instance |
| AgentStep | Agent tool call step |

### Application Layer
| Component | Purpose |
|-----------|---------|
| WorkflowEngine | Executes workflows step by step |
| AgentEngine | Plans and executes agent runs |
| BusinessAutomations | 5 pre-built recipes |

### Business Automations
| Recipe | Trigger | Action |
|--------|---------|--------|
| Low Stock Alert | INVENTORY_LOW | Alert operator |
| Receivable Overdue | RECEIVABLE_OVERDUE | Draft → Approve → WhatsApp |
| Customer Reactivation | CUSTOMER_INACTIVE | Draft → Approve → WhatsApp |
| Order Follow-up | ORDER_DELIVERED | Draft message |
| Payment Confirmation | PAYMENT_RECEIVED | Notify customer |

### Agent Scopes
| Scope | Tools | Risk Ceiling |
|-------|-------|-------------|
| CUSTOMER_AGENT | customer, order lookup | LOW |
| SALES_AGENT | catalog, inventory, order | MEDIUM |
| INVENTORY_AGENT | stock, low stock, summary | LOW |
| FINANCE_AGENT | payments, receivables, reports | LOW |
| SUPPORT_AGENT | customer, order, inventory | LOW |

### API
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /automation/workflows | List workflows |
| POST | /automation/workflows | Create workflow |
| POST | /automation/workflows/{id}/execute | Execute |
| POST | /automation/runs/{id}/pause | Pause |
| POST | /automation/runs/{id}/cancel | Cancel |
| GET | /automation/approvals | List approvals |
| POST | /automation/approvals/{id}/approve | Approve |
| POST | /automation/approvals/{id}/reject | Reject |
| GET | /automation/agents | List agents |
| POST | /automation/agents/{id}/execute | Execute agent |
| GET | /automation/agents/runs | List runs |
| POST | /automation/kill-switch | Toggle kill switch |
| GET | /automation/metrics | Metrics |

## SAFETY

- ✅ Agent never accesses DB directly
- ✅ Agent uses only allowed tools (allowlist)
- ✅ Agent risk ceiling enforced
- ✅ Policy engine authorizes all actions
- ✅ HIGH/CRITICAL actions require approval
- ✅ Approvals are one-time, bound, expiring
- ✅ Kill switch pauses all automations
- ✅ Dry run mode (no mutations)
- ✅ Deterministic conditions (no eval/exec)
- ✅ Agent step limit (MAX_AGENT_STEPS)
- ✅ Idempotent events
- ✅ Outbox pattern for reliability
- ✅ Failure isolation (one automation can't break others)

## TESTS

| Suite | Tests | Status |
|-------|-------|--------|
| test_automation.py | 54 | ✅ |
| test_audio.py | 28 | ✅ |
| test_whatsapp_hardening.py | 46 | ✅ |
| test_whatsapp_gateway.py | 32 | ✅ |
| test_financial.py | 47 | ✅ |
| test_inventory.py | 23 | ✅ |
| test_phase7_1_validation.py | 48 | ✅ |
| test_phase7_final.py | 34 | ✅ |
| test_crm.py | 21 | ✅ |
| test_order_domain.py | 33 | ✅ |
| test_phase6_validation.py | 32 | ✅ |
| test_ai.py | 68 | ✅ |
| **Backend Total** | **466** | **✅ All pass** |
| WhatsApp | 38 | ✅ |
| TypeScript | PASS | ✅ |
| Build | PASS | ✅ |

## ADVERSARIAL: 15/15 PASS ✅

## PROJECT STATUS

```
FASE 5  — WhatsApp Core       = CONGELADA ✅
FASE 6  — CRM Core            = CONGELADA ✅
FASE 7  — Inventory Core      = CONGELADA ✅
FASE 8  — Financial Core      = CONGELADA ✅
FASE 9  — Text AI Core        = CONGELADA ✅
FASE 10 — WhatsApp AI         = CONGELADA ✅
FASE 11 — Voice + Audio       = CONGELADA ✅
FASE 12 — Controlled Automation = CONGELADA ✅
FASE 13 = READY
```
