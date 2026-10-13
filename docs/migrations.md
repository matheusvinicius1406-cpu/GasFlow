# Migrations — política e estado

Última atualização: 2026-10-09.

## Política

**O schema do banco é definido exclusivamente pelas migrations do Alembic.**
`Base.metadata.create_all()` e `_ensure_sqlite_columns()` (em
`app/infrastructure/database/init_db.py`) existem como caminho de conveniência
para testes isolados e para o app Desktop de máquina única — **não** são a
fonte de verdade do schema de produção.

Consequência prática: o banco de desenvolvimento deve ser **construído a
partir das migrations** (`alembic upgrade head`), nunca populado apenas por
`create_all`.

## O que aconteceu em 2026-10-09

O banco de desenvolvimento (`backend/gasflow.db`) estava em `alembic_version
= f2b9d4c6a8e0`, enquanto o head era `9f4b7e2a6c31` — **17 migrations atrás**.
A causa: `init_db()` chamava `create_all()` e `_ensure_sqlite_columns()` no
boot, mas **nunca gravava `alembic_version`**. Resultado:

- As tabelas existiam (criadas pelo `create_all`), então `alembic upgrade
  head` falhava em `op.create_table` (tabela já existe).
- ~12 índices declarados nas 17 migrations nunca tinham sido criados.
- Índices "soltos" no banco legacy tinham nomes longos
  (`ix_driver_location_history_*`) vindos do `create_all`; os das migrations
  têm nomes curtos (`ix_driver_loc_hist_*`). Quem lesse o banco via
  `PRAGMA index_list` via dois conjuntos de índices para as mesmas colunas e
  não sabia de onde vinha cada um.

### O que foi feito

O banco foi **reconstruído a partir das migrations** (0 migrations
modificadas, 0 script de reparo):

| | antes | depois |
|---|---|---|
| `alembic_version` | `f2b9d4c6a8e0` | `9f4b7e2a6c31` (head) |
| tabelas | 69 (incl. `_schema_version` do init_db) | 68 (migrations) + `_schema_version` (recriado no boot) |
| índices de migration | ausentes (~12) | presentes |
| dados | seed do `init_db` (auth/permissions/settings/products/audit) | seed regenerado no boot |

O arquivo antigo foi **preservado** como `backend/gasflow.db.legacy`
ignorado pelo git. O admin (`admin-001`) não foi copiado — o `AuthService`
o recria automaticamente no primeiro `/auth/login`
(`app/application/security/auth_service.py:_persist_defaults_to_db`).

## Se acontecer de novo

Sintoma: `alembic current` mostra uma revisão antiga, ou `alembic upgrade
head` falha com "table already exists".

```bash
cd backend
mv gasflow.db gasflow.db.legacy          # preserva, não apaga
alembic upgrade head                      # reconstrói do zero
# sobe o app 1x — init_db regenera o seed (RBAC, settings) e o
# AuthService recria o admin no primeiro login
```

O banco `.legacy` pode ser descartado depois de confirmar que o novo
funciona.

## Resolvido (2026-10-13): `init_db` bootstrapa banco vazio pelo Alembic

`init_db()` agora detecta **banco vazio** (`_database_is_empty()`) e cria o
schema por `alembic upgrade head` (`_run_alembic_upgrade`) em dev/prod/Desktop
— o banco novo nasce com `alembic_version` gravado, que era a causa do drift.

- **Bancos já populados** (legado ou migrado) seguem no `create_all` +
  `_ensure_sqlite_columns()`, que vira rede de compat para colunas faltantes.
- **Testes**: `ENVIRONMENT=test` (e `GASFLOW_INIT_DB_ALEMBIC=0`) mantêm o
  `create_all` efêmero no engine isolado — sem migrar a cada sessão.
- O **exe/Desktop** já rodava `run_migrations()` antes do `init_db` (banco
  não-vazio → caminho inalterado).
- Testes: `tests/test_init_db_alembic_boot.py`.

### Bug corrigido junto: backup A.3 nunca era criado no Windows

`_backup_before_migration()` montava o caminho com `str(engine.url)` — que no
Windows **percent-encoda** o caminho (`C%3A%5CUsers\...`), então
`Path(...).exists()` era sempre `False` e o backup automático era pulado em
silêncio (`tests/test_schema_migration.py::test_backup_created_before_first_migration`
falhava desde então). Agora usa `engine.url.database` (caminho decodificado) e
ignora `:memory:`. `_ensure_sqlite_columns()` continua como rede de compat,
para o caso de uma migration futura falhar no meio.
