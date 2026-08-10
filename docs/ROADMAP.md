# Roadmap

> Plano completo de escalabilidade em `docs/SCALABILITY_PLAN.md`.

## Fase 0 — Fundação técnica ✅

* Config via `.env` (pydantic-settings)
* Conexão SQLite/PostgreSQL com pool
* Migrations com Alembic
* Chaves estrangeiras reais + timestamps com timezone
* Camada de repositories + paginação
* Exceções de domínio + handler global
* Logging estruturado (structlog) + request-id
* Estoque atômico com lock de linha nos pedidos
* Testes (pytest) + lint (ruff) + CI + Docker/compose

## Fase 1 — Multiempresa (multi-tenant) ✅

* Modelo `Company` (depósito)
* `company_id` em clientes, pedidos, produtos e entregadores
* Código único por empresa (numeração reinicia por depósito)
* Isolamento automático nas queries (repositories escopados)
* Testes de isolamento entre empresas

## Fase 2 — Autenticação e RBAC ✅

* Modelo `User` vinculado à empresa; senha com bcrypt
* JWT access + refresh (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`)
* Cadastro self-serve: `register` cria empresa + usuário OWNER
* Tenant derivado do token (substitui o header da Fase 1)
* Papéis OWNER > ADMIN > ATTENDANT > DRIVER com `require_role`
* Gestão de usuários (`/users`, ADMIN+) e `/companies/me`
* Testes de auth + permissões por papel

## Fase 1 (legado) — Estrutura inicial

* Estrutura do projeto
* API
* Banco de dados
* Clientes

## Fase 2

* Pedidos

## Fase 3

* Painel operacional

## Fase 4

* Aplicativo dos entregadores

## Fase 5

* WhatsApp

## Fase 6

* CRM

## Fase 7

* Estoque

## Fase 8

* Financeiro

## Fase 9

* IA de texto

## Fase 10

* IA de áudio

## Fase 11

* Automações avançadas

## Fase 12

* Expansão multiempresa
