# Mapeamento de migração — SQLite legado → schema atual

Espelho documental de `scripts/home-server/data/mapping.py` (fonte de
verdade **executável**). Se o schema atual mudar (tabelas/colunas/chaves de
negócio), o `mapping.py` e este documento precisam mudar juntos — o teste
`test_ops01d_mapping` falha se o executável divergir do schema.

## Regras de planejamento (por tabela)

| Situação da origem | Ação | Motivo no relatório |
| --- | --- | --- |
| Tabela em `SKIP_TABLES` (derivada/metadado) | `skip` | `metadado/derivada` |
| Tabela em `BLOCKED_TABLES` (decisão explícita) | `block` | motivo cadastrado |
| Tabela sem equivalente no schema atual | `block` | `tabela_legada_sem_equivalente` |
| Coluna da origem sem equivalente no alvo | `block` | `coluna_sem_equivalente` (+ lista de colunas) |
| Coluna obrigatória do alvo ausente na origem (sem default) | `block` | `coluna_obrigatoria_ausente:<coluna>` |
| Caso contrário | `migrate` | — |

`SKIP_TABLES` (baseline): `_schema_version`, `_ops01d_run`,
`alembic_version`, `sqlite_sequence`, `sqlite_stat1`.
`BLOCKED_TABLES` está vazio na baseline: tabela desconhecida já é bloqueada
dinamicamente.

## Detecção da origem (`detect_source_kind`)

| Assinatura | Resultado |
| --- | --- |
| presença de tabela de `WHATSAPP_SERVICE_MARKERS` (`_migration_tracking`) | `whatsapp-service` — **sempre** recusado (fora do escopo; serviço Node permanece em SQLite por design) |
| todas as `BACKEND_REQUIRED_TABLES` (`clients`) presentes | `backend` — permitido |
| caso contrário | `unknown` — recusado, salvo `--allow-unknown-source` |

## Ledgers imutáveis (`IMMUTABLE_TABLES`)

`auth_audit_log`, `cash_movements`, `driver_location_history`,
`financial_ledger`, `idempotency_keys`, `outbox_entries`, `stock_movements`,
`whatsapp_messages`.

Política: **cópia íntegra ou nada**. Se QUALQUER linha da tabela estiver
inválida, a tabela inteira é bloqueada
(`ledger_imutavel_com_linhas_invalidas`) — nunca migração parcial de dado
financeiro/log.

## Chaves de negócio (`LOGICAL_FKS`)

Relações que o schema não declara como FK (chave de negócio por `codigo`):

| Filho | Coluna | Pai | Coluna | Obrigatória |
| --- | --- | --- | --- | --- |
| `orders` | `client_codigo` | `clients` | `codigo` | não |
| `order_items` | `order_codigo` | `orders` | `codigo` | sim |
| `order_items` | `product_codigo` | `products` | `codigo` | sim |
| `payments` | `order_codigo` | `orders` | `codigo` | sim |
| `receivables` | `order_codigo` | `orders` | `codigo` | sim |
| `receivables` | `customer_codigo` | `clients` | `codigo` | sim |

FKs **declaradas** no modelo atual são verificadas além destas. Regras por
linha: referência órfã → `orphan_reference`; pai bloqueado →
`parent_table_blocked`; filhos de pai não migrável → fora; obrigatória nula →
`not_null_reference`; `tenant_id` filho ≠ pai → `cross_tenant_reference`.

## Regras por linha (tabelas `migrate`)

* Cast de tipos (int/str/bool/float/Decimal/datetime/JSON) — falha →
  `cast_*_failed`;
* `tenant_id` nulo: `block` (padrão) → `null_tenant`; `platform` → preenche
  com `PLATFORM_TENANT_ID` (`"default"`, espelha
  `presentation/dependencies.py`), só com `--null-tenant=platform`;
* NOT NULL violado → `not_null_violation`;
* PK duplicada → `duplicate_pk`; unicidades (coluna única, `UniqueConstraint`,
  índice único) → `unique_violation`;
* valores `NULL` nunca contam como duplicidade (semântica SQL);
* ordem de carga: ordenação topológica por dependência (pais primeiro);
  ciclos caem em ordem alfabética.

## Conferências pós-carga (execute)

1. `PRAGMA foreign_key_check` — zero violações;
2. contagens por tabela: linhas aceitas × linhas no destino;
3. somas financeiras (quantizadas a centavos, `ROUND_HALF_UP`, NULL ignorado
   como o `SUM` do SQL):

| Tabela | Colunas conferidas |
| --- | --- |
| `orders` | `subtotal`, `delivery_fee`, `discount`, `total` |
| `order_items` | `unit_price`, `subtotal` |
| `payments` | `amount` |
| `receivables` | `original_amount`, `paid_amount` |
| `financial_ledger` | `amount` |

Falha em qualquer conferência → rollback + remoção do alvo (código 1).

## Marcador `_ops01d_run`

Tabela criada **no alvo** por `migrate_rehearsal.py --execute`. Uma linha por
execução bem-sucedida: versão da ferramenta, fingerprint da origem
(`size:sha256`), tipo da origem, início/fim e contagens por tabela (JSON).

* Alvo existente **sem** marcador → sobrescrita proibida (código 2);
* marcador com fingerprint **diferente** da origem atual → reexecução
  bloqueada (código 2);
* marcador com fingerprint **igual** → reconciliação somente-leitura
  (idempotente; revalida e reconfere sem gravar).

## Processo de mudança

1. Alterar o schema real (modelo) ou as regras de negócio;
2. atualizar `scripts/home-server/data/mapping.py`;
3. atualizar este documento;
4. rodar `python -m pytest tests/test_ops01d_mapping.py` (e demais
   `test_ops01d_*`) — o teste acusa divergência entre executável, documento e
   schema.
