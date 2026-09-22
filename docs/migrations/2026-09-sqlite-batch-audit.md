# Auditoria — migrations Alembic no SQLite (batch_alter_table)

**Data:** 22/09/2026
**Escopo:** as 14 revisions em `backend/migrations/versions/` + o `env.py`.
**Motivo:** o Desktop roda `alembic upgrade head` no boot (decisão B2) sobre
SQLite. O SQLite não faz `ALTER TABLE` completo (drop column, alter column,
add constraint), então o Alembic precisa de *batch mode* — que **recria** a
tabela (copia → dropa → renomeia). O risco é uma migration com operação que o
batch não reproduza ou que a reflexão não consiga reconstruir.

## Método

1. Varredura de DDL por revision: `op.*` fora de `batch_alter_table` e o que
   entra no batch.
2. Execução da cadeia inteira num SQLite real (baseline + 13 incrementais).
3. Confirmação pelo drift guard (schema migrado × models).

## Resultado

**Nenhuma operação do caminho de upgrade ficou fora de batch sem suporte nativo
no SQLite.**

| Operação | Onde | Situação |
|----------|------|----------|
| `add_column` (sempre com `server_default` quando `NOT NULL`) | `b7d3e9f2a4c8`, `d1e5a7c3b2f8`, `e9b2c4d6a1f3` | Nativo no SQLite — ok |
| `create_index` (inclusive único **parcial** com `sqlite_where`) | `e1a5c9b3d7f4`, `b3a7c9e1d5f4`, `c3f8a1d7e9b2`, `c5e8a1f4b7d2`, `d7e4b1a9c6f2` | Nativo no SQLite — ok |
| add/drop column, `create_unique_constraint`, índice em tabela existente | `e4f7a9b1c3d5`, `f2b9d4c6a8e0`, `a4c8e2f6b1d3`, `a7c1e9f2b4d6`, `c8d4e2f6a9b1`, baseline | Dentro de `batch_alter_table` — ok |
| `drop_column` **fora** de batch | `b7d3e9f2a4c8:50-51`, `d1e5a7c3b2f8:30-36`, `e9b2c4d6a1f3:26-28` | Só em `downgrade()`; ver abaixo |

`env.py` configura `render_as_batch=True` nos modos offline e online
(`env.py:54,69`).

## O único ponto fora de batch

Os três `op.drop_column` fora de `batch_alter_table` estão **todos em
`downgrade()`**, em colunas simples (sem PK/índice/unique). `DROP COLUMN` exige
SQLite ≥ 3.35.

- O SQLite do ambiente é **3.50.4** (Python 3.14), então funciona.
- O Desktop roda **apenas `upgrade head`** — `downgrade()` nunca é executado em
  produção. O `ddl` fora de batch não é caminho real.

Não há correção a fazer: envolver esses `drop_column` em batch mudaria o
`downgrade` sem benefício no caminho que roda de verdade.

## Risco residual (válido para migrations futuras)

Como o batch **recria a tabela**, duas condições continuam valendo ao escrever
uma migration nova:

1. **Não criar constraint/índice sem nome** em tabela existente — a reflexão do
   batch pode não conseguir reconstruir a tabela. Use nome explícito
   (`sa.UniqueConstraint("a", "b", name="uq_...")`).
2. **Atenção com FKs de terceiros** para a tabela recriada: a recriação
   (drop + rename) pode quebrar referências externas — limitação conhecida do
   batch do SQLite, não específica deste projeto.

Os blocos de batch que **só criam índice** (baseline, `a7c1e9f2b4d6`,
`c8d4e2f6a9b1`) são inócuos: criar índice já é nativo, então o batch não
recria a tabela (`recreate="auto"`).

## Evidência executada

```bash
cd backend
python -m pytest tests/test_desktop_migrations.py \
                 tests/test_migrations_schema_alignment.py \
                 tests/test_schema_migration.py -q
# 15 passed
```

`test_desktop_migrations.py` sobe a cadeia completa (baseline + incrementais) em
SQLite — DB novo, DB legado `create_all` e DB já versionado — e confirma que as
39 tabelas de runtime existem. `test_migrations_schema_alignment.py` é o drift
guard: compara coluna a coluna o schema migrado com os models.
