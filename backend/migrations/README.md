# Migrations Alembic — GasFlow

O schema do GasFlow é definido pelos **models SQLAlchemy** (fonte única),
registrados em `app/infrastructure/database/init_db.py` (39 tabelas em runtime).
O `env.py` importa esse registro para que as migrations reflitam exatamente
o schema que o app usa — nunca há duas definições de schema para divergir.

## Workflow

```bash
cd backend

# 1. Aplicar migrations num banco novo (SQLite dev ou Postgres prod)
DATABASE_URL="sqlite:///./gasflow.db" python -m alembic upgrade head

# 2. Após ALTERAR um model, gerar a migration correspondente
DATABASE_URL="sqlite:///./_scratch.db" python -m alembic revision --autogenerate -m "descricao"

# 3. Revisar o arquivo gerado em migrations/versions/ e aplicar
python -m alembic upgrade head
```

> **Importante**: rode o `revision --autogenerate` contra um banco VAZIO de
> scratch (ou no head atual) para obter apenas o diff real dos models.
> Nunca aponte o autogenerate para um banco com dados sem revisar o diff.

## Bancos existentes criados por create_all (dev legado)

Ambientes cujo schema foi criado pelo antigo `init_db()/create_all` já estão
idênticos ao baseline se nunca tiveram models alterados. Para adotar o Alembic
sem reaplicar DDL, grave o head atual:

```bash
DATABASE_URL="sqlite:///./gasflow.db" python -m alembic stamp head
```

Depois disso, `upgrade head` passa a gerenciar a evolução do schema.

## Baseline

- `12f8390d5be4_baseline_schema_atual_completo_39_` — snapshot completo do
  schema atual (39 tabelas) gerado a partir dos models.
- A cadeia anterior (`a074610b4bbb → b001 → c001`) foi **arquivada** em
  `migrations/archive/`: estava quebrada (`upgrade head` falhava em SQLite —
  `drop_constraint` sem batch mode) e cobria apenas 18 das 39 tabelas.

## Teste de alinhamento (drift guard)

`tests/test_migrations_schema_alignment.py` aplica `upgrade head` num banco
SQLite temporário e compara tabela a tabela (colunas, PK, nullable) com os
models. Se um model for alterado/adicionado sem migration, o teste falha e
aponta a divergência.

## Notas

- O app mantém `init_db()/create_all` apenas para testes e dev rápido
  (semanticamente igual ao baseline). Produção deve usar `alembic upgrade head`.
- `security_*` (app/infrastructure/security/models.py) é código morto
  (nenhum importador) e não faz parte do schema.
