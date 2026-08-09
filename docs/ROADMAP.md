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

## Fase 1

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
