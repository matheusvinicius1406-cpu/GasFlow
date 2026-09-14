# Migração v3 — Débito de estoque movido para a entrega (Decisão B3(a))

**Data:** 14/09/2026
**Regra nova:** o estoque só é debitado quando o pedido é **realmente entregue**
(`DELIVERED`). Antes, o débito acontecia na confirmação do pedido
(`Order CONFIRMED`).

## O que mudou

| Evento | Antes (B2) | Depois (B3(a)) |
|---|---|---|
| Order `CONFIRMED` | debita `quantity` + `quantity_full` | **não mexe no estoque** |
| Delivery `DELIVERED` | só credita `quantity_empty` (troca) | **debita `quantity` + `quantity_full` e credita `quantity_empty`** (1 commit único) |
| Delivery `CANCELLED` após `DELIVERED` | reverte a troca (vazios) | **reverte tudo** (cheios voltam, vazios saem) |
| Order `CANCELLED` antes de `DELIVERED` | revertia a reserva | **no-op** (nunca foi debitado) |

Implementação:

- `SQLAlchemyInventoryRepository.deliver_stock_atomic` — débito atômico da
  entrega (SALE com `quantity_full_delta = -qty` e `quantity_empty_delta = +qty`).
- `SQLAlchemyInventoryRepository.reverse_delivery_stock_atomic` — reversão
  exata (RETURN, idempotente, clamp de vazios em 0).
- Hook em `SQLAlchemyDeliveryPersistenceRepository._transition` →
  `_apply_delivery_stock_effect`: aplica débito/reversão após a transição de
  status. Best-effort: falha de estoque **nunca** reverte a transição (a
  entrega é fato físico consumado); o erro é logado.
- `UpdateOrderStatusUseCase` não toca mais estoque em nenhum status.

Idempotência: a constraint `uq_stock_movements_reference_product_type`
`(reference_type, reference_id, product_codigo, type)` garante um único
movimento `SALE` (e um único `RETURN` de reversão) por entrega/produto.
Chamar 2x `DELIVERED` (ou reprocessar) não duplica débito.

## Migração de dados (one-shot, idempotente)

Pedidos já `CONFIRMED` (ou `DELIVERED` pelo fluxo antigo do pedido) no
momento do deploy tinham débito prematuro. O boot aplica
`_revert_premature_stock_debits()` (em `init_db.py`), que:

1. Encontra movimentos `SALE` com `reference_type='ORDER'` que não tenham
   par de reversão (`RESERVATION_REVERSAL` ou `ORDER_RETURN`) para o mesmo
   pedido/produto.
2. Para cada pedido:
   - `CONFIRMED` sem delivery `DELIVERED` → credita de volta
     `quantity += qty`, `quantity_full += qty` e grava movimento
     `RESERVATION_REVERSAL` com `reference_id = revert:<codigo>`.
   - `DELIVERED` sem delivery `DELIVERED` correspondente → idem (a entrega
     real vai debitá-los de novo via `SALE DELIVERY`; líquido fica correto).
   - `CANCELLED` com `SALE` órfã (sem devolução) → idem.
3. Grava trilha de auditoria em `auth_audit_log`
   (`action='stock.migration.revert'`, `details` com before/after).
4. Marca a execução em `system_settings.id='stock_debit_migration_v3'` —
   **rodar 2x não faz nada** (marca verificada antes de qualquer UPDATE).

Proteções:

- Roda depois do backup automático (`_backup_before_migration`) — a v3
  também dispara novo backup antes de mexer no banco.
- Sem inventário para o produto → item pulado (não falha).
- Pedido inexistente → pulado e contabilizado em `skipped`.
- Nunca derruba o boot: qualquer exceção é logada por `init_db()`
  (comportamento padrão das migrações leves).

## Como validar

```bash
cd backend
ADMIN_PASSWORD=test_password_123 python -m pytest tests/test_delivery_debit.py -q
```

Testes (8): `test_order_confirmed_does_not_debit_stock`,
`test_delivery_delivered_debits_stock`, `test_delivery_delivered_credits_empty`,
`test_delivery_cancelled_after_delivered_reverts`,
`test_order_cancelled_before_delivered_does_not_change_stock`,
`test_delivery_idempotent`, `test_migration_reverts_premature_debits`,
`test_migration_idempotent`.

## Invariante

`quantity == quantity_full` (quantity = cheios operáveis). `quantity_empty`
é rastreamento paralelo da física da troca (1 cheio sai, 1 vazio entra na
entrega) e nunca entra no total vendável — preserva a checagem de estoque
suficiente do débito atômico.
