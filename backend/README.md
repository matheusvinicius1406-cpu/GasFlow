# GasFlow — Backend

API do GasFlow em FastAPI + SQLAlchemy.

## Arquitetura

```
app/
  api/           Routers HTTP (FastAPI)
  services/      Regras de negócio
  repositories/  Acesso a dados (queries + paginação)
  models/        Modelos SQLAlchemy (ORM)
  schemas/       Contratos Pydantic (entrada/saída)
  core/          Config, exceções, logging, middleware
  database/      Engine, sessão, base declarativa
alembic/         Migrations de banco
tests/           Testes (pytest)
```

Fluxo: `api` → `services` → `repositories` → `models`.

## Rodar em desenvolvimento (SQLite)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Em SQLite as tabelas são criadas automaticamente no startup.

## Rodar com PostgreSQL (produção-like)

Na raiz do repositório:

```bash
docker-compose up --build
```

Sobe `postgres` + `redis` + `api`. A API aplica as migrations
(`alembic upgrade head`) antes de iniciar.

## Autenticação e multiempresa

Todo dado de negócio pertence a uma empresa (`company_id`), e o acesso é
autenticado por JWT. A empresa (tenant) é derivada do usuário do token.

Fluxo:

```bash
# 1. Cadastro self-serve: cria a empresa (depósito) + usuário OWNER
curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
  -d '{"empresa_nome":"Gás Sul","nome":"Ana","email":"ana@sul.com","senha":"senha123"}'
# -> { "access_token": "...", "refresh_token": "..." }

# 2. Use o token nas demais chamadas
curl localhost:8000/clients/ -H 'Authorization: Bearer <access_token>'
```

Endpoints de auth: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`.

### Papéis (RBAC)

Hierarquia `OWNER > ADMIN > ATTENDANT > DRIVER`:

- **ADMIN+**: produtos/estoque, entregadores, gestão de usuários (`/users`)
- **ATTENDANT+**: clientes e pedidos
- **Qualquer autenticado**: leituras (GET)

Toda a autenticação passa por `app/api/dependencies.py`
(`get_current_user`, `get_current_company_id`, `require_role`).

## Migrations (Alembic)

```bash
# aplicar
alembic upgrade head

# gerar nova migration a partir das mudanças nos modelos
alembic revision --autogenerate -m "descrição"

# reverter
alembic downgrade -1
```

> A URL do banco vem das settings (`.env` / variáveis de ambiente); não é preciso
> editar `alembic.ini`.

## Testes e lint

```bash
pytest
ruff check app tests alembic
```

Os testes usam SQLite em memória, isolado por teste (ver `tests/conftest.py`).
