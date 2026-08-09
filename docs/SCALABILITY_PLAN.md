# Plano: GasFlow escalável e completo

## Contexto

O GasFlow é um sistema para depósitos de gás e água. Hoje ele é um backend
FastAPI + SQLAlchemy em estágio inicial: 4 modelos (`Client`, `Order`,
`Product`, `DeliveryDriver`), serviços com métodos estáticos, routers REST e
schemas Pydantic. Os docs (`docs/VISION.md`, `docs/ROADMAP.md`) descrevem uma
visão de 12 fases (WhatsApp, CRM, financeiro, estoque, app do entregador,
multiempresa), mas quase nada disso existe em código.

Para o sistema se tornar **escalável e completo** — atendendo múltiplos
depósitos como um SaaS — a base técnica atual precisa ser endurecida e os
módulos de negócio precisam ser construídos. Decisões definidas com o usuário:

- **Abrangência:** Fundação técnica **+** features de negócio (12 fases).
- **Multiempresa:** multi-tenant **desde a base** (todo dado isolado por empresa).
- **Interfaces:** backend/API **+** painel operacional web **+** app do entregador.

Resultado pretendido: um GasFlow production-grade, multi-tenant, com API robusta,
painel de gestão, app de entregador e integração WhatsApp — capaz de crescer em
número de depósitos, pedidos e usuários sem reescritas.

---

## Diagnóstico da base atual (o que corrigir)

Problemas que bloqueiam escala/robustez hoje:

1. **Sem chaves estrangeiras reais** — entidades ligadas por string `codigo`
   (`Order.client_codigo`, `Order.product` guarda o código do produto, etc.).
   Sem integridade referencial, sem `JOIN` eficiente, sem cascatas.
2. **Sem migrations** — `init_db.py` usa `Base.metadata.create_all`. Qualquer
   mudança de schema em produção fica impossível de versionar.
3. **`config.py` não lê `.env`** — `Settings(BaseModel)` tem valores hardcoded;
   o `.env.example` (DATABASE_URL, DEBUG) é ignorado exceto em `connection.py`.
4. **Postgres quebrado** — `connection.py` passa `connect_args={"check_same_thread": False}`
   (opção só de SQLite) para toda engine, incluindo o Postgres do
   `docker-compose.yml`.
5. **Geração de código com race condition** — `generate_code` lê o último id e
   soma 1 (em `order_service.py`, `client_service.py`, etc.); concorrência gera
   códigos duplicados.
6. **`datetime.utcnow` depreciado** e sem timezone em todos os modelos.
7. **Sem autenticação/autorização** — qualquer um chama qualquer endpoint.
8. **Sem paginação** — `get_all` retorna tudo; não escala com volume.
9. **Sem testes, sem CI, sem logging estruturado, sem tratamento de erro padronizado.**
10. **Estoque decrementado sem transação atômica/lock** (`order_service.create`),
    permitindo venda de estoque inexistente sob concorrência.
11. **Sem camada de tenant** — nada isola dados por depósito.

---

## Arquitetura-alvo

**Stack (evolução do que já existe, sem trocar fundações):**

- **API:** FastAPI (mantido), organizado em `app/api` (routers) → `app/services`
  (regras) → `app/repositories` (acesso a dados) → `app/models`.
- **Banco:** PostgreSQL (já no `docker-compose.yml`) com **Alembic** para migrations.
- **Auth:** JWT (access + refresh) via `python-jose` + `passlib[bcrypt]`, RBAC
  por papéis (`OWNER`, `ADMIN`, `ATTENDANT`, `DRIVER`).
- **Multi-tenant:** coluna `company_id` (FK → `companies`) em **todas** as tabelas
  de negócio; dependência FastAPI que injeta o tenant do token e um filtro
  automático nas queries. Códigos (`codigo`) passam a ser **únicos por empresa**,
  não globais.
- **Async/filas:** Celery + Redis (ou RQ) para tarefas pesadas/assíncronas
  (envio WhatsApp, notificações, relatórios, recuperação de clientes).
- **Cache:** Redis para dados quentes (catálogo de produtos, sessão de bot).
- **Realtime:** WebSocket (FastAPI) para o painel (fila de pedidos ao vivo) e app
  do entregador (novas entregas).
- **Observabilidade:** logging estruturado (`structlog`), health/readiness,
  métricas Prometheus, Sentry para erros.
- **Empacotamento:** `Dockerfile` do backend + `docker-compose` completo
  (api, postgres, redis, worker). CI no GitHub Actions (lint + testes + build).

**Interfaces:**

- **Painel operacional (web):** React + TypeScript + Vite (SPA), consumindo a API.
- **App do entregador (mobile):** React Native / Expo (multiplataforma) — fila de
  entregas, atualizar status, mapa/rota, comprovante.

---

## Estrutura de repositório alvo

```
GasFlow/
  backend/            # FastAPI (existente, refatorado)
    app/
      api/  services/  repositories/  models/  schemas/  core/  workers/
    alembic/          # migrations (novo)
    tests/            # pytest (novo)
    Dockerfile        # novo
  frontend/           # painel web React (novo)
  driver-app/         # app do entregador Expo (novo)
  docker-compose.yml  # ampliado: api, db, redis, worker
  .github/workflows/  # CI (novo)
  docs/               # atualizar conforme evolução
```

---

## Fases de execução

Ordenadas por dependência. Cada fase é entregável e testável isoladamente.

### Fase 0 — Fundação técnica (pré-requisito de tudo)
Objetivo: base sólida antes de multi-tenant e features.

- Corrigir `app/core/config.py` para usar `pydantic-settings` (`BaseSettings`)
  lendo `.env` (app_name, version, debug, database_url, secret_key, redis_url).
  Adicionar `pydantic-settings` ao `requirements.txt`.
- Corrigir `app/database/connection.py`: `check_same_thread` só para SQLite
  (detectar via URL); pool de conexões (`pool_size`, `max_overflow`,
  `pool_pre_ping`) para Postgres.
- Introduzir **Alembic**: `alembic init`, baseline com o schema atual, e passar a
  gerar migrations em vez de `create_all` (manter `init_db` só para testes/SQLite).
- Introduzir **relacionamentos e FKs reais** nos modelos (`app/models/*`):
  `Order.client_id → clients.id`, `Order.product_id → products.id`,
  `Order.driver_id → delivery_drivers.id`, mantendo `codigo` como identificador
  legível de negócio. Migrar dados na migration.
- Trocar `datetime.utcnow` por `datetime.now(timezone.utc)` em todos os modelos e
  serviços; usar `server_default`/`onupdate` do SQLAlchemy.
- Camada **repositories**: extrair queries dos serviços para
  `app/repositories/*` (base genérica `BaseRepository` com CRUD + paginação).
- **Paginação** padrão (`limit`/`offset` + total) em todos os `list_*`.
- Tratamento de erros: exceções de domínio (`app/core/exceptions.py`) +
  `exception_handler` global no `main.py` (substituir `raise Exception(...)` dos
  serviços por exceções tipadas → HTTP 4xx corretos).
- **Logging estruturado** (`structlog`) + middleware de request-id.
- **Testes**: `pytest` + `httpx` + SQLite em memória; cobrir CRUD e o fluxo de
  pedido. Fixtures em `backend/tests/conftest.py`.
- **CI**: `.github/workflows/ci.yml` (ruff + pytest).
- **Dockerfile** do backend + `docker-compose` com api + postgres + redis.

Arquivos-chave: `backend/app/core/config.py`, `backend/app/database/connection.py`,
`backend/app/models/*.py`, `backend/app/services/*.py`, `backend/requirements.txt`,
novos `backend/alembic/`, `backend/app/repositories/`, `backend/tests/`.

### Fase 1 — Multi-tenant (empresas)
Objetivo: isolar todos os dados por depósito.

- Novo modelo `Company` (`app/models/company.py`): id, nome, cnpj, telefone,
  responsável, plano, ativo, timestamps.
- Adicionar `company_id` (FK) em `clients`, `orders`, `products`,
  `delivery_drivers` (e futuras tabelas). Migration com backfill para uma
  empresa default.
- `codigo` passa a ser **único por `(company_id, codigo)`** — ajustar constraints
  e `generate_code` para escopar por empresa (e resolver a race condition com
  `SELECT ... FOR UPDATE` ou sequência por empresa).
- Dependência `get_current_company` que resolve o tenant a partir do usuário
  autenticado e filtra automaticamente todas as queries (`BaseRepository`
  recebe `company_id`).

Arquivos-chave: novo `backend/app/models/company.py`, migration Alembic,
`backend/app/repositories/base.py`, `backend/app/api/dependencies`.

### Fase 2 — Autenticação e RBAC
Objetivo: acesso seguro por papel.

- Modelo `User` (email, senha hash, `role`, `company_id`, ativo).
- Endpoints `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`.
- JWT (access+refresh), `passlib[bcrypt]`; dependências `get_current_user` e
  `require_role(...)` aplicadas aos routers.
- CORS: trocar lista fixa por origins configuráveis via `.env`.

Arquivos-chave: novo `backend/app/models/user.py`, `backend/app/api/auth.py`,
`backend/app/core/security.py`, ajustes em `backend/app/main.py`.

### Fase 3 — Pedidos completos + histórico + estoque atômico
Objetivo: núcleo operacional confiável.

- Refatorar `OrderService.create` para transação atômica com **lock de estoque**
  (`with_for_update`) e validação por exceções de domínio.
- Modelo de **itens de pedido** (`OrderItem`) para pedidos com múltiplos produtos
  (hoje `Order` guarda 1 produto). `Order` vira cabeçalho (cliente, endereço,
  status, total, pagamento) + itens.
- **Máquina de estados** de status com transições válidas (evitar pular de
  PENDING→DELIVERED). Registrar histórico de mudanças (`order_status_history`).
- Movimentações de estoque auditadas (`stock_movements`) em vez de só decrementar.

Arquivos-chave: `backend/app/models/order.py`, novos `order_item.py`,
`stock_movement.py`, `backend/app/services/order_service.py`,
`backend/app/services/pricing_service.py`.

### Fase 4 — Painel operacional (web)
Objetivo: gestão visual da operação.

- Projeto `frontend/` (React + TS + Vite). Telas: login, dashboard, clientes,
  produtos/estoque, pedidos (kanban por status), entregadores, financeiro.
- Fila de pedidos em tempo real via WebSocket.
- Cliente HTTP com auth JWT + refresh.

Arquivos-chave: novo diretório `frontend/`.

### Fase 5 — App do entregador (mobile)
Objetivo: entregador na rua.

- Projeto `driver-app/` (Expo/React Native). Login, lista de entregas
  atribuídas, atualizar status, navegação/rota (deep-link mapa), comprovante
  (foto/assinatura), notificações push.

Arquivos-chave: novo diretório `driver-app/`.

### Fase 6 — Integração WhatsApp
Objetivo: atendimento e pedidos automáticos.

- Webhook de entrada (WhatsApp Cloud API) → serviço de bot → cria/identifica
  cliente por telefone (`ClientService.get_by_phone` já existe) e registra pedido.
- Envio assíncrono via Celery worker; sessão de conversa em Redis.
- Fluxo do `docs/FLOWS.md` (Mensagem → Bot → Banco → Pedido).

Arquivos-chave: novo `backend/app/api/whatsapp.py`,
`backend/app/services/bot_service.py`, `backend/app/workers/`.

### Fase 7 — CRM + Financeiro + Estoque avançado
Objetivo: completar os módulos de negócio.

- **CRM:** histórico de compras por cliente, segmentação, recuperação automática
  (clientes inativos há N dias → tarefa Celery), fidelização.
- **Financeiro:** contas a receber, formas de pagamento, fechamento de caixa,
  relatórios (faturamento, ticket médio).
- **Estoque:** entradas/saídas, alerta de estoque mínimo, inventário.

Arquivos-chave: novos módulos em `backend/app/models`, `services`, `api`.

### Fase 8 — Inteligência e automações (visão futura)
Objetivo: diferenciais do `docs/VISION.md`.

- IA de texto (interpretar mensagens do WhatsApp), IA de áudio (transcrição de
  pedidos por voz), previsão de demanda, mapa de calor de vendas, rastreamento de
  entregas, impressão automática de pedidos.
- Descritas em alto nível; detalhamento após o núcleo estar em produção.

---

## Reuso do que já existe

- Manter FastAPI, SQLAlchemy `DeclarativeBase` (`app/database/base.py`),
  `get_db` (`app/database/dependencies.py`) e o padrão router→service.
- `ClientService.get_by_phone` e `format_crm_name` já servem ao WhatsApp/CRM.
- Enum `OrderStatus` (`app/models/order.py`) é a base da máquina de estados.
- `PricingService.calculate` permanece o ponto único de precificação (estender
  para descontos/promoções depois).
- `docs/ROADMAP.md` e `docs/VISION.md` já mapeiam as fases — atualizar conforme
  entrega.

---

## Verificação

Por fase, validar de ponta a ponta:

- **Backend:** `cd backend && pytest` (cobrir CRUD, fluxo de pedido, auth,
  isolamento multi-tenant — garantir que empresa A não vê dados da B).
- **Migrations:** `alembic upgrade head` em banco limpo + `alembic downgrade`
  volta sem erro.
- **Local:** `docker-compose up` sobe api+db+redis(+worker); `GET /health`
  responde `healthy`; Swagger em `/docs` lista todos os endpoints.
- **Fluxo manual (via /docs ou curl):** criar empresa → usuário/login → produto →
  cliente → pedido (checar estoque decrementado atomicamente) → atribuir
  entregador → transição de status válida → histórico registrado.
- **Auth:** endpoint protegido rejeita sem token (401) e com papel errado (403).
- **Painel/app:** login + operação real contra a API local.
- **CI:** workflow do GitHub Actions verde (lint + testes) em cada push.

---

## Sequência recomendada de entrega

Fase 0 → 1 → 2 → 3 são o **caminho crítico** (base escalável + núcleo confiável).
Fases 4–5 (interfaces) e 6 (WhatsApp) podem correr em paralelo após a Fase 3.
Fase 7 (CRM/financeiro/estoque) depois do núcleo. Fase 8 é evolução.

Recomendo iniciar a implementação pela **Fase 0** por ser pré-requisito de todas
as demais e por corrigir os bugs que hoje impedem rodar em Postgres/produção.
