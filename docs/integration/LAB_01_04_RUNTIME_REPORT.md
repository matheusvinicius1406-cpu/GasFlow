# GasFlow Home Server — relatório runtime LAB-01 → LAB-05

**Data/hora da verificação:** 28/10/2026, 12:30 (-03:00) · **re-verificação final:** 28/10/2026, 13:02 (-03:00)
**Re-verificação profunda (LAB-05/LAB-02/LAB-04):** 28/10/2026, 14:33–14:45 (-03:00)
**Resultado geral:** **LAB-01 a LAB-03 APROVADOS · LAB-05 APROVADO (com prova de linhagem e teste independente) ·
LAB-02 APROVADO — R-1 CORRIGIDO · LAB-04 EM ANDAMENTO (pareamento é ação humana;
sem simulador local — envio bloqueado)** — laboratório **ativo** nesta máquina.
**Branch/HEAD:** `release/home-server-candidate` / `e989f70d029385fd974d3d7e5cb0426cbce670a5`

> Relatório anterior (27/10, 13:37) registrava **BLOQUEADO** porque o Docker Engine
> estava parado. O operador iniciou o Docker Desktop manualmente; esta execução
> repetiu o gate do daemon, o inventário e executou os gates LAB-01 → LAB-05
> conforme `docs/integration/OPS_01C_LAB_PLAN.md`.

---

## 0. Estado do daemon e inventário (gate de segurança)

| Verificação | Resultado |
|---|---|
| Contexto | `desktop-linux`, `docker info` funcional |
| Docker CLI / Compose | 29.6.2 / 5.3.1 (≥ 2.24.4 exigido pela tag `!override`) |
| Recursos preexistentes `gasflow-hs-lab_*` antes do `up` | **Nenhum** — namespace limpo no início desta execução |
| Outros stacks no host (intocados) | `gasflow` (e2e: 4 containers), `twenty` (3 containers), `gasflow-whatsapp` (Exited, 7 semanas) |
| Portas em escuta antes do lab | 8000/8088/80/5432/3000/9090/6379 livres na leitura do gate |

Nenhum recurso ambíguo foi reutilizado; todos os containers/volumes/rede criados
nesta execução têm prefixo `gasflow-hs-lab`.

---

## 1. Estado Git

- Branch: `release/home-server-candidate` · HEAD: `e989f70`.
- Estado inicial da execução (inalterado): `backend/tests/test_ops01b_homeserver_profile.py`,
  `deploy/home-server/README.md`, `deploy/home-server/verify-static.sh`,
  `docs/integration/OPS_01C_LAB_PLAN.md`, diretório não rastreado `docs/ops/` e este relatório (`??`).
- **Execução de aprofundamento (28/10, 14:33–14:45) adicionou apenas:**
  `backend/app/infrastructure/database/init_db.py` (correção R-1) e o novo
  `backend/tests/test_init_db_dialect_selection.py` (testes de dialeto).
- Sem commit, push, merge, reset, `git clean` ou rewrite.

---

## 2. Estado do laboratório (projeto `gasflow-hs-lab`)

| Container | Estado | Portas publicadas | Memória / limite |
|---|---|---|---|
| `gasflow-hs-lab-postgres` | Up ~3h **(healthy)** | **nenhuma** (5432 só na rede interna) | 55 MiB / 640 MiB |
| `gasflow-hs-lab-redis` | Up ~3h **(healthy)** | **nenhuma** (6379 só na rede interna) | 4 MiB / 128 MiB |
| `gasflow-hs-lab-backend` | Up ~2h **(healthy)** | **nenhuma** (8000 só na rede interna) | 136 MiB / 768 MiB |
| `gasflow-hs-lab-frontend` | Up ~2h **(healthy)** | **`127.0.0.1:8088`** | 7 MiB / 128 MiB |
| `gasflow-hs-lab-whatsapp` | Up ~46min **(healthy)**, 0 restarts | **nenhuma** (3000 só na rede interna) | 81 MiB / 1 GiB |

- Única porta do lab no host: **`127.0.0.1:8088`** (confirmado em
  `Get-NetTCPConnection -State Listen`: 8088 em `127.0.0.1`; 8000/5432/6379/80 **sem**
  listener novo do lab). Os únicos outros listeners de 3000 são de outros projetos
  (`twenty`), não do laboratório.
- Volumes do projeto: `gasflow-hs-lab_postgres_data`, `_whatsapp_data`,
  `_whatsapp_auth`, `_baileys_auth`, `_whatsapp_uploads`, `_whatsapp_export`,
  `_backups_data` — todos com prefixo próprio; Redis efêmero (sem volume).
- Nenhum container `gasflow-*` de produção (`gasflow-whatsapp`, `C:\gf`) foi
  criado, iniciado ou modificado.

---

## 3. LAB-01 — PostgreSQL + Redis (**APROVADO**)

- `config -q` verde com os três `-f` + `--env-file deploy/home-server/.env.lab`.
- Projeto `gasflow-hs-lab`, DSN `postgresql+psycopg2://***@postgres:5432/gasflow_lab`,
  publicação exatamente `127.0.0.1:8088`.
- `select current_database()` → `gasflow_lab` (banco novo, volume próprio).
- Ambos `healthy`; nenhum log de falha de autenticação no Postgres.
- Nenhuma porta 5432/6379 em escuta no host.

## 4. LAB-02 — Backend FastAPI + migração no boot (**APROVADO com ressalva R-1**)

- Comando de boot confirmado no compose: `alembic upgrade head && uvicorn … --workers 1`
  — a migração **antecede** o uvicorn.
- **25 upgrades** aplicados no boot, de ` (baseline 39 tabelas) ` até
  `a4b5c6d7e8f9 (head)` — `alembic current` = `alembic head` = `a4b5c6d7e8f9`.
- DSN dentro do container: `postgresql+psycopg2://***:***@postgres:5432/gasflow_lab`
  (não SQLite, não banco real).
- Schema: **69 tabelas** em `gasflow_lab` (`auth_users=3`, `auth_roles=7`,
  `permissions=78`, `role_permissions=65`, `auth_tenants=3`).
- Recursos dentro do limite (136 MiB / 768 MiB; 0.17 % CPU); nenhum bind mount
  gravável; nenhuma porta nova publicada.

**R-1 (novo achado, não bloqueante):** o boot loga **um** `ERROR`
`schema migration leve falhou` — `_ensure_sqlite_columns()` executa
`PRAGMA table_info("ai_audit_log")`, sintaxe **SQLite**, contra PostgreSQL
(`backend/app/infrastructure/database/init_db.py:127`). A exceção é capturada
pelo `try/except` do `init_db()` e o boot continua (API saudável, smoke verde).
Efeito colateral: no PostgreSQL as etapas seguintes do mesmo bloco são
**puladas** — `_ensure_schema_version` (tabela `_schema_version` ausente),
`_backfill_stock_full_empty`, `_revert_premature_stock_debits`,
`_reorg_cleanup` e `_seed_rbac_if_needed`. No lab isso não quebra nada porque o
Alembic já criou o schema completo e a migração `e4f7a9b1c3d5` já semeou RBAC
(78 permissões). Classificação original: **P2-R1**.

**✅ R-1 CORRIGIDO (28/10, 14:33–14:45 — frente de aprofundamento):**

- **Correção mínima em `init_db.py`:** (1) `_ensure_sqlite_columns()` retorna
  cedo quando `engine.url.get_backend_name() != "sqlite"` (defesa em profundidade);
  (2) `init_db()` seleciona a cadeia de migrações leves **por dialeto real** —
  ela roda apenas em SQLite (caminho legado do Desktop) e é omitida em outros
  dialetos com log `init_db.light_migrations.skipped` (nível DEBUG).
- **Por que omitir em vez de habilitar os passos portáveis:** em PostgreSQL o
  Alembic é a única fonte de schema/semente. Habilitar etapas que hoje não rodam
  criaria **migrações inesperadas** (ex.: `_reorg_cleanup` apaga e re-semeia o
  catálogo; `_ensure_schema_version` criaria a tabela `_schema_version` fora das
  migrations — indesejado também para o critério de 69 tabelas do LAB-06).
  O comportamento observado em PG é **idêntico ao anterior** (nenhuma etapa da
  cadeia roda), apenas sem o `ERROR` de boot. SQLite: **idêntico ao anterior**.
- **Testes para ambos os dialetos:** novo
  `backend/tests/test_init_db_dialect_selection.py` (5 testes): cadeia completa
  em SQLite; no PostgreSQL só `_bootstrap_schema` e **zero conexões** da cadeia
  (engine stub que falha ao conectar); sem log de falha; `_ensure_sqlite_columns`
  no-op em PostgreSQL; continua executando em SQLite. Comportamento SQLite pré-existente
  coberto por `test_schema_migration.py` (preservado, verde).
- **Verificação em PostgreSQL REAL (não só unitária):** container descartável
  `docker run --rm` (imagem do backend já existente, código corrigido montado
  **read-only**, DSN apontando para o banco descartável `gasflow_lab_itest`):
  `init_db()` executado com `RESULT=PASS` — 69 tabelas antes/depois, 0 tabelas
  criadas, **0 logs de ERROR**, 1 log `light_migrations.skipped`, 0
  `schema migration leve falhou`, `_schema_version` ausente. Container encerrado
  automaticamente (`--rm`), sem tocar em bancos operacionais.
- **Regressão (verde):** foco `test_init_db_dialect_selection + test_schema_migration +
  test_init_db_alembic_boot + test_p0_seed_backfill + test_desktop_migrations`
  → **26 passed** (264 s); `test_migrations_schema_alignment + test_p0_regression +
  test_ops01d_pg + test_ops01c_lab_pre_homologation` → **32 passed** (118 s).
- **Pendência:** a imagem do backend do lab ainda contém o código pré-correção;
  o próximo `up --build` do lab/app operacional levará a correção a produção
  (nenhuma mudança foi implantada nesta execução).

## 5. LAB-03 — Frontend + Nginx (**APROVADO**)

- `smoke-test.sh http://127.0.0.1:8088` → **9 ok / 0 falhas** (exit 0):
  SPA 200, `/health` 200, `/ready` 200, api v1 200, auth/driver 401 esperado,
  `/metrics` **404 na borda**, proxy do WhatsApp 401, login + `GET /dashboard` 200.
- Observação: o smoke só passa se `ADMIN_PASSWORD` vier do `.env.lab`
  (`set -a && . ./deploy/home-server/.env.lab && set +a`); sem isso a última
  verificação falha com "login retornou sem token". **R-2 (doc):** vale registrar
  isso no README do laboratório.
- `Get-NetTCPConnection` → 8088 com `LocalAddress = 127.0.0.1`; nenhum `0.0.0.0`.
- GasFlow Desktop em `127.0.0.1:8000`: **não estava em escuta** antes nem durante
  (estado preservado).

## 6. LAB-04 — WhatsApp isolado (**EM ANDAMENTO — inspeção concluída, pareamento pendente**)

Build da imagem `gasflow-hs-lab-whatsapp` (node:26-slim, `npm ci` + `tsc`) concluído;
primeira tentativa de `up --build` travou no passo `npm prune` (HDD 540 rpm) e foi
encerrada; a repetição finalizou o build e subiu o container.

**Modo simulação / isolamento inspecionado:**

| Verificação | Evidência |
|---|---|
| Boot **não** conecta conta | 4 linhas de log no total: `incoming.bridge.wired`, `db.default_lists_created`, `broadcast.disabled`, `api.started` — nenhum `connect`, `qr`, `session` ou `pairing` |
| Estado das contas | `primary` e `secondary`: `state=disconnected`, `connected=false`, `hasQr=false`, `phone=null`, `lastConnectedAt=null` |
| Nenhum arquivo de sessão | `/app/baileys_auth` e `/app/wwebjs_auth` **vazios**; os 5 mounts são somente volumes `gasflow-hs-lab_*` |
| Kill-switch de campanha | `WA_BROADCAST_ENABLED=false` (env **e** overlay) + log `broadcast.disabled` |
| Webhook externo | `WA_CRITICAL_WEBHOOK_URL=` (vazio) |
| Motor | `WA_ENGINE=baileys` (dual-mode; rollback `wwebjs` sem rebuild) |
| Bridge | `GASFLOW_BACKEND_URL=http://backend:8000` (rede interna) |
| Portas publicadas | **nenhuma** (`docker port` vazio) |
| Rotas protegidas | `/api/whatsapp/start` → **401**, `/api/whatsapp/qr` → **401** sem API key; `/metrics` → **401** (fail-closed); `/connect` → 200 (HTML estático, sem QR) |
| Healthcheck | `healthy`, 0 restarts, `{"ok":true,…}` |
| Re-verificação 13:02 | `/api/ready` → `{"ready":true,"total":2}`; `/api/whatsapp/start` → 401; `/app/baileys_auth` e `/app/wwebjs_auth` ainda **vazios**; `WA_BROADCAST_ENABLED=false`, `WA_CRITICAL_WEBHOOK_URL=[]`, `WA_ENGINE=baileys` |

**Pendente (ação humana, critério 5 do gate):** parear um **número de teste
dedicado** via `POST /api/whatsapp/accounts/:id/start` + QR e enviar a mensagem de
prova ponta a ponta. Nada disto foi automatizado nesta execução e **nenhum QR foi
fotografado ou copiado para documentação** (P1-3 permanece sob disciplina humana).

**🔎 Análise de simulador (28/10, 14:35 — inspeção de código, sem pareamento/QR/envio):**

- **Não existe simulador de WhatsApp verdadeiro em runtime.** O único artefato de
  simulação é `whatsapp/tests/mocks/mock-provider.ts` (`MockWhatsAppProvider`,
  "unit test mock that never starts a browser") — importado **apenas** pelos testes
  unitários (`tests/*.test.ts`); nenhum import em `whatsapp/src/`.
- Em runtime o motor é fechado: `type EngineName = 'wwebjs' | 'baileys'`
  (`src/provider/provider-manager.ts:65`), resolvido por `WA_ENGINE`/`WA_ENGINE_*`
  (default `baileys`). **Nenhuma env seleciona mock/sim.** O comentário sobre
  "engine fake" (linha 483) é apenas documentação do método público
  `handleEngineEvent` usado por testes.
- **Não há flag `DRY_RUN`/`SEND_DISABLED`** para envios individuais.
  `WA_BROADCAST_ENABLED=false` desliga **apenas campanhas** (`broadcast.ts:35,49`)
  — não é garantia de simulador, conforme restrição da tarefa.
- **Conclusão: sem simulação segura de ponta a ponta → testes de envio do LAB-04
  permanecem BLOQUEADOS.** Cobertura atual de envio é só unitária (mock). Concluir
  o gate exige pareamento humano com número de teste dedicado (ação não autorizada
  nesta execução).

## 7. LAB-05 — Backup + restauração com dado fictício (**APROVADO**)

| Etapa | Comando | Resultado |
|---|---|---|
| a. Dump sintético sem servidor | `python scripts/home-server/data/pg_backup.py --mock --execute --out "$TEMP/gf-lab-bk"` | **exit 0**, `status: verified`, `magic_ok: true`, dump 69 B + relatório JSON (manifest 508 B) |
| b. Dump real do banco fictício | `pg_dump -U gasflow_lab -d gasflow_lab --format custom --file /tmp/gasflow_lab.dump` (dentro do container; senha só via socket/`pg_isready`, **nunca em argv**) | **exit 0**, **225.526 bytes** |
| c. Banco descartável de restore | `CREATE DATABASE gasflow_lab_restore;` | OK — `pg_database` lista só `gasflow_lab` e `gasflow_lab_restore` |
| d. Restauração | `pg_restore -d gasflow_lab_restore --exit-on-error /tmp/gasflow_lab.dump` | **exit 0**, sem erros |
| e. Verificação de schema | diff das listas de tabelas origem × restore | **69 = 69, diff vazio**; `alembic_version = a4b5c6d7e8f9` nos dois |
| f. Re-verificação 13:02 | `psql` nas duas bases | `gasflow_lab` 69 tabelas · `gasflow_lab_restore` 69 tabelas, `alembic_version = a4b5c6d7e8f9` · artefatos `%TEMP%\gf-lab-bk` presentes (dump 69 B + manifesto 508 B) |

Critérios do gate: nenhum arquivo escrito no repositório (`git status --short`
**idêntico** ao estado inicial), artefatos só em `%TEMP%\gf-lab-bk`, nenhum dump
com dado real (somente `gasflow_lab`), nenhuma senha em linha de comando,
nenhuma sobrescrita.

### 7.1 Aprofundamento de integridade (28/10, 14:33–14:45)

**Investigação do «dump de 69 bytes vs 69 tabelas» — COINCIDÊNCIA, não relação:**

- O arquivo de **69 bytes** é o artefato do modo mock:
  `pg_backup.py --mock --execute --out %TEMP%/gf-lab-bk` →
  `gasflow-20261028T150746Z.dump` = magia `PGDMP` (5 B) + 1 linha de comentário
  `-- ops01d mock dump: artefato de laboratorio, nenhum dado real` = exatamente
  69 bytes; manifesto 508 B com `"mode": "mock"`, `"status": "verified"`,
  `"magic_ok": true`. **Não é restaurável e nunca foi usado no restore.**
- O arquivo **usado no restore** é `/tmp/gasflow_lab.dump` (dentro do container
  `gasflow-hs-lab-postgres`): **225.526 bytes**, formato **custom do pg_dump**
  (magia `PGDMP`), **sha256 `8813f799c945e3f72d74aaf0a5c8a157ed98be0edb7e13abdddb5fbb95d57d2e`**,
  mtime 28/10 **15:08 UTC**. TOC (`pg_restore --list`): **632 entradas**,
  incl. **69 seções `TABLE DATA`** — o 69 das tabelas é o schema real; os 69 bytes
  do mock são acaso.

**Linhagem de `gasflow_lab_restore` (reconstruída do arquivo, não de migrations/auto-init):**

| Evidência | Resultado |
|---|---|
| `pg_stat_activity` (todos `gasflow_lab%`) | só `gasflow_lab` com 3 backends do app + 1 `psql`; `gasflow_lab_restore`/`gasflow_lab_itest` = **0 conexões de app** |
| DSNs dos containers | `DATABASE_URL` de todos → **apenas `gasflow_lab`** (nenhum aponta para restore/itest) |
| Tabelas `_schema_version` (produto do init_db legado) | **ausente** nas 3 bases → cadeia de migrações leves nunca rodou contra restore/itest |
| Origem dos dados | conteúdo idêntico ao arquivo do dump (prova abaixo) — sem processo alembic/uvicorn conectou |

**Teste de restauração independente (banco descartável `gasflow_lab_itest`):**
criado do zero, `pg_restore --exit-on-error /tmp/gasflow_lab.dump` concluído
(sem erros observados — verificado por comparação de conteúdo completo):

| Verificação | Resultado |
|---|---|
| Schema | **69 tabelas** = restore; **299 índices** = restore; **113 constraints** = restore; **0 constraints não validadas** (`pg_constraint WHERE NOT convalidated`) |
| `alembic_version.version_num` | `a4b5c6d7e8f9` (idêntico) |
| Contagem por tabela | **diff VAZIO entre as 69 tabelas** (restore × itest) |
| Registros de teste (dados sintéticos) | `auth_users=3`, `auth_roles=7`, `permissions=78`, `role_permissions=65`, `auth_tenants=3` |
| Dados (`pg_dump --data-only`, `estrict` filtrado) | **idênticos** — 1.108 linhas, diff **vazio** |
| Schema (`pg_dump --schema-only`, `estrict` filtrado) | **idêntico** — 5.001 linhas, diff **vazio** |

Conclusão: `itest` foi reconstruído **integralmente do arquivo** e é indistinguível
de `gasflow_lab_restore` em schema e dados → o restore anterior também veio do
arquivo, não de migrations/auto-init.

**Deriva esperada origem × restore (não é defeito):** só 2 das 69 tabelas diferem,
ambas **vivas** e escritas pelo backend desde o dump (15:08 UTC): `auth_audit_log`
25 vs 22 e `auth_sessions` 15 vs 13 — smoke tests e health checks posteriores
criaram sessões/auditoria. As outras 67 tabelas são idênticas.

**Limpeza:** `gasflow_lab_itest` (descartável, criado nesta execução) foi
**DROPADO** após a verificação (0 conexões antes do drop). Restam `gasflow_lab`
e `gasflow_lab_restore`. Os 5 containers e os 7 volumes `gasflow-hs-lab_*`
permanecem intactos; nenhum banco/volume pré-existente foi excluído.

## 8. Verificações estáticas repetidas (regressão)

Reexecutadas na **re-verificação final (28/10, 13:02)**, com o lab no ar:

- `./deploy/home-server/verify-static.sh` → **exit 0** (projeto, `127.0.0.1:8088`,
  segredos do `.env.lab` fora do Git).
- `pytest backend/tests/test_ops01b_homeserver_profile.py backend/tests/test_ops01c_lab_pre_homologation.py -q`
  → **48 passed** em 14,2 s.
- `./scripts/smoke-test.sh http://127.0.0.1:8088` com `ADMIN_PASSWORD` do
  `.env.lab` → **9 ok / 0 falhas** (exit 0).
- `git status --short` → **6 entradas, idênticas ao estado inicial** (4 modificadas
  pré-existentes + `docs/integration/LAB_01_04_RUNTIME_REPORT.md` e `docs/ops/` não
  rastreados).
- `git check-ignore deploy/home-server/.env.lab` → ignorado (`.gitignore:98`).

## 9. Erros, achados e bloqueadores

1. **R-1 (P2): CORRIGIDO em 28/10, 14:33–14:45)** — `PRAGMA table_info` do
   `_ensure_sqlite_columns()` executava contra PostgreSQL → 1 `ERROR` por boot e
   cadeia de migrações leves abortada. Correção: seleção por dialeto em
   `init_db.py` (cadeia só em SQLite + guard na função), 5 novos testes de dialeto,
   regressão verde (26 + 32 passed) e verificação em PostgreSQL real com
   `RESULT=PASS` (0 ERROR, 69→69 tabelas, sem `_schema_version`). Detalhe na §4.
2. **R-2 (doc):** `scripts/smoke-test.sh` depende de `ADMIN_PASSWORD` exportado a
   partir de `deploy/home-server/.env.lab`; sem isso o último check falha.
3. **R-3 (infra):** build do gateway travou no passo `npm prune` na primeira
   tentativa (HDD 540 rpm); repetição concluiu. Risco de tempo de build já
   registrado como P2.
4. **R-4 (ambiente):** primeira tentativa de `up` terminou com um container
   `gasflow-hs-lab-whatsapp` em estado `Created` (conflito de nome); resolvido na
   sequência pelo próprio compose — sem remoção manual de recursos de terceiros.
5. **R-5 (doc, menor):** `deploy/home-server/.env.lab` começa com BOM UTF-8,
   gerando `line 1: $'\357\273\277#': command not found` ao fazer `source` no Git
   Bash (o smoke continua verde porque o erro é ignorado, mas convém remover o BOM).
6. **Nenhum bloqueador de segurança:** nenhuma porta pública, nenhuma sessão fora
   dos volumes do lab, nenhum arquivo de `data/` copiado, nenhum dado real exposto.

## 10. Estado final e próxima etapa

O laboratório **continua no ar** (5 containers `healthy` na re-verificação de
13:02 — `down` **não** foi executado; parar ou descartar é decisão do operador):

```bash
# parar preservando dados do lab
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab down
# descarte total (só volumes gasflow-hs-lab_*)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab down -v --remove-orphans
```

**Próximos passos:** (1) pareamento humano do **número de teste** para concluir o
LAB-04 — **sem simulador local existente, os testes de envio permanecem bloqueados**
até o pareamento (não autorizado nesta execução); (2) gate LAB-06 (aceite) com os
artefatos de `%TEMP%\gf-lab-bk` removidos; (3) **R-1 concluído** — falta apenas
rebuild da imagem do backend (`up --build`) para levar a correção ao lab/prod
(frente separada, não executada aqui).

Esta execução de aprofundamento **não** realizou push, merge, deploy, reset,
`down`/`down -v`, migration em banco operacional, backup operacional, pareamento,
geração de QR ou envio de mensagens — e **não** excluiu nenhum banco ou volume
pré-existente (apenas o banco descartável `gasflow_lab_itest` criado por esta
própria execução, após concluir suas verificações).
