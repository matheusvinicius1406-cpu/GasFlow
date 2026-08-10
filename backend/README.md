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

## Multiempresa (multi-tenant)

Todo dado de negócio pertence a uma empresa (`company_id`). A empresa da
requisição é resolvida assim:

- Com o header `X-Company-Id: <codigo-da-empresa>` → opera naquela empresa.
- Sem o header → usa a **empresa padrão** (`000001`), criada automaticamente
  (conveniência para uso single-tenant / desenvolvimento).

Gerencie empresas em `/companies`. Na Fase 2 (auth), a empresa passará a vir do
usuário autenticado — bastará alterar `app/api/dependencies.py::get_current_company`.

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
