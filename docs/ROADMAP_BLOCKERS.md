# Roadmap de Evolução — Bloqueios, Riscos e Conhecimento Necessário

**Original:** 12/09/2026
**Re-baseline:** 21/09/2026 — verificado item por item contra o código, com
evidência (`arquivo:linha`).
**Escopo:** pré-análise de viabilidade do roadmap multimodal (RBAC/Admin,
Financeiro, Estoque, Fiscal, Motoristas, Inteligência, App do Entregador,
Auditoria).
**Propósito:** tudo o que pode bloquear a execução e tudo o que o implementador
precisa saber sobre o estado atual antes de escrever a primeira linha.

> **Por que este documento foi reescrito.** Executando o plano original (passos
> 0.2–0.7 da PARTE 6) descobriu-se que **ele já estava implementado**: as
> tabelas RBAC, o `PolicyLoader`, cheios/vazios, o snapshot diário, o CRUD de
> usuários e as telas de Admin existem no código. O documento descrevia o
> estado de 12/09; o código andou. Seguir o plano como estava escrito seria
> trabalho redundante — por isso a PARTE 6 agora lista só o que ficou aberto.
> O que **não** foi re-verificado nesta passagem está marcado como tal, em vez
> de dado como resolvido.

---

## PARTE 1 — ESTADO ATUAL (o que já existe e onde)

O roadmap parte da premissa de "criar do zero" vários módulos — **falso em
vários pontos**, e mais falso hoje do que em 12/09:

### 1.1 Segurança / RBAC — ✅ P0 implementado

- `backend/app/domain/security/models.py`: `User` (bcrypt), `Session`, `Tenant`,
  `TenantMembership`, `Role`, `Permission`, `AuditRecord`, `TenantContext` com
  permissões wildcard (`admin.*`, `order.*`), `SystemRole`
  (`ADMIN/MANAGER/OPERATOR/DRIVER/CUSTOMER/SYSTEM`), `AuditAction` (18 tipos).
  `must_change_password` em `models.py:42`.
- **Permissões passaram a vir do banco** (o gap do P0 fechou):
  `app/application/security/permission_policy_loader.py` sobrepõe o
  `ROLE_PERMISSIONS` do código; DB vazio (pré-seed) cai no dict de código como
  fallback (`permission_policy_loader.py:191-212`). Cache em
  `app/infrastructure/database/permission_cache.py`.
- Tabelas canônicas: `auth_users` (`auth_model.py:24`), `auth_roles` (:89),
  `auth_memberships` (:103), `auth_audit_log` (:121); `permissions`
  (`rbac_model.py:23`), `role_permissions` (:40), **`user_permissions_override`**
  (:55, unique `(user_id, permission_id)`), `stock_daily_snapshots` (:76). Seed
  em `app/infrastructure/database/rbac_seed.py`.
- ⚠️ Existe um **schema paralelo** `security_*`
  (`app/infrastructure/security/models.py`) que **não** é o canônico — ver D5
  na PARTE 8. Ao mexer em RBAC, o arquivo certo é `rbac_model.py`/`auth_model.py`.
- Migrations: `e4f7a9b1c3d5_p0_rbac_audit_stock.py` (cria `auth_users`,
  `stock_movements`, `stock_daily_snapshots`) e
  `f2b9d4c6a8e0_admin_audit_before_after_platform.py` (before/after em
  `auth_audit_log`).
- **CRUD de usuários implementado** em
  `app/presentation/api/core/admin.py`: `GET /users` (:136), `POST /users`
  (:179), `PATCH /users/{id}` (:216), `POST /users/{id}/reset-password` (:247),
  `deactivate` (:284), `activate` (:310). `last_login_at` em
  `app/infrastructure/repositories/auth_model.py:42`, exposto em `admin.py:169`.
- Endpoints de matriz/permissões: `GET /settings/permissions/matrix`,
  `/settings/permissions/me` (`presentation/api/settings.py`); fábricas
  `require_role` / `require_permission` em `presentation/dependencies.py`;
  middleware em `presentation/middleware/auth_middleware.py`.
- Frontend: `features/settings/PermissionsPanel.tsx` (matriz),
  `features/admin/UsersPage.tsx` e `features/admin/AuditPage.tsx` — ambas
  roteadas com `PermissionRoute` (`App.tsx`). `AuthProvider` carrega
  `mustChangePassword` (`features/auth/AuthProvider.tsx:31`).

### 1.2 Autenticação atual

- Single-admin (`ADMIN_PASSWORD` → `settings.json` do Desktop; `LOGIN.txt` no
  userData) **e** service-to-service (`X-GasFlow-Key`).
- **JWT existe — no escopo entregador/mobile**:
  `app/presentation/api/logistics/driver_mobile_auth.py` — `access_token` é
  JWT HS256 de 15 min com escopo `"mobile"`; `refresh_token` é **opaco e vive
  no banco** (7 dias, rotação com revogação da família em reuso).
- **Segredo do JWT já resolvido em 3 níveis** (`driver_mobile_auth.py:99-116`):
  env `MOBILE_JWT_SECRET` → `settings.mobile_jwt_secret`
  (`core/config.py:28-30`) → arquivo gerado **uma vez** em
  `MOBILE_JWT_SECRET_FILE` (default `<tempdir>/gasflow/mobile_jwt_secret.key`).
  Em produção, env **ou** arquivo é obrigatório, mínimo 32 bytes aleatórios.
- **Operador ainda NÃO usa JWT**: `app/presentation/api/core/auth.py` não emite
  token — a sessão de operador segue no modelo atual.

### 1.3 Estoque — ✅ parcialmente implementado (ver B3)

- `inventory` (`quantity`, `minimum`, `maximum`) + **`quantity_full` /
  `quantity_empty`** (`app/application/inventory/snapshot_service.py:118-119`;
  alinhamento de `quantity` com o total em
  `app/infrastructure/database/init_db.py:240-248`).
- **`stock_daily_snapshots` existe**, com unicidade idempotente
  `(tenant_id, snapshot_date, product_codigo)` + índices (`rbac_model.py:79-81`).
- `stock_movements` com constraint de idempotência por referência, e o par de
  **`RESERVATION_REVERSAL`** (`reference_id = revert:<codigo>`)
  implementado em `init_db.py:312-432`.
- `deduct_stock_atomic` é o caminho de débito
  (`app/application/inventory/use_cases.py:79,138`).
- **[Corrigido — ver B3] O débito está na ENTREGA, não no pedido.**
  `app/application/delivery/use_cases.py` não chama estoque, mas quem chama é
  `delivery_persistence_repository.py:269` →
  `inventory_repository.py::deliver_stock_atomic` (SALE + troca cheio→vazio no
  mesmo commit), com o espelho no app do entregador
  (`driver_stock_service.py:240`). O pedido (`order/use_cases.py`) **não** toca
  estoque por decisão explícita.

### 1.4 Branch arquivado (`archive/claude-scalability-plan`)

- **Veredito mantido: não mergear.** Schema incompatível (`users`/`companies`
  com roles OWNER/ADMIN/ATTENDANT/DRIVER vs. `auth_users` + `SystemRole`) e 23
  conflitos na época. A parte útil do padrão JWT **já foi absorvida** (1.2).

### 1.5 Infra de release

- NSIS + `afterPack` (`desktop/scripts/after-pack.js`), backend PyInstaller
  onefile (`gasflow-backend.spec`, entrypoint `desktop_entry.py`).
- Auto-update funcional; **última release publicada: v1.1.7** (instalador +
  `latest.yml` + `.blockmap` conferidos pelo próprio workflow).
- Migração de schema: o exe aplica **`alembic upgrade head` no boot**
  (`desktop_entry.py::run_migrations()`, bundle `migrations_bundle` embutido
  pelo spec), com `stamp head` para bancos legados sem `alembic_version` e
  degradação graciosa se falhar. Por baixo, `create_all()` +
  `_ensure_sqlite_columns()` (`init_db.py:99`) + `_schema_version`
  (`init_db.py:198,212`) atendem bancos antigos. ⚠️ `desktop/README.md:126-134`
  está **desatualizado**: descreve só o caminho `create_all`. Ver B2.

### 1.6 Tempo real e localização

- WebSocket do backend operante (Event Bus) — reutilizável para push.
- **`driver_locations` já existe**
  (`app/infrastructure/repositories/delivery_persistence_model.py:133`), com
  serviço dedicado e auditoria
  (`app/application/delivery/driver_location_service.py`), respeitando janela
  de horário configurável (inclusive travessia de meia-noite,
  `app/domain/settings/models.py:55`).

---

## PARTE 2 — BLOQUEIOS DUROS (impedem ou quebram se não tratados)

| # | Bloqueio | Status em 21/09 | Evidência / o que resta |
|---|----------|-----------------|-------------------------|
| ~~B1~~ | Gate "Require Authenticode signature" no `release.yml` | ✅ **Fechado** (`2498374`) | v1.1.6 e v1.1.7 publicaram com o step fora. |
| ~~B2~~ | Alembic não roda no exe empacotado | ✅ **Fechado — Alembic roda no boot do exe** | `desktop_entry.py::run_migrations()` aplica `alembic upgrade head` a partir do `migrations_bundle` embutido no spec: banco vazio cria tudo + `alembic_version`; banco legado de `create_all` (tabelas sem `alembic_version`) recebe `stamp head` e passa a receber só as revisões pendentes; se a migração falha, o app **não** cai (log `migrations falharam no boot — seguindo com init_db/create_all`). Comprovado subindo o exe: log `Running upgrade 12f8390d5be4 -> a7c1e9f2b4d6 -> …` e `/health` respondendo `healthy`. `_ensure_sqlite_columns()` (`init_db.py:99`) segue como rede de compat, **não** como o mecanismo principal. |
| B3 | Débito de estoque: CONFIRMED vs. DELIVERED | ✅ **DECIDIDO E IMPLEMENTADO** — opção (a) | **Correção de 21/09:** a versão anterior deste doc dizia "aberto" e descrevia o pedido como quem reserva/reverte. Isso era o estado **pré-migração**. O código implementa a decisão B3(a) v3: o pedido **não** toca estoque; o débito é na entrega DELIVERED (`inventory_repository.py::deliver_stock_atomic`, SALE + troca cheio→vazio no mesmo commit; `reverse_delivery_stock_atomic` no cancelamento pós-DELIVERED), e um one-shot de dados desfez os débitos antigos do pedido — `init_db.py::_revert_premature_stock_debits` (marcador `stock_debit_migration_v3`, `reference_type = RESERVATION_REVERSAL`). **Trocar para "pedido debita" não é correção de bug: é mudança de regra**, e exigiria uma migração v4 para re-debitar os pedidos que o v3 creditou de volta. |
| ~~B4~~ | Permissões em código, não no banco | ✅ **Fechado** | `permission_policy_loader.py` (DB sobrepõe, código é fallback) + `user_permissions_override` (`rbac_model.py:55`) + seed (`rbac_seed.py`). |
| B5 | Sem JWT para sessão multimodal | ⚠️ **Parcial** | Escopo **entregador** pronto (access 15 min + refresh rotativo DB-backed, segredo em 3 níveis). **Falta o operador** (`api/core/auth.py` não emite JWT) — é o que bloqueia sessão simultânea desktop+mobile com escopo por plataforma. |
| ~~B6~~ | IPC do Electron sem camada de permissão | ✅ **Fechado** | `desktop/src/main/ipc-permissions.ts` (`registerProtectedHandler` consulta a permissão antes de executar; usado em `src/main/index.ts`). |
| B7 | Fiscal não pode ser "só código" | ❌ **Aberto — externo** | Confirmado no código: as únicas menções a SEFAZ são *"sem SEFAZ"* (`presentation/api/purchase_notes.py:2`, `application/purchase/purchase_service.py`). Continua dependendo de certificado A1/credenciamento. MVP real = deep link para o NFF + persistência local. |
| B8 | App do entregador vs. LGPD/CLT | ❌ **Aberto — jurídico** | Nada mudou por código. O backend de localização já existe (1.6), então o que falta é o **documento jurídico** antes de soltar o app. |
| ~~B9~~ | PyInstaller: CI em 3.12 vs. Docker/produção em 3.14 | ✅ **Fechado** | CI e release agora usam `python-version: "3.14"` (antes 3.12), igual ao `backend/Dockerfile` (`python:3.14-slim`). Validado **antes** de alinhar: PyInstaller 6.22.3 (a versão pinada) compila o spec no 3.14.6, o exe sobe, roda a cadeia Alembic inteira e responde `/health`; a suíte do backend (1662 provas) já rodava no 3.14 local. |

---

## PARTE 3 — RISCOS TÉCNICOS (médios, mitigáveis)

Status de re-verificação em 21/09 ao lado de cada um.

1. **SQLite + concorrência / snapshot idempotente** — ✅ *verificado*: unicidade
   `(tenant_id, snapshot_date, product_codigo)` + índices (`rbac_model.py:79-81`).
2. **Timezone do snapshot** (`utcnow()` vs. data local do depósito) — ⚠️ **não
   re-verificado** nesta passagem.
3. **Reversão de entrega cancelada** — ✅ *verificado*: existe o par
   `RESERVATION_REVERSAL` (`init_db.py:312-432`).
4. **`audit_logs` com before/after e PII** — ⚠️ **parcial**: o before/after
   existe (`f2b9d4c6a8e0`); a política de redaction **não** foi verificada.
5. **Segredo JWT no Desktop** — ✅ *verificado*: env → settings → arquivo gerado
   1x (`driver_mobile_auth.py:99-116`), obrigatório ≥32 bytes em produção.
6. **`must_change_password` no fluxo de login** — ⚠️ **parcial**: a flag existe
   no modelo (`models.py:42`), o endpoint de reset existe (`admin.py:247`) e o
   `AuthProvider` carrega `mustChangePassword` (`AuthProvider.tsx:31`); se o
   login **força** a troca, não foi verificado.
7. **Localização do motorista sem Redis** — ✅ *verificado*: tabela
   `driver_locations` (`delivery_persistence_model.py:133`) + serviço com
   auditoria e janela de horário.
8. **Push de realtime reusando o WebSocket** — ⚠️ **não re-verificado**.
9. **Fallback de IA keyless (toggle default-off)** — ⚠️ **não re-verificado**.
10. **Alembic `batch_alter_table` no SQLite** — 🔻 *irrelevante para o Desktop*,
    que não usa Alembic (B2); segue valendo para Docker/produção.
11. **Compat de auto-update: migrations aditivas** — ⚠️ **vira requisito duro**
    enquanto o Desktop persistir no caminho `create_all` (ver resíduo do B2).12. **Testes backend: senha do conftest** — ✅ *verificado na prática*: rode a suíte **sem definir `ADMIN_PASSWORD`** — o `conftest.py` já traz o default (`test_password_123`) e é exatamente como o CI roda. Sobrescrever o env (ex.: `ADMIN_PASSWORD=test_password`) reprova os 17 testes de login/sessão de `test_security.py`, e o efeito só aparece quando o arquivo roda isolado — parece regressão e não é.
13. **Frontend: React 19 + Vite + zod** — ✅ *verificado*: React 19.3, Vite 8.3,
    Vitest 5; telas novas seguem `features/` (não existe `pages/`), com
    `PermissionsPanel.tsx` e `admin/UsersPage.tsx` como referência de padrão.
14. **`crm-sync` com tenant hardcoded** — ✅ *verificado*: `whatsapp/src/crm-sync.ts`
    não referencia mais tenant "default".

---

## PARTE 4 — O QUE O IMPLEMENTADOR PRECISA SABER (mapa do código)

### Autenticação/autorização
- `get_tenant_context` (`presentation/dependencies.py`) → `TenantContext` com
  `has_permission()` (wildcard) — **todas** as rotas novas passam por
  `require_permission`.
- Convenção de permissão: `resource.action` (`settings.read`, `order.create`,
  `admin.*`). O roadmap usa `:` (`finance:export`) — **usar `resource.action`**.
- Permissões efetivas = banco (`permission_policy_loader.py`) com fallback de
  código; overrides por usuário em `user_permissions_override`.
- CRUD de usuários: `presentation/api/core/admin.py` (o lugar para mexer quando
  o assunto é Admin console).

### Estoque
- Entidade: `app/domain/inventory/entity.py`; repositório atômico:
  `inventory_repository.py::deduct_stock_atomic`.
- Movimentos: `domain/inventory/stock_movement.py` (`MovementType`) +
  `RESERVATION_REVERSAL` para reversão.
- Gancho de entrega: `application/delivery/use_cases.py::UpdateDeliveryStatusUseCase`
  **não mexe em estoque**; quem mexe é o repositório de persistência da entrega
  (`delivery_persistence_repository.py:269` → `deliver_stock_atomic`).

### Release/packaging
- Ordem obrigatória do build local: PyInstaller do backend **antes** do
  electron-builder (o yml só copia o exe).
- `afterPack` instala deps de agent/whatsapp no pacote (electron-builder 26).
- Release: bump `desktop/package.json` → tag `v*` → CI builda exe+NSIS → publica
  → **step de verificação exige `.exe` + `.exe.blockmap` + `latest.yml` e release
  publicado (não rascunho)**.
- Portas no Desktop: backend 8000, WhatsApp 3101 (dev: 3001); settings em
  `%APPDATA%/gasflow-desktop/settings.json`.

### Migrations
- `backend/migrations/versions/` (Alembic, SQLite com batch ops). Baseline
  `12f8390d5be4_baseline_schema_atual_completo_39_` — **tabelas novas nascem em
  migration incremental**, não no baseline. Drift guard em
  `migrations/README.md`.
- Desktop: o exe **usa Alembic no boot** (`desktop_entry.py`), com `stamp head`
  para banco legado; `_ensure_sqlite_columns()` é rede de compat, não o
  mecanismo. Migration nova chega ao Desktop porque `migrations/` + `alembic.ini`
  entram no spec como `migrations_bundle`.

### Armadilha de schema (leia antes de editar RBAC)
- O schema **canônico** é `auth_model.py` (`auth_users`, `auth_roles`,
  `auth_memberships`, `auth_audit_log`) + `rbac_model.py` (`permissions`,
  `role_permissions`, `user_permissions_override`, `stock_daily_snapshots`).
- Existe um `app/infrastructure/security/models.py` com tabelas `security_*`
  que **parece** o schema de RBAC mas não é usado pela aplicação (ver D5).
  Editar lá não muda nada em runtime.

### Referências úteis
- Padrão JWT/refresh já aprovado em casa:
  `presentation/api/logistics/driver_mobile_auth.py`.
- Painel RBAC existente: `frontend/src/features/settings/PermissionsPanel.tsx`.
- Admin (padrão de tela + testes): `frontend/src/features/admin/`.
- Exemplos de permissão em teste: `backend/tests/test_settings_api.py`.

---

## PARTE 5 — DECISÕES DE ARQUITETURA

| # | Decisão | Status |
|---|---------|--------|
| 1 | Estoque cheios/vazios: aditivo + `quantity` como total, ou substituir | ✅ **Decidido e implementado**: aditivo (`quantity_full`/`quantity_empty`) com `quantity` sincronizado como total (`init_db.py:240-248`). |
| 2 | Timing do débito (pedido vs. entrega) | ✅ **Fechada por código — decisão B3(a) v3**: o débito é na entrega DELIVERED e a migração one-shot já desfez os débitos antigos do pedido. Reabrir = mudança de regra + migração v4. Ver B3. |
| 3 | Roles/permissões: banco com fallback de código vs. banco como fonte única | ✅ **Decidido e implementado**: banco sobrepõe, código é fallback (preferido no doc; `permission_policy_loader.py:191-212`). |
| 4 | Segredo JWT no Desktop: env + arquivo (ACL/DPAPI) vs. prompt por boot | ✅ **Decidido e implementado**: env → settings → arquivo gerado 1x, ≥32 bytes obrigatório em produção. |
| 5 | Migração no Desktop: Alembic no exe vs. `create_all` + version guard | ✅ **Decidido e implementado**: **Alembic no exe** (a opção recomendada aqui) + `create_all`/`_ensure_sqlite_columns` como rede para banco legado. Ver B2. |

---

## PARTE 6 — ORDEM SUGERIDA DE EXECUÇÃO (só o que sobrou)

O que estava aqui (0.3 a 0.7) **já está implementado** — ver PARTE 1. O que
realmente falta:

| Passo | Entrega | Destrava | Depende de |
|-------|---------|----------|------------|
| ~~0.2~~ | ~~Migração-on-boot no Desktop~~ | — | **Feito**: `alembic upgrade head` no boot do exe (`desktop_entry.py`). |
| ~~1~~ | ~~Alinhar o interpretador do release ao de produção (B9)~~ | — | **Feito**: CI/release em 3.14, com o spec validado no 3.14 antes de alinhar. |
| 2 | ~~Decidir o timing do débito (B3)~~ — **feito**: débito na entrega (`deliver_stock_atomic`), migração v3 aplicada | Todo o P0 de estoque | — |
| 3 | Cobrir com teste de atomicidade o par `deliver_stock_atomic` / `reverse_delivery_stock_atomic` (idempotência + clamp de vazios) | Núcleo operacional | — |
| 4 | **JWT de operador + sessão multimodal (B5)** | P1/P2 (sessão desktop+mobile por plataforma) | Reusar o padrão de `driver_mobile_auth.py`. |
| 5 | Fiscal: deep link NFF + dados locais (B7) | P2 Fiscal | Decisões externas (contabilidade/certificado). |
| 6 | Documento LGPD/CLT (B8) | App do entregador | Jurídico. |

**Regra mantida:** cada passo termina com suíte verde + commit; não misturar
correção com feature nova.

---

## PARTE 7 — RESUMO EXECUTIVO

- **O P0 está essencialmente pronto** — RBAC persistido com overrides, CRUD de
  usuários, reset de senha, auditoria before/after, cheios/vazios, snapshot
  diário idempotente, telas de Admin, gate de permissão no IPC e segredo JWT
  resolvido. O que este documento descrevia como "gap real" virou código.
- **Aberto de verdade, por ordem de custo/benefício:**
  1. **B3** — ✅ fechado por código (débito na entrega + migração v3 dos
     débitos antigos do pedido). Não é mais bloqueio de negócio.
  2. **B5** — JWT de operador ✅ implementado (access JWT + refresh rotativo);
     o do entregador já existia e serve de padrão.
  3. **B7/B8** — fiscal e LGPD/CLT: não se resolvem com código.

  Nesta passagem, **B9** foi fechado (CI/release alinhados ao 3.14 de produção,
  com o spec validado no 3.14 antes de alinhar).
- **B2 está fechado de verdade:** o exe aplica a cadeia Alembic no boot, então
  o Desktop recebe migrations incrementais de verdade (não só `create_all`). A
  versão anterior deste documento (e o próprio `desktop/README.md`) descreviam
  apenas o caminho antigo — eu tinha escrito "resíduo" aqui e não existe.
- **Riscos não re-verificados nesta passagem:** 2, 4 (redaction), 6 (forçar
  troca no login), 8, 9, 10, 11 — marcados na PARTE 3 para não virarem "achismo
  silencioso".
- **Achado novo desta passagem (D5):** há um **segundo schema de RBAC**
  (`security_*`) que a aplicação não usa — só o próprio teste o importa. Não
  quebra nada hoje; é a armadilha de editar o arquivo errado.
- O branch arquivado **não** deve ser mergeado; a parte útil (JWT/refresh) já
  foi absorvida.

---

## PARTE 8 — DÍVIDAS DECLARADAS NA v1.1.7 (herdadas, com evidência)

Itens que **não** foram corrigidos porque a correção não depende do projeto —
ficam registrados em vez de silenciados, para não virarem surpresa.

| # | Dívida | Evidência | O que destrava |
|---|--------|-----------|----------------|
| D1 | **5 alertas HIGH de `extract-zip`** no serviço WhatsApp, chegando por `whatsapp-web.js` → `puppeteer` → `@puppeteer/browsers`. | `npm audit` no `whatsapp/`. A `2.0.1` é a **última versão publicada** do pacote e é exatamente a que o `overrides` do `package.json` já fixa — não há correção upstream para aplicar. As versões de `extract-zip`/`puppeteer`/`whatsapp-web.js` **não** mudaram na v1.1.7, então não foi introduzido pela release. | Release corrigida do `extract-zip` (ou trocar o motor `wwebjs`, que só é usado no rollback `WA_ENGINE=wwebjs`). Nenhum workflow roda `npm audit`, então não bloqueia CI. |
| D2 | **TypeScript 7 bloqueado no serviço WhatsApp.** | `typescript-eslint@8.70.0` — o último publicado — declara `peerDependencies.typescript: ">=4.8.4 <6.1.0"`. TS 7.0.2 está fora da faixa, e é o que o lint usa. A PR do dependabot (#25) fica **vermelha** no CI por isso. | Publicação de um `typescript-eslint` que aceite TS 7. Enquanto isso o serviço fica em TS 6 — subir seria trocar typecheck por lint que não roda. |
| D3 | **10 rotas do serviço WhatsApp sem consumidor no repositório** (`/lists/*/contacts`, `/customers/sync`, `/campaigns/*/preview`, `/whatsapp/accounts/*/media`…). | `backend/tests/integrity_allowlist.json`, check `whatsapp-sem-consumidor`. | Decisão de produto: são API do serviço que o proxy do backend só não expõe. Remover seria decidir produto por auditoria; expor seria criar tela. Ficam na allowlist com motivo. |
| D5 | **Schema paralelo `security_*` ("schema fantasma").** `app/infrastructure/security/models.py` define `security_users`, `security_roles`, `security_role_permissions`, `security_tenants`, `security_memberships`, `security_sessions`, `security_audit` — um segundo modelo de RBAC, parecido com o canônico. | Nenhum módulo da aplicação o importa: o único importador é `backend/tests/test_security.py`. As tabelas **não** aparecem no baseline Alembic (0 ocorrências de `security_`) nem entram no metadata do runtime, então **não existem em nenhum banco real** — e o teste passa porque cria o próprio schema. | Decisão de dono: **remover** (junto do teste, se ele só testa o fantasma) ou **promover** a canônico. Enquanto existir, é o tipo de arquivo em que um implementador de RBAC editaria por engano. Não é quebra de tela hoje, é risco de trabalho no lugar errado. |
| D4 | **Shim de tipos `frontend/src/test/jest-dom-vitest.d.ts`.** | `@testing-library/jest-dom` 7.x declara `interface Assertion<T = any>` e o Vitest 5 declara `Assertion<R, T>`; a mesclagem de interfaces falha e os matchers somem do `expect`. O shim redeclara a augmentation com a assinatura do Vitest 5. | Suporte a Vitest 5 no `jest-dom`. É shim de compatibilidade, comentado como tal — remover quando o upstream publicar. |

### Infra de release — o que passou a ser regra (v1.1.7)

O gate de CI do release existia desde 16/09 mas **nunca tinha rodado**: como o
release da v1.1.6 saiu *antes* dele, a v1.1.7 foi a primeira tag a exercitá-lo —
e reprovou. Os consertos abaixo são pós-mortem dessa primeira execução:

1. `ci-gate` não fazia `actions/checkout` → workspace vazio → `python3` sai com
   código 2 em 1s, antes de olhar o CI.
2. `permissions: contents: write` sem `actions: read` → a consulta às runs
   voltaria 403 mesmo com o script no lugar.
3. Ninguém conferia o release publicado: o publish do electron-builder pode
   terminar **verde** deixando só o `.blockmap`, e aí o auto-update fica sem
   `latest.yml` para ler. Agora um step confere `.exe`, `.exe.blockmap` e
   `latest.yml` **e exige release publicado** (rascunho é pior que ausente: o
   updater não o enxerga), publicando a URL no resumo do run.
4. O download do toolchain do electron-builder é o ponto frágil (504 do host de
   binários matou o build da v1.1.7) → cache do Actions + retry de 3 tentativas.
5. `cancel-in-progress: true` no `ci.yml` valia também para push na `main` — um
   push posterior **cancelava a CI do commit da tag** que o gate do release
   exige. Agora só cancela em `pull_request`.
