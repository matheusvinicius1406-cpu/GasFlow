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

## Pendência: `init_db` ainda usa `create_all`

Enquanto `init_db()` chamar `create_all()` sem gravar `alembic_version`, o
problema acima pode se repetir se alguém bootar o app num banco novo sem
rodar `alembic upgrade head` antes. A correção de fundo é fazer `init_db`
rodar `alembic upgrade head` (uma fonte de verdade), o que também eliminaria
a necessidade de `_ensure_sqlite_columns`. Isso é um item separado — mexe no
caminho de boot do backend, dos testes e do Desktop, e merece sessão própria
com regressão completa.
