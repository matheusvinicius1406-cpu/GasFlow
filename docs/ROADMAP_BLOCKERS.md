# Roadmap de Evolução — Bloqueios, Riscos e Conhecimento Necessário

**Data:** 12/09/2026
**Escopo:** pré-análise de viabilidade do roadmap multimodal (RBAC/Admin, Financeiro, Estoque, Fiscal, Motoristas, Inteligência, App do Entregador, Auditoria).
**Propósito:** tudo o que pode bloquear a execução e tudo o que o implementador precisa saber sobre o estado atual antes de escrever a primeira linha.

---

## PARTE 1 — ESTADO ATUAL (o que já existe e onde)

O roadmap parte da premissa de "criar do zero" vários módulos — **falso em vários pontos**. Já existe:

### 1.1 Segurança / RBAC (FASE 13 — mais avançado do que o roadmap assume)
- `backend/app/domain/security/models.py` (404 linhas): `User` (bcrypt), `Session`, `Tenant`, `TenantMembership`, `Role`, `Permission`, `AuditRecord`, `TenantContext` com **permissões wildcard** (`admin.*` → tudo, `order.*` → `order.read`), `SystemRole` = `ADMIN/MANAGER/OPERATOR/DRIVER/CUSTOMER/SYSTEM`, `AuditAction` com 18 tipos, `ROLE_PERMISSIONS` (linha 282).
- Fábricas de dependência em `app/presentation/dependencies.py`: `require_role(...)`, `require_permission("x.y")` (concede por role ADMIN como defesa dupla).
- Endpoint de matriz: `GET /settings/permissions/matrix` e `/settings/permissions/me` (`presentation/api/settings.py`).
- Tabelas no banco (baseline Alembic): `auth_users`, `auth_audit_log` (com índices por actor/tenant/timestamp), `ai_audit_log`.
- Frontend: `frontend/src/features/settings/PermissionsPanel.tsx` (matriz RBAC já renderizada).
- Middleware: `presentation/middleware/auth_middleware.py` (require_auth/require_admin/require_permission).

**Gap real do P0 RBAC:** permissões vivem em **código** (`ROLE_PERMISSIONS` dict), não no banco. Não há CRUD persistido de usuários (endpoints users), nem `must_change_password`, nem `last_login_at`, nem roles/permissions/overrides como tabelas, nem `audit_logs` unificado com before/after JSON.

### 1.2 Autenticação atual
- Single-admin: `ADMIN_PASSWORD` (env) → `backendAdminPassword` em `settings.json` do Desktop; `LOGIN.txt` no userData guarda instruções.
- Service-to-service: `X-GasFlow-Key` (`MARCOS_GAS_API_KEY` / `WHATSAPP_SERVICE_KEY`), **sem fallback JWT** no sync-batch (hardening deliberado).
- **Não há JWT/refresh token em produção hoje.** O branch arquivado tem uma implementação, mas incompatível (ver 1.4).

### 1.3 Estoque
- `inventory` (quantity única, minimum/maximum) e `stock_movements` (com `uq_stock_movements_reference_product_type` — idempotência por referência!) em `infrastructure/repositories/inventory_model.py`.
- **Débito acontece no pedido CONFIRMED** (`application/order/use_cases.py::_deduct_stock` → `deduct_stock_atomic`), com retorno atômico no CANCELLED. **A entrega não debita estoque hoje.**
- `delivery` domain completo (PENDING→ASSIGNED→EN_ROUTE→ARRIVED→DELIVERED/FAILED/CANCELLED) em `application/delivery/use_cases.py` — `UpdateDeliveryStatusUseCase` é o gancho natural para o débito na finalização.
- **Não existe** cheios/vazios (`quantity_full/quantity_empty`), nem `stock_daily_snapshot`.

### 1.4 Branch arquivado (`archive/claude-scalability-plan`)
Tem JWT+refresh+multi-tenant prontos (tags `archive/claude-scalability-plan`), porém:
- Schema **incompatível**: tabela `users` + `companies` (roles OWNER/ADMIN/ATTENDANT/DRIVER) vs. atual `auth_users` (ADMIN/MANAGER/OPERATOR/DRIVER/CUSTOMER/SYSTEM).
- Conflitos com a main atual (23 conflitos na época do arquivamento).
- **Veredito: não mergear.** Usar apenas como referência de padrão (refresh tokens, estrutura do AuthService).

### 1.5 Infra de release (validada nesta sessão)
- NSIS + afterPack hook (`desktop/scripts/after-pack.js` restaura node_modules de agent/whatsapp no pacote — electron-builder 26 ignora node_modules em extraResources).
- Auto-updater funcional (1.1.2 > v1.1.1 detectado pelo updater).
- Backend embutido: PyInstaller onefile (`gasflow-backend.spec`, entrypoint `desktop_entry.py`).

### 1.6 Tempo real
- WebSocket do backend já operante ("Realtime bridge: Event Bus → WebSocket connected" nos logs) — reutilizável para push de localização de motoristas.

---

## PARTE 2 — BLOQUEIOS DUROS (impedem ou quebram se não tratados)

| # | Bloqueio | Impacto | Resolução necessária |
|---|----------|---------|---------------------|
| B1 | **`release.yml` tem o gate "Require Authenticode signature"** (linhas 64–71: `Get-AuthenticodeSignature` → `throw` se não Valid). Sem certificado, **toda release falha e nada é publicado**. | Bloqueia publicar v1.1.2+ e todo o pipeline de evolução. | Remover o step (decisão já aprovada na spec `docs/exe-rebuild-spec.md` #13). Trivial, fazer primeiro. |
| B2 | **Alembic não roda no exe empacotado.** `desktop_entry.py` não invoca `alembic upgrade`; o compose de produção aplica no boot, mas o Desktop não. Usuários instalados ficariam **sem as tabelas novas** (users, roles, audit_logs, stock_full/empty, snapshots). | P0 inteiro (novas tabelas) não chega aos usuários do Desktop. | Adicionar migração-on-boot no `desktop_entry.py` (alembic embutido no exe via hiddenimports, apontando para o migrations/ empacotado como resource) **ou** fallback `create_all` com guard de versão. Decidir antes do primeiro PR. |
| B3 | **Débito de estoque em pedido CONFIRMED conflita com o requisito "somente entregas FINALIZADAS debitam".** Migrar o débito para DELIVERED sem remover o do CONFIRMED = **duplo débito**. | Inconsistência de estoque (o pior tipo de bug para o negócio). | Decidir: (a) mover o débito do pedido para a entrega (pedido só valida/reserva), ou (b) manter débito no CONFIRMED e a entrega só move cheio→vazio (a troca do cilindro é isso fisicamente). A opção (b) reflete a realidade do GLP: na entrega, 1 cheio sai e 1 vazio entra. |
| B4 | **Permissões em código, não no banco.** O Admin console exige persistir roles/permissões/overrides; hoje `TenantContext` carrega o dict hardcoded. | Sem loader DB→contexto, telas de roles não persistem nada. | Criar tabelas + seed, e um `PolicyLoader` que sobrepõe `ROLE_PERMISSIONS` (código = fallback, banco = fonte). Manter wildcard. |
| B5 | **Sem JWT.** Sessão multimodal (desktop+mobile simultâneos, escopo por plataforma) exige access+refresh JWT — hoje não existe na main. | P1/P2 (driver app) bloqueados sem isso. | Construir sobre `app/domain/security` (bcrypt e Session já prontos). Usar o branch arquivado só como referência. Segredo do JWT: variável de ambiente gerada no 1º boot (Desktop), NUNCA no settings.json. |
| B6 | **IPC do Electron sem camada de permissão.** `finance:export_pdf` etc. exigem validação no main process; preload/contextBridge atual não tem notion de permissão. | Requisito "3 camadas" do roadmap não atendido. | Criar wrapper de IPC que consulta o backend (`/settings/permissions/me` ou token decodificado) antes de executar handlers sensíveis. |
| B7 | **Fiscal não pode ser "só código".** NFC-e/NF-e exige certificado digital A1, credenciamento SEFAZ, CSC do município. O NFF (gov.br) é web, sem API → deep link/webview é o único MVP real. | P2 Fiscal depende de decisões externas (contabilidade, certificado). | Não subestimar: MVP = deep link para NFF + persistência local dos dados da nota. Emissão direta (Focus NFe etc.) só quando houver credenciamento. |
| B8 | **App do entregador bloqueado por auditoria LGPD/CLT** (pré-requisito legal do próprio roadmap). GPS fora do horário de trabalho, consentimento, retenção, TST. | P2 entregador não pode começar sem o documento jurídico aprovado. | Produzir o documento primeiro (P1); o backend de localização (tabela+API) PODE ser construído antes, o app não. |
| B9 | **PyInstaller rebuild obrigatório** para qualquer mudança de backend chegar ao Desktop — e o CI usa Python 3.12 enquanto o Docker/produção usa 3.14 (dependabot bumpou). | Divergência de comportamento local/CI/prod. | Validar o spec no 3.14 (ou alinhar CI) antes de confiar no artefato do release. |

---

## PARTE 3 — RISCOS TÉCNICOS (médios, mitigáveis)

1. **SQLite + concorrência**: `stock_daily_snapshot` diário com múltiplos processos (Desktop + futuras instâncias) — usar upsert idempotente por (date, product_codigo) e agendar no 1º request do dia.
2. **Timezone do snapshot**: código usa `datetime.utcnow()`; "estoque inicial do dia" precisa de data **local** do depósito. Definir TZ de negócio (America/Sao_Paulo) em config, não do server.
3. **Reversão de entrega cancelada**: a `uq_stock_movements(reference_type, reference_id, product_codigo, type)` já dá idempotência — movimentos de reversão devem ter `type` próprio (ex.: `REVERSAL`) e respeitar a mesma constraint.
4. **audit_logs com before/after JSON**: contém PII de clientes → política de redaction (nunca logar senha/hash, telefone completo opcional). Volume alto → índices (actor, action, created_at) desde a migração.
5. **Segredo JWT no Desktop**: settings.json é texto plano — gerar segredo no 1º boot em arquivo com ACL de usuário (ou DPAPI). Nunca commitar.
6. **`must_change_password` no fluxo atual**: o frontend precisa interceptar login e forçar troca — tocar no fluxo de login single-admin existente sem quebrar o LOGIN.txt.
7. **Redis para último ponto do motorista**: verificar se o compose atual sobe Redis (o whatsapp usa SQLite; comentários do código citam "Redis do compose"). Se não houver, primeira versão pode usar tabela `driver_locations` com índice (driver_id, recorded_at DESC) — Postgres/SQLite aguenta leitura de último ponto por driver sem Redis no volume atual.
8. **Realtime driver push**: reusar o WebSocket existente (Event Bus) — novo tópico `driver_status_changed`; não criar segundo canal.
9. **Fallback de IA (keyless)**: requisitos de privacidade — dados de clientes indo para endpoint de terceiros exige toggle admin default-off + `audit_log` de uso. O roadmap já prevê o toggle; implementá-lo no mesmo PR.
10. **Alembic batch_alter_table**: SQLite não suporta ALTER completo — seguir o padrão dos migrations existentes (batch ops) e o "drift guard" documentado em `migrations/README.md`.
11. **Compat auto-update**: usuário em 1.1.1 → atualiza para 1.1.2+ com schema novo: migrations precisam ser aditivas (sem quebrar código antigo já em execução durante o update).
12. **Testes backend**: última execução conhecida exigia `ADMIN_PASSWORD=test_password_123` (default do conftest) — não sobrescrever env na sessão de teste. CI verde é gate para P1 (instrução do roadmap).
13. **Frontend**: React 19 + Vite 8 + zod 4 (recém-mergeados) — telas novas devem seguir `features/` (não existe `pages/`); usar `PermissionsPanel.tsx` como referência de padrão.
14. **WhatsApp no Desktop compartilha o backend**: endpoints de driver/localização devem exigir JWT — hoje `crm-sync` usa tenant "default" hardcoded; multi-usuário precisa de tenant do contexto, não hardcoded.

---

## PARTE 4 — O QUE O IMPLEMENTADOR PRECISA SABER (mapa do código)

### Autenticação/autorização
- `get_tenant_context` (dependencies.py) → `TenantContext` com `has_permission()` (wildcard) — **todas** as rotas novas devem usá-lo via `require_permission`.
- Convenção de permissão existente: `resource.action` (ex.: `settings.read`, `order.create`, `admin.*`). O roadmap usa `:` (ex.: `finance:export`) — **padronizar num formato só** (sugestão: adotar `resource.action` existente e mapear os novos).
- Roles são `SystemRole` (enum) + `ROLE_PERMISSIONS` dict → matriz do endpoint `/settings/permissions/matrix`.

### Estoque
- Entidade: `app/domain/inventory/entity.py` (entry/exit/adjust com validações, `stock_status` derivado).
- Repositório atômico: `inventory_repository.py::deduct_stock_atomic` (use este padrão para qualquer débito novo).
- Movimentos: `domain/inventory/stock_movement.py` (MovementType) + constraint de idempotência por referência.
- Gancho de entrega: `application/delivery/use_cases.py::UpdateDeliveryStatusUseCase` (DELIVERED/CANCELLED já tratam proof, failure, release de motorista).

### Release/packaging
- Ordem obrigatória do build local: pyinstaller do backend ANTES do electron-builder (o yml só copia o exe).
- `afterPack` hook instala deps de agent/whatsapp no pacote (electron-builder 26).
- Release: bump `desktop/package.json` → tag `v*` → CI builda exe+NSIS → publica (após remover o gate B1).
- Portas no Desktop: backend 8000, WhatsApp 3101 (dev: 3001), settings em `%APPDATA%/gasflow-desktop/settings.json`.

### Migrations
- Diretório: `backend/migrations/versions/` (Alembic, naming `xxxx_descricao.py`), SQLite com batch ops.
- Baseline: `12f8390d5be4_baseline_schema_atual_completo_39_.py` — **as tabelas novas devem nascer como migration incremental**, não mexer no baseline.
- Drift guard: ver `migrations/README.md`.

### Referências úteis
- JWT/refresh (padrão, não merge): `git show archive/claude-scalability-plan:backend/app/services/auth_service.py`.
- Painel RBAC existente: `frontend/src/features/settings/PermissionsPanel.tsx`.
- Testes de permissão como exemplo: `backend/tests/test_settings_api.py` (TestPermissionsEndpoints, TestWildcardPermissionFix).

---

## PARTE 5 — DECISÕES DE ARQUITETURA PENDENTES (bloqueiam o 1º PR)

1. **Estoque cheios/vazios**: colunas novas + manter `quantity` sincronizado como total (compat com pedidos/relatórios) **ou** substituir quantity em todo o fluxo? → Recomendado: aditivo + property `total`.
2. **Timing do débito**: manter débito no pedido CONFIRMED e na entrega apenas trocar cheio→vazio (física do GLP) **ou** mover débito para entrega DELIVERED (texto literal do roadmap)? → Impacta B3; decidir com o dono do negócio.
3. **Roles/permissões**: seed no banco com fallback de código (recomendado) vs. banco como única fonte.
4. **Armazenamento do segredo JWT no Desktop**: env gerada + arquivo com DPAPI/ACL (recomendado) vs. prompt do usuário a cada boot.
5. **Migração no Desktop**: Alembic embutido no exe vs. `create_all` com version guard (B2).

---

## PARTE 6 — ORDEM SUGERIDA DE EXECUÇÃO (P0 destravado)

| Passo | Entrega | Desbloqueia |
|-------|---------|-------------|
| 0.1 | Remover gate Authenticode do `release.yml` (B1) + publicar v1.1.2 | Pipeline de release inteiro |
| 0.2 | Migração-on-boot no `desktop_entry.py` (B2) + validação no instalador | Todas as tabelas novas |
| 0.3 | Migration: `auth_users` (must_change_password, last_login_at, role) + `roles`, `permissions`, `role_permissions`, `user_permissions_override`, `audit_logs` + seed | P0 RBAC |
| 0.4 | `PolicyLoader` (banco→TenantContext) + CRUD de usuários (endpoints) + reset de senha + audit em cada mutação | Admin console |
| 0.5 | Migration estoque: `quantity_full/quantity_empty`, `stock_movements` cheio/vazio, `stock_daily_snapshot` (decisão 5.1/5.2 antes) | P0 estoque |
| 0.6 | Débito/transação na finalização de entrega + reversão no cancel + testes de atomicidade | Núcleo operacional |
| 0.7 | Telas Admin (usuários, roles, auditoria) + IPC com permissão (B6) | Fechamento do P0 |
| 0.8 | Suite verde (pytest + vitest + e2e) + instalador validado (NSIS) | Gate para P1 |

**Regra do roadmap mantida:** não avançar a P1 sem P0 verde e build empacotado validado.

---

## PARTE 7 — RESUMO EXECUTIVO

- **Nada do P0 é "do zero"**: segurança FASE 13, delivery domain e atomicidade de estoque já existem — o trabalho é completar (persistir policy, unificar audit, split cheios/vazios).
- **2 bloqueios triviais** (gate de assinatura, migração no exe) travam TODO o roadmap se não forem os primeiros PRs.
- **1 conflito de negócio** (débito CONFIRMED vs. DELIVERED) precisa de decisão do dono antes do código de estoque.
- **2 dependências externas** (credenciamento fiscal; auditoria jurídica LGPD/CLT) não se resolvem com código — isolá-las no cronograma.
- O branch arquivado **não** deve ser mergeado (schema incompatível); usar como referência de padrão JWT.
