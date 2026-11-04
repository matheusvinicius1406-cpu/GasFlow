# OPS-01C-A — Pré-homologação: plano do laboratório progressivo (LAB-01)

> **Status:** preparação ESTÁTICA concluída · **Nada foi iniciado:** nenhum
> container, migration, backup operacional, push ou deploy nesta entrega.
> **Data das verificações:** 2026-10-26/27 · **HEAD:** `ebaf84e` +
> commits desta frente (ver `INT_01_FINAL_REPORT.md`), branch
> `release/home-server-candidate`.

Este plano é a ponte entre a INT-01 (integração concluída, ver
`INT_01_FINAL_REPORT.md`) e o **LAB-01** (primeira subida real do
laboratório). Ele responde aos sete pontos de verificação pedidos, classifica
os riscos, define os **seis gates LAB-01…LAB-06** com pré-requisitos,
comandos, resultados esperados, critérios de aprovação, condições de abortar
e limpeza — e registra a **preparação do LAB-01** — seguindo o procedimento
de `deploy/home-server/README.md` (§8), sem substituí-lo.

Gate estático correspondente: `backend/tests/test_ops01c_lab_pre_homologation.py`
(roda junto com `test_ops01b_homeserver_profile.py`, sem daemon).

---

## 1. Verificações executadas (somente leitura/estáticas)

### 1.1 Isolamento do laboratório da operação atual — **CONFIRMADO**

Resolução estática com `docker compose -p gasflow-hs-lab config --format json`
(prod + homeserver + lab + `.env.lab.example`, com observabilidade):

| Artefato | Laboratório | Operação atual (intocada) |
|---|---|---|
| Projeto Compose | `gasflow-hs-lab` (fixado também por `-p`) | `<dir>` (ex.: `gasflow`) / Desktop fora do Docker |
| Containers | `gasflow-hs-lab-*` (8) | `gasflow-*` / processos Desktop |
| Volumes (runtime) | `gasflow-hs-lab_postgres_data`, `_whatsapp_auth`, `_baileys_auth`, `_whatsapp_data`, `_whatsapp_uploads`, `_whatsapp_export`, `_backups_data`, `_prometheus_data`, `_grafana_data` | volumes reais com outro prefixo |
| Rede | `gasflow-hs-lab_internal` | rede da stack real |
| Credenciais | `.env.lab.example` mantém placeholders `CHANGE_ME_lab_*`; `.env.lab` local, ignorado pelo Git, usa segredos fortes e exclusivos do laboratório; `MARCOS_GAS_API_KEY` e `GASFLOW_SERVICE_KEY` compartilham a chave service-to-service exigida pelo app; banco fixado em `gasflow_lab` | `C:\gf\.env` e `C:\gf\backend\.env` existem e **não são lidos por este stack** |
| Bind mounts | apenas configs de `monitoring/` (read-only) — **nenhum bind de dados/sessão** | — |

Evidências adicionais: `deploy/home-server/.env.lab` já existia no início da
auditoria, está ignorado pelo Git e contém somente placeholders para as
credenciais; nenhum `.env` de produção existe no worktree. A árvore inicial
não estava limpa: havia três arquivos modificados e os documentos/teste OPS-01C-A
como não rastreados; esse trabalho foi preservado e integrado nesta execução.

### 1.2 `alembic upgrade head` exclusivamente sobre PostgreSQL novo — **CONFIRMADO**

- Comando do backend no stack do lab (config resolvida):
  `sh -c alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`
  (a migração **antecede** o boot do uvicorn).
- `backend/migrations/env.py` resolve o DSN **exclusivamente** de
  `os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")` e sobrescreve
  `configuration["sqlalchemy.url"]` — o `sqlalchemy.url` estático do
  `alembic.ini` nunca vence em runtime.
- No lab, o overlay fixa
  `DATABASE_URL=postgresql+psycopg2://gasflow_lab:…@postgres:5432/gasflow_lab`
  → host é o serviço interno `postgres` (sem porta publicada), banco
  `gasflow_lab` em volume **novo** `gasflow-hs-lab_postgres_data` (inexistente
  hoje; `-p gasflow-hs-lab` impede que `COMPOSE_PROJECT_NAME` herdada reutilize
  volumes/rede de outro projeto).
- A resolução foi testada com um `DATABASE_URL` hostile apontando para
  `outside.invalid`; o backend continuou resolvendo para `postgres:5432/gasflow_lab`.
- Risco residual documentado (P1-4 abaixo): rodar `alembic` no **host** sem
  `DATABASE_URL` cai no default SQLite relativo ao cwd. Regra: migrar
  **somente** dentro do container do lab, nunca no host.

### 1.3 Conflito de portas com o GasFlow Desktop (`127.0.0.1:8000`) — **CONFIRMADO (sem conflito)**

- Única porta publicada pelo stack do lab: **`127.0.0.1:8088`** (frontend).
  `docker compose` do lab **não** publica 8000, 80, 5432, 6379, 3000, 9090.
- Varredura de escuta hoje (host): `8000`, `8088`, `80`, `5432`, `3000`,
  `9090`, `6379` — **todos livres**; nenhum processo GasFlow/uvicorn em execução.
- O único compose que publica `8000` é o **dev** `docker-compose.yml`
  (`${BACKEND_PORT:-8000}:8000`), que **não** integra o stack do laboratório.
- **Defeitos de isolamento encontrados e corrigidos nesta entrega:**
  o compose de prod publica `"${FRONTEND_PORT:-80}:80"` e listas de `ports`
  são **somadas** no merge. Inicialmente, `FRONTEND_PORT=0.0.0.0:80` herdada
  causou bind público; `DATABASE_URL` herdada apontou para `outside.invalid`;
  `COMPOSE_PROJECT_NAME` também substituiu o nome do projeto. O overlay agora
  fixa o bind em `127.0.0.1:8088`, o DSN em `postgres:5432/gasflow_lab`, e
  todos os comandos do lab fixam `-p gasflow-hs-lab`. As três variáveis foram
  simuladas na resolução Compose e não alteraram porta, banco ou nome de
  projeto. `ports: !override` exige Compose **≥ 2.24.4**.

### 1.4 Ambiente Docker sem interferir no computador operacional — **CONFIRMADO**

- Docker CLI 29.6.2 e Compose 5.3.1 instalados; daemon **indisponível**
  (pipe `dockerDesktopLinuxEngine` inexistente; `docker info` falhou).
  `com.docker.service` não está registrado nesta instalação. Nenhum container,
  volume ou rede foi iniciado/consultado via daemon.
- Iniciar o Docker Desktop é **ação explícita do LAB-01** (gate LAB-01),
  não automação deste plano.
- Windows informou Intel Core i3-10110U (2C/4T), 11,82 GB de RAM visível,
  5,02 GB livres e 706,53 GB livres no C:. WSL mostra Ubuntu 24.04 / WSL 2.
  Portas 80, 8000, 8088, 5432, 6379 e 3000 não tinham sockets em escuta na
  leitura realizada.
- Orçamento do perfil: core **2688 MB**, com observabilidade **3360 MB**,
  tetos de CPU por serviço — projeção cabe em 12 GB; build e uso real de HDD
  continuam não medidos porque o daemon não foi iniciado.
- Desktop GasFlow: `C:\gf` existe com `.env`, `backend\.env` e
  `backend\gasflow.db` (instalação operacional — **não lida, não modificada**;
  nenhum processo ativo no momento).

### 1.5 Risco de contas WhatsApp reais / reuso de sessão — **MITIGADO (disciplina humana)**

- Sessões do lab ficam **só** em volumes prefixados
  (`gasflow-hs-lab_baileys_auth`, `gasflow-hs-lab_whatsapp_auth`); não há
  bind mount de sessão; `C:\gf\whatsapp` (sessão do Desktop, se houver) não é
  montado por este stack; `data/whatsapp` não existe no repositório.
- O gateway **não conecta conta no boot** (pareamento é ação explícita).
- Dupla trava de campanha no lab: `WA_BROADCAST_ENABLED=false` no env **e** no
  overlay; `WA_CRITICAL_WEBHOOK_URL` vazio.
- Risco residual (P1-3): parear um **número de produção** no QR do lab —
  mitigação é procedimental: somente número de teste dedicado (gate LAB-04).

### 1.6 Backup PostgreSQL testável em dados fictícios — **CONFIRMADO**

- `scripts/home-server/data/pg_backup.py`: dry-run é o padrão; `--mock
  --execute` gera dump sintético **sem servidor** (caminho exercitado por
  `backend/tests/test_ops01d_pg.py`, 8 testes verdes na INT-01); DSN com
  senha embutida é **recusado** (senha só via `PGPASSWORD`/pgpassfile).
- Caminho real no LAB-01: dump do banco fictício `gasflow_lab` com
  `pg_dump` disponível **dentro** da imagem `postgres:16-alpine`
  (`docker compose exec` no gate LAB-05 — nada executado hoje).
- Conversão SQLite→PostgreSQL segue pendente e **não autorizada** até aqui
  (`docs/data-migration/README.md`).

### 1.7 `data/prototype-contacts/app.db` — inspeção de metadados (sem registros)

**Somente esquema/contagens foi lido; nenhum registro foi exposto.**

| Indicador | Valor |
|---|---|
| Arquivo | `data/prototype-contacts/app.db` — **versionado no git** (commit `028d79a`, pré-existente à integração); sidecars `.bak`/`-shm.bak`/`-wal.bak` não existem no worktree atual |
| Tamanho / páginas | 2.195.456 bytes · 536 páginas · journal `delete` · `user_version=0` |
| Tabelas | 9 |
| Tabela de maior risco | `contacts`: **8.601 linhas** com colunas `phone`, `jid`, `name`, `push_name`, `business_name` → **contém dados pessoais (PII)** |
| Finalidade observável | Base SQLite de protótipo/contatos no diretório `prototype-contacts`; não há referência direta a esse caminho nos serviços do app nem nos filtros atuais de empacotamento |
| Demais | `lists` 13, `list_contacts` 9.412, `campaigns`/`campaign_recipients`/`contact_preferences`/`customers`/`list_members` 4 cada, `_migration_tracking` 0 |

**Indicador de risco adicional (mesmo diretório, versionado):**
`data/` contém 73 arquivos versionados (17.360.423 bytes), incluindo
42 arquivos `.txt` e 25 `.json` em `data/export-broadcast/`, além de
`data/pendentes-renomeacao-744.json` e `data/renomeador-ia-c3.json` — material
de contato de campanhas. A configuração atual do Electron limita `extraResources`
a `backend/app`, `requirements.txt`, executáveis e builds de frontend/WhatsApp;
o contexto Docker do backend ignora `*.db`. Portanto, o app.db **não aparece
incluído diretamente** nos pacotes definidos hoje, mas continua exposto no
histórico e em cópias/arquivos fonte do repositório. O
`.gitignore` já contém `*.db`, mas **arquivo rastreado vence o ignore**; não
há Git LFS. Classificação: **P1-1 (conformidade)** — fora do escopo desta
frente alterar histórico (qualquer limpeza exige decisão do dono e rewrite de
história, **proibido aqui**).

> **Agravante de publicação:** o relatório anterior registra o repositório
> remoto como público e evidência de download anônimo. Não fiz nova consulta
> remota nesta execução; considerei o estado Git local como fonte primária.
> Trate PII versionado como bloqueador para publicação/distribuição do
> repositório até decisão do proprietário. Não copie `data/` para logs, testes,
> docs ou laboratório, não apague o banco nem reescreva histórico sem autorização.

---

## 2. Classificação de riscos

### P0 — resolvido no overlay do laboratório

A resolução anterior permitia que variáveis herdadas mudassem o DSN, abrissem
`0.0.0.0:80` e renomeassem o projeto. O overlay agora fixa o DSN e a porta;
os comandos e testes fixam o projeto com `-p gasflow-hs-lab`. A resolução
estática adversarial confirmou os três valores, sem iniciar o daemon.

### P1 (abertos, com mitigação obrigatória)

| ID | Risco | Mitigação (gate) | Estado |
|---|---|---|---|
| P1-1 | PII versionado no git (`app.db` + `data/export-broadcast/*`); relatório anterior registra remoto público | não expor registros; decisão do proprietário sobre protótipo/remoção e histórico fora desta frente; nunca copiar para o lab | aberto (não bloqueia o lab; bloqueia publicação) |
| P1-2 | Variáveis herdadas poderiam substituir DSN, bind da porta e nome do projeto | DSN/porta fixos no overlay; todos os comandos usam `-p gasflow-hs-lab`; teste simula `DATABASE_URL`, `FRONTEND_PORT` e `COMPOSE_PROJECT_NAME` hostis | **RESOLVIDO nesta entrega** |
| P1-3 | Pareamento de número **real** de WhatsApp no lab | gate LAB-04: somente número de teste dedicado; broadcast já desligado em dupla | aberto |
| P1-4 | `alembic` no host sem `DATABASE_URL` cairia em SQLite do cwd | migrar somente dentro do container do lab | aberto |
| P1-5 | `alembic upgrade head` no boot sem backup prévio (P1-8 oficial) | em produção: backup OPS-01D obrigatório antes; no lab o banco é descartável (sem dado a perder) | aberto |
| P1-6 | Credenciais reais em `C:\gf\*.env` no mesmo host | stack do lab não lê esses arquivos; nunca copiá-los para `.env.lab` | aberto |
| P1-7 | Compose < 2.24.4 recusa a tag `!override` | Compose 5.3.1 instalado e versão mínima documentada; verificação estática do daemon não depende de runtime | **RESOLVIDO no host atual** |

### P2 (registrados, não bloqueiam)

HDD 540 rpm (build inicial ~10–20 min), chunk >500 kB do frontend, 30 skips
de backend, CI sem job mobile, TLS/backup off-host pendentes (README §10).

---

## 3. Gates do laboratório (LAB-01 … LAB-06)

> Comandos em bash (Git Bash/WSL), sempre na ordem
> **prod → homeserver → lab**, sempre com `-p gasflow-hs-lab` e
> `--env-file deploy/home-server/.env.lab`.
> **Nestas entregas nenhum gate abaixo foi executado.** Um gate só começa com
> o anterior **APROVADO**.

Em todos os gates valem as **Proibições permanentes** (§6).

### LAB-01 — PostgreSQL + Redis isolados

#### Pré-requisitos

- Docker Desktop iniciado **manualmente** pelo operador (engine parada hoje).
- `docker compose version` ≥ **2.24.4** (P1-7: a tag `!override` do overlay
  do lab exige isso; abaixo disso o `config` recusa o arquivo).
- `.env.lab` presente e ignorado pelo Git; todos os segredos locais devem ser
  fortes e exclusivos do laboratório. `MARCOS_GAS_API_KEY` e
  `GASFLOW_SERVICE_KEY` precisam conter a mesma chave service-to-service;
  os demais segredos devem ser independentes. O template `.env.lab.example` mantém
  `CHANGE_ME_lab_*` apenas como valores fictícios e não deve ser usado para
  iniciar o laboratório sem substituí-los.
- Árvore limpa e branch correta: `git status --short && git branch --show-current`
  → `release/home-server-candidate`.
- Nenhum container GasFlow ativo: `docker ps --format '{{.Names}}'`.
- Gate estático verde (pode rodar sem daemon):
  `./deploy/home-server/verify-static.sh` +
  `python -m pytest backend/tests/test_ops01b_homeserver_profile.py backend/tests/test_ops01c_lab_pre_homologation.py -q`.

#### Comandos

```bash
# 0. resolução (sem daemon) — porta DEVE ser 127.0.0.1:8088
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab config -q
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  config --format json | python -c "import json,sys;d=json.load(sys.stdin);print([p for s in d['services'].values() for p in s.get('ports') or []])"

# 1. subir SÓ postgres + redis (nada mais sobe nesta etapa)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  up -d postgres redis
```

#### Resultados esperados

- Dois containers `gasflow-hs-lab-postgres` e `gasflow-hs-lab-redis`,
  `docker compose ps` → `healthy` (healthchecks `pg_isready -U gasflow_lab -d
  gasflow_lab` com `start_period: 15s` e `redis-cli ping` com `start_period: 5s`).
- Nenhuma porta publicada por eles: `docker port` vazio; `Get-NetTCPConnection`
  sem 5432/6379.
- Volume criado **apenas** `gasflow-hs-lab_postgres_data`; Redis **sem volume**
  (efêmero por decisão documentada).
- Rede `gasflow-hs-lab_internal` criada; nenhum container `gasflow-*` real.

#### Critérios de aprovação

1. Ambos `healthy` em ≤ 60 s após `start_period`.
2. `docker volume ls` lista volumes só com prefixo `gasflow-hs-lab_`; nenhum
   volume de produção criado/modificado.
3. Nenhuma porta 5432/6379 escutando no host (`Get-NetTCPConnection -State Listen`).
4. `docker compose … exec postgres psql -U gasflow_lab -d gasflow_lab -c "select current_database();"`
   → `gasflow_lab` (banco novo, não o do Desktop).
5. Log do Postgres sem erro de autenticação/permissão.
6. Nenhuma migration executada nesta etapa (o backend ainda não subiu).

#### Condições de abortar

- Qualquer container criado **fora** do prefixo `gasflow-hs-lab-`.
- Porta 5432/6379 publicada, ou `up` sem `--env-file` (falha segura esperada:
  compose aborta por variável obrigatória ausente — se **não** abortar, parar).
- `docker compose version` < 2.24.4.
- Processo do GasFlow Desktop (`127.0.0.1:8000`) ausente/errante, ou qualquer
  escrita detectada fora dos volumes do lab.
- Engine Docker iniciada por automação e não pelo operador.

#### Limpeza

```bash
# só o laboratório; nunca volumes de outro projeto (prefixo próprio)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  down -v --remove-orphans
```

`down -v` apaga **apenas** `gasflow-hs-lab_*`. Se algo fora do prefixo for
afetado → abortar e investigar antes de qualquer novo `up`.

---

### LAB-02 — Backend (FastAPI + migração no boot)

#### Pré-requisitos

- LAB-01 **APROVADO** (PG e Redis `healthy`, sem portas públicas).
- `.env.lab` presente; a resolução efetiva deve mostrar
  `@postgres:5432/gasflow_lab` e `BACKEND_WORKERS=1` (o overlay fixa o DSN).
- Nenhum backup pendente a proteger (banco do lab é descartável).

#### Comandos

```bash
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  up -d backend
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  logs backend --tail 100
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  exec postgres psql -U gasflow_lab -d gasflow_lab -c "\dt"
```

#### Resultados esperados

- Container `gasflow-hs-lab-backend` `healthy`, 1 worker (`--workers 1`).
- No log: `alembic upgrade head` conclui **antes** do uvicorn subir, sem erro.
- Schema completo **apenas** em `gasflow_lab`; zero toque em
  `C:\gf\backend\gasflow.db` (inexistente no container).
- Backend sem porta publicada no host (só rede interna `:8000`).

#### Critérios de aprovação

1. Log de migração sem `ERROR`/`Failed`.
2. `\dt` mostra as tabelas esperadas em `gasflow_lab`.
3. `docker compose … exec backend sh -c 'echo $DATABASE_URL'` confirma o DSN
   do lab (não SQLite, não banco real).
4. Nenhuma migration aplicada fora de `gasflow_lab`.
5. `docker stats --no-stream` dentro do limite de 768 MB / 1.5 CPU.
6. Nenhum bind mount gravável montado no container.

#### Condições de abortar

- Migração falhou ou aplicou em banco que não seja `gasflow_lab`.
- Backend tentou abrir SQLite (`*.db`) ou caminho de `C:\gf`.
- Limite de memória estourado repetidamente (OOM).
- Qualquer porta nova publicada no host.
- Necessidade de rodar `alembic` no **host** (P1-4: proibido).

#### Limpeza

```bash
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  stop backend
# descarte total do lab (banco incluído)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  down -v --remove-orphans
```

---

### LAB-03 — Frontend + Nginx (borda)

#### Pré-requisitos

- LAB-02 **APROVADO**.
- O overlay fixa `127.0.0.1:8088`; CORS é configurado para essa origem no env.
- Porta 8088 livre no host (confirmado na varredura desta entrega).

#### Comandos

```bash
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  up -d frontend
./scripts/smoke-test.sh http://127.0.0.1:8088
```

#### Resultados esperados

- Frontend `healthy`; **apenas** `127.0.0.1:8088` escutando (nada em `0.0.0.0`).
- Smoke verde: `/api` responde, rota de login renderiza, sem erro de build.
- Nginx não expõe `/metrics` sem autenticação (invariante O2 já coberta por
  `test_prod_stack_config.py`).

#### Critérios de aprovação

1. `Get-NetTCPConnection -State Listen | Where LocalPort -eq 8088` →
   `LocalAddress` = `127.0.0.1`.
2. Nenhuma outra porta nova em escuta (80 segue como estava: livre/inalterada).
3. `./scripts/smoke-test.sh http://127.0.0.1:8088` exit 0.
4. GasFlow Desktop continua íntegro em `127.0.0.1:8000` (ligado ou
   desligado, conforme estava).
5. `docker compose ps` mostra só serviços do projeto `gasflow-hs-lab`.

#### Condições de abortar

- Qualquer bind em `0.0.0.0`/`::` na porta 8088 ou 80.
- Porta 8000 do Desktop alterada/ocupada por container do lab.
- Smoke falhar por erro de build ou rota inesperada.
- Qualquer bind resolvido diferente de `127.0.0.1:8088`.

#### Limpeza

```bash
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  stop frontend
# parada total preservando dados do lab:
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  down
```

---

### LAB-04 — WhatsApp isolado (número de TESTE)

#### Pré-requisitos

- LAB-03 **APROVADO**.
- Número de **teste dedicado** em mãos (nunca um número de produção, P1-3).
- `WA_BROADCAST_ENABLED=false` (env **e** overlay) e
  `WA_CRITICAL_WEBHOOK_URL` vazio — conferir antes de subir.
- Nenhuma campanha agendada no ambiente real.

#### Comandos

```bash
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  up -d whatsapp
# pareamento é AÇÃO EXPLÍCITA e humana — nada de automação aqui
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  logs whatsapp --tail 100
```

#### Resultados esperados

- Container `gasflow-hs-lab-whatsapp` `healthy`, sem conta conectada no boot.
- Sessão gravada **somente** em `gasflow-hs-lab_baileys_auth` /
  `gasflow-hs-lab_whatsapp_auth`.
- QR exibido uma única vez para o operador; **nunca** fotografado para docs.

#### Critérios de aprovação

1. `docker volume inspect` das sessões mostra nome iniciando com
   `gasflow-hs-lab_`.
2. Nenhuma mensagem de campanha enviada (log sem `broadcast`).
3. Webhook crítico vazio (`WA_CRITICAL_WEBHOOK_URL=` no resolved config).
4. Nenhum arquivo de sessão criado fora dos volumes do lab.
5. Mensagem de prova manual, ponta a ponta, com o número de teste.

#### Condições de abortar

- Pareamento de qualquer número que não seja o de teste dedicado.
- `WA_BROADCAST_ENABLED=true` em qualquer campanha.
- Sessão gravada em bind mount ou fora de `gasflow-hs-lab_*`.
- QR/credencial capturado para documentação (viola §6.8).
- Webhook apontando para ambiente real.

#### Limpeza

```bash
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  stop whatsapp
# apagar a sessão do lab (só volumes do projeto)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  down -v --remove-orphans
```

---

### LAB-05 — Backup + recuperação (dados fictícios)

#### Pré-requisitos

- LAB-02 **APROVADO** (banco `gasflow_lab` com schema).
- `python scripts/home-server/data/pg_backup.py --mock --execute` já passou
  (dump sintético **sem servidor** — pode rodar desde a fase 0).
- Espaço em disco para dump temporário (~dezenas de MB) fora do `C:\gf`.

#### Comandos

```bash
# a. dump sintético SEM servidor (inofensivo)
python scripts/home-server/data/pg_backup.py --mock --execute --out "$TEMP/gf-lab-bk"

# b. dump real do banco fictício (senha só via ambiente, nunca em argv)
# Obtenha POSTGRES_PASSWORD de deploy/home-server/.env.lab por meio seguro;
# não imprima o valor nem o coloque no histórico do shell.
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  exec postgres pg_dump -U gasflow_lab -d gasflow_lab --format custom \
  --file /tmp/gasflow_lab.dump

# c. recuperação SOMENTE em banco novo descartável
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  exec postgres psql -U gasflow_lab -d postgres -c \
  "CREATE DATABASE gasflow_lab_restore;"
```

#### Resultados esperados

- Artefatos criados em diretório temporário, **sem sobrescrever** nada.
- Relatório JSON do `pg_backup` presente.
- Restore conclui em `gasflow_lab_restore` (volume/prefixo do lab).
- **Zero** toque em `C:\gf\backend\gasflow.db` e em qualquer dump real.

#### Critérios de aprovação

1. `pg_backup --mock --execute` exit 0 com relatório JSON.
2. Dump custom do `gasflow_lab` gerado e com tamanho > 0.
3. Restore em `gasflow_lab_restore` recupera o schema (`\dt`).
4. Nenhum arquivo em `C:\gf`, `data/` ou repositório foi modificado
   (`git status --short` limpo).
5. Nenhum dump contendo dado real (só `gasflow_lab`).

#### Condições de abortar

- Qualquer operação de backup/restore apontando para banco que não seja do lab.
- Necessidade de senha em linha de comando (histórico do shell).
- Sobrescrita de arquivo existente.
- Dump gerado dentro do repositório ou em `data/`.

#### Limpeza

```bash
rm -rf "$TEMP/gf-lab-bk"          # artefatos sintéticos
# banco de restauração de teste é descartável junto com o lab:
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  down -v --remove-orphans
```

---

### LAB-06 — Aceite do laboratório progressivo

#### Pré-requisitos

- Gates LAB-01 … LAB-05 todos **APROVADOS** com evidência registrada.
- Testes estáticos verdes:
  `python -m pytest backend/tests/test_ops01b_homeserver_profile.py backend/tests/test_ops01c_lab_pre_homologation.py -q`
  e `./deploy/home-server/verify-static.sh`.
- `git status --short` limpo; nenhuma migration real executada.

#### Comandos

```bash
./deploy/home-server/verify-static.sh
python -m pytest backend/tests/test_ops01b_homeserver_profile.py \
  backend/tests/test_ops01c_lab_pre_homologation.py -q
git status --short && git branch --show-current
docker ps --format '{{.Names}}'    # depois do descarte: só o que era esperado
```

#### Resultados esperados

- Todos os gates documentados como aprovados, com data e evidência.
- Nenhum artefato novo fora dos volumes do lab; repositório limpo.
- Stack do lab parada/descartada conforme a intenção do operador.

#### Critérios de aprovação

1. `verify-static.sh` exit 0 (porta resolvida `127.0.0.1:8088`).
2. Pytest OPS-01B + OPS-01C: **0 falhas** (pula só se Docker CLI ausente).
3. Nenhum `docker compose up` fora dos comandos deste plano.
4. Nenhum push/merge/reset/execução contra banco real.
5. P1-1 mantido: nenhum arquivo de `data/` copiado para logs/testes/docs.
6. Relatório final de LAB-01 escrito com o que foi aprovado e o que ficou
   pendente (P1-3, P1-4, P1-5 seguem abertos até a produção).

#### Condições de abortar

- Qualquer teste vermelho, `config -q` falhando ou porta divergente.
- Contaminado o ambiente real (volume/banco/sessão/porta do Desktop).
- Histórico git alterado, push realizado ou branch principal mesclada.
- Dado de `data/` copiado para documentação ou log.

#### Limpeza

```bash
# parada preservando dados do lab (para reuso)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  down
# descarte total — limitado aos volumes exclusivos do laboratório
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  down -v --remove-orphans
```

`down -v` **nunca** atinge volumes de outro projeto (prefixo próprio).
Depois: `docker volume ls` não pode listar nenhum `gasflow-hs-lab_*`.

---

## 4. Preparação do LAB-01 (entregáveis desta frente)

| # | Entregável | Estado |
|---|---|---|
| 1 | **Arquivo de ambiente fictício** | template `deploy/home-server/.env.lab.example` (só placeholders `CHANGE_ME_lab_*`) versionado; `.env.lab` local, **gitignored**, segredos fortes e exclusivos do laboratório, com chave backend/WhatsApp compartilhada conforme contrato |
| 2 | **Configuração de Compose resolvida** | `docker compose … config --format json` verde para prod+hs e prod+hs+lab, com e sem `--profile observability`, com `.env.production.example` e `.env.lab.example` |
| 3 | **Comandos revisados de inicialização** | ordem fixa prod → homeserver → lab, sempre `--env-file deploy/home-server/.env.lab`; só `up -d postgres redis` na primeira etapa (gate LAB-01) |
| 4 | **Critérios de verificação do PostgreSQL** | ver gate LAB-01: `healthy` via `pg_isready -U gasflow_lab -d gasflow_lab`, `current_database()` = `gasflow_lab`, **sem porta 5432 publicada**, volume `gasflow-hs-lab_postgres_data`, nenhuma migration nesta etapa |
| 5 | **Critérios de verificação do Redis** | ver gate LAB-01: `healthy` via `redis-cli ping`, **sem porta 6379 publicada**, **sem volume** (efêmero), `RATE_LIMIT_REDIS_URL=redis://redis:6379/0` apontando para o serviço interno |
| 6 | **Estimativa de recursos** | core **2688 MB** (postgres 640 + redis 128 + backend 768 + frontend 128 + whatsapp 1024) · com observabilidade **3360 MB** (+ prometheus 384 + grafana 192 + alertmanager 96) · CPU: postgres 1.0, redis 0.5, backend 1.5, frontend 0.5, whatsapp 1.0 · cabe em 12 GB com ~4,4 GB de folga (detalhe no README §4) |
| 7 | **Procedimento de parada seguro** | `down` (parada, preserva dados) sempre com os três `-f` e o `--env-file`; sem `kill`, sem `docker rm` manual, sem toque em outro projeto |
| 8 | **Roteiro de limpeza limitado aos volumes exclusivos** | `down -v --remove-orphans` — apaga **apenas** `gasflow-hs-lab_*`; verificação pós: `docker volume ls` sem nenhum prefixo do lab |

Verificação estática dos itens 2 e 6:
`./deploy/home-server/verify-static.sh` (exit 0 nesta entrega) e
`python -m pytest backend/tests/test_ops01c_lab_pre_homologation.py -q`.

---

## 5. Execução progressiva dentro do LAB-01 (fases 0–5)

> As fases abaixo são o **conteúdo** dos gates da §3, na ordem em que serão
> executadas. **Nada abaixo da fase 0 foi executado nestas entregas.**

### Pré-condições (todas obrigatórias antes da fase 1)

```bash
# P1. Docker Desktop iniciado manualmente pelo operador
docker compose version          # >= 2.24.4 (top-level name: + tag !override)
# P2. Confirme que o .env.lab local usa somente credenciais fictícias; não o
# sobrescreva se já existir.
git check-ignore deploy/home-server/.env.lab
# P3. Árvore limpa e branch correta
git status --short && git branch --show-current   # release/home-server-candidate
# P4. Nenhum container GasFlow ativo / Desktop decide-se que fica ligado
docker ps --format '{{.Names}}'
```

### Fase 0 — estática (PODE SER EXECUTADA A QUALQUER MOMENTO; sem daemon)

```bash
./deploy/home-server/verify-static.sh
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  config -q
# GATE OBRIGATÓRIO: projeto, DSN e porta devem resolver para o lab
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  config | grep -A2 "published"
```

**Aprovação da fase 0:** `config -q` verde · projeto `gasflow-hs-lab`,
DSN `postgres:5432/gasflow_lab`, publicação exatamente `127.0.0.1:8088`
mesmo com overrides hostis · nenhum
`8000`/`80`/`5432` publicado · pytest `test_ops01b_homeserver_profile.py` +
`test_ops01c_lab_pre_homologation.py` verdes.

### Fase 1 — subir só o core do lab (primeira vez que containers sobem)

```bash
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  up -d --build
```

**Aprovação:** 5 serviços `healthy` (`ps`) · `docker stats` dentro dos
limites · nenhum volume fora de `gasflow-hs-lab_*` · nenhum container
`gasflow-*` real criado · `Get-NetTCPConnection` mostrando **só** `8088`
em loopback nova · GasFlow Desktop segue íntegro em `127.0.0.1:8000`
(ligado ou desligado, conforme estava).

### Fase 2 — smoke de borda + migração no boot (banco novo/descartável)

```bash
./scripts/smoke-test.sh http://127.0.0.1:8088
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab \
  exec postgres psql -U gasflow_lab -d gasflow_lab -c "\dt"   # schema do lab
```

**Aprovação:** smoke verde · `alembic upgrade head` concluiu no log do
backend (`docker compose … logs backend`) · tabelas presentes **apenas** em
`gasflow_lab` · NENHUMA migration aplicada em banco real (inexistente nesta fase).

### Fase 3 — backup/restore PostgreSQL com dado fictício (ferramentas OPS-01D)

Comandos e critérios: **gate LAB-05** (§3).

### Fase 4 — WhatsApp com NÚMERO DE TESTE (opcional, humana)

Critérios: **gate LAB-04** (§3).

### Fase 5 — app do entregador / dispositivo (P1-4 oficial)

Fora do Docker: build do APK e teste físico — momento próprio (não faz parte
do LAB-01 Docker).

### Rollback / descarte

```bash
# Parar preservando dados do lab
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab down
# APAGAR só o laboratório ( volumes gasflow-hs-lab_* )
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml -f docker-compose.homeserver.yml \
  -f docker-compose.homeserver.lab.yml --env-file deploy/home-server/.env.lab down -v
```

`down -v` **nunca** atinge volumes de outro projeto (prefixo próprio).

---

## 6. Proibições permanentes (valem em todas as fases)

1. Nenhum `docker compose up` **fora** dos comandos deste plano (arquivos
   exatos: prod → homeserver → lab, sempre com
   `--env-file deploy/home-server/.env.lab`).
2. Nada de portas novas, `-p` diferente de `gasflow-hs-lab`, `docker-compose.yml` (dev) ou
   `docker-compose.e2e.yml`/`osrm` no stack do lab.
3. Nenhuma migration/`psql` contra banco que **não** seja `gasflow_lab`.
4. Nenhum acesso a `C:\gf\backend\gasflow.db`, `C:\gf\.env`,
   `C:\gf\backend\.env`, `C:\gf\whatsapp` ou `%APPDATA%\gasflow-desktop`.
5. Nenhum backup operacional (só os sintéticos/fictícios das fases 0/3).
6. Sem push, merge em `main`, reset, `git clean`, rewrite de histórico.
7. Sem pareamento de número real de WhatsApp; sem campanhas.
8. Nenhum registro pessoal de `data/` copiado para logs, testes ou docs
   (inclui `app.db`, `data/export-broadcast/*` e backups do mesmo diretório).

---

## 7. Resumo dos critérios (checklist de aprovação progressiva)

| Gate | Só avança se |
|---|---|
| LAB-01 | `config -q` verde **e** projeto/DSN/porta resolvidos como lab **e** testes OPS-01B/01C verdes **e** engine iniciada manualmente **e** PG/Redis `healthy` sem portas públicas |
| LAB-02 | migração concluída só em `gasflow_lab`, backend `healthy` com 1 worker, sem bind mount gravável |
| LAB-03 | smoke verde, **só** `127.0.0.1:8088` escutando, Desktop intacto em `127.0.0.1:8000` |
| LAB-04 | número de teste dedicado, sessão só em volume `gasflow-hs-lab_*`, `WA_BROADCAST_ENABLED=false`, sem QR em docs |
| LAB-05 | dump+restore fictícios concluídos com relatório, sem sobrescrita, `git status` limpo |
| LAB-06 | todos os gates anteriores aprovados com evidência; `verify-static.sh` e pytest verdes; nenhuma proibição violada |
| LAB-01 → produção | **ainda exige:** migração real SQLite→PG em cópia, backup/restore reais, dispositivo físico, WhatsApp real, P1-1..P1-8 oficiais |

---

## 8. Veredito da pré-homologação (OPS-01C-A)

> **OPS-01C-A CONCLUÍDA COM RESTRIÇÕES.** Os gates estáticos estão aptos;
> o LAB-01 ainda não foi iniciado e depende de ação humana.
>
> - **P0:** nenhum após a correção estática. DSN do backend, bind da porta e
>   nome do projeto foram testados com overrides hostis; todos permaneceram
>   em `gasflow_lab`, `127.0.0.1:8088` e `gasflow-hs-lab`.
> - **Restrições:** daemon Docker indisponível; nenhum container, migration,
>   backup/restore ou serviço real foi iniciado. Validação é estática.
> - **P1-1:** dados pessoais continuam versionados; publicação do repositório
>   e de fontes derivadas bloqueada até decisão do proprietário. O app.db não
>   consta dos filtros de pacotes Electron/Docker atuais.
> - **P1 restantes:** pareamento WhatsApp, migration automática sem backup em
>   produção e migração/restore de dados reais continuam fora deste aceite.
> - **Próximo passo humano:** após revisar a evidência estática, iniciar
>   manualmente o Docker e executar LAB-01 — esta execução não autoriza nem
>   realiza a inicialização.
