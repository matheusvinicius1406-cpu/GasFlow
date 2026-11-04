# INT-01 — Relatório Final de Integração

> **Status:** CONCLUÍDA · **Classificação final:** CANDIDATO APROVADO PARA HOMOLOGAÇÃO
> (NÃO aprovado para produção) · **Data:** 2026-10-26
> Branch `release/home-server-candidate`, worktree `GasFlow-integration`.

---

## 1. Branch / HEAD

| Item | Valor |
|---|---|
| Branch | `release/home-server-candidate` (worktree `GasFlow-integration`) |
| Base | `213c187` (merge-base exato de `parallel/freebuff-mobile-p0` e `parallel/opencode-data`) |
| HEAD ao fechar a frente | `ebaf84ee00eaa352731dc1feefbb1fe021663f62` |
| Árvore | limpa (`git status` vazio) |
| Operações proibidas executadas? | Nenhuma: sem push, sem merge em `main`, sem reset, sem stash, sem delete |
| Worktrees originais | intactos: `GasFlow@213c187`, `GasFlow-freebuff@92e3d50`, `GasFlow-opencode@d256ac6` |

## 2. Cherry-picks — 9 commits, 0 conflitos, 0 correções

Hooks pre-commit passaram em todos (sem `--no-verify`). Verificação por domínio:
`git diff` vazio frente→integração em **ambos** os domínios — árvore integrada
byte-idêntica às branches-fonte; nenhum commit de correção foi necessário.

| # | SHA integração | Origem | Conteúdo |
|---|---|---|---|
| 1 | `7bb5250` | freebuff `28c7ff3` | perfil Docker Home Server |
| 2 | `e3c6bd8` | freebuff `36b6fa8` | readiness/aceite (docs) |
| 3 | `71e9467` | freebuff `92e3d50` | fix P0 `arrive` + URL porta 80 |
| 4 | `0f3b00b` | opencode `971de40` | rascunho ferramentas OPS-01D |
| 5 | `c683887` | opencode `9c46d1a` | read-only estrito + preservação de relatórios |
| 6 | `0792113` | opencode `9a7a431` | ensaio completo + marcador `_ops01d_run` |
| 7 | `aa7e8da` | opencode `11fb254` | docs migração |
| 8 | `6a15490` | opencode `23ca079` | 41 testes |
| 9 | `ebaf84e` | opencode `d256ac6` | `pg_backup`/`pg_restore` + 8 testes |

Auditoria pré-integração (9 commits): sem risco crítico; sem segredos; sem
arquivos `.db`/sessões novos; env examples apenas com placeholders `CHANGE_ME_*`.

## 3. Testes executados — todos verdes

| Bloco | Resultado |
|---|---|
| Backend full (`tests/`, inclui os 171 da Etapa A) | **2526 passed, 30 skipped** (21m20s) |
| Frontend | **528/528** + `build` exit 0 + eslint OK |
| WhatsApp | **160/160** + typecheck + eslint OK |
| Mobile | **75/75** + typecheck OK (`npm ci` prévio) |
| Etapa C — 3 configs Compose (prod / +homeserver / +lab) | `docker compose config --quiet` exit 0 ×3 |
| Qualidade | `ruff check` ✓ · `ruff format --check` 18 ✓ · `git diff --check` ✓ · scan de segredos ✓ |

**3489 testes passaram, 0 falhas.**

**Não executado (fora do escopo desta frente / proibido pelas regras):** E2E,
desktop/Electron, `docker compose up/down` real, migrations contra banco real,
backup/restore contra Postgres real, APK em dispositivo, WhatsApp real.

## 4. Estado do Compose (validação estática — zero daemon)

Três configs `docker compose config --quiet` exit 0 (prod / prod+homeserver /
prod+homeserver+lab com env examples e `--profile observability`).

Fatos extraídos da config resolvida:

- Perfil Home Server: **única porta publicada `frontend:80`**; 8 healthchecks;
  observabilidade atrás do profile `observability`; secrets só file-based
  (`metrics_key`, `alerts_secret`) com placeholders `CHANGE_ME_*` e
  `METRICS_PUBLIC=false`; log rotation `10m×3` + `no-new-privileges` em todos.
- Laboratório (overlay `docker-compose.homeserver.lab.yml`): projeto próprio
  `gasflow-hs-lab` (volumes/rede prefixados), containers com sufixo `-lab`,
  porta `127.0.0.1:8088` em loopback, `restart: "no"`, broadcast WhatsApp
  desligado (`WA_BROADCAST_ENABLED=false`).
- Volumes nomeados: `backups_data`, `postgres_data`, `whatsapp_auth`,
  `whatsapp_data`, `whatsapp_uploads`, `whatsapp_export`, `baileys_auth`,
  `grafana_data`, `prometheus_data`.

## 5. Backups / migração

Ferramentas OPS-01D validadas **apenas em dado sintético/isolado** (49 testes +
smoke de 32 checks): dry-run padrão, rollback removendo alvo, reconciliação por
fingerprint, bloqueio de fonte alheia/DSN PostgreSQL/sem `--strict`, marcador
`_ops01d_run`, preservação de relatórios.

**Nunca** executadas contra `C:\gf\backend\gasflow.db` ou Postgres real —
migração real segue **não autorizada/não validada**. A validação real será
objeto do LAB-01 (ver `OPS_01C_LAB_PLAN.md`).

## 6. Android / WhatsApp

- **APK:** não construído (SDK fora do escopo da integração); a lógica TS do
  app está coberta por 75 testes + typecheck. Pendência física: P1-4.
- **WhatsApp:** 160 testes + typecheck; sessão real/QR nunca exercitados
  nesta máquina (P1-5 — exige ação humana e número dedicado).

## 7. Demonstrável hoje (sem daemon)

1. Frontend buildado (528 testes + build).
2. Fluxo do app `start → arrive → complete` (P0-1 corrigido e testado).
3. URL do Home Server na porta 80 orientada no login (P0-2 corrigido).
4. Contratos de readiness mobile↔backend.
5. Perfis Docker Home Server/Lab estaticamente válidos.
6. Ensaio de migração/backups em dado sintético (OPS-01D).

## 8. Bloqueadores

**Homologação (próxima fase, por design — não bloqueia a entrada):**
subir a stack do laboratório, dispositivo físico, pareamento WhatsApp
supervisionado, rehearsal SQLite→PG real.

**Produção (pendências P1/P2 — 12 na conta oficial de
`docs/delivery/PENDENCIAS_BLOQUEANTES.md`):**

| ID | Pendência |
|---|---|
| P1-1 | Fila offline do app volátil (memória) |
| P1-2 | GPS só em primeiro plano (`@ikolvi/tracelet` não compila) |
| P1-3 | CI sem job mobile (testes do app não rodam no CI) |
| P1-4 | Validação física do app pendente desde v1.2.1 |
| P1-5 | WhatsApp real nunca exercitado nesta máquina |
| P1-6 | Backup/restore/migração SQLite→Postgres não executados em dado real |
| P1-7 | Idempotência do app não chega ao servidor (`client_action_id` ignorado) |
| P1-8 | `alembic upgrade head` no boot sem backup prévio automático |

## 9. Riscos

- `data/prototype-contacts/app.db` está **versionado no repo original**
  (commit `028d79a`, pré-existente à integração) — preservado, fora do escopo;
  ver inspeção de metadados em `OPS_01C_LAB_PLAN.md` (item 7).
- Build do frontend gera chunk >500 kB (aviso não bloqueante).
- 30 skips nos testes de backend.
- Testes mobile/E2E sem job de CI (P1-3).

## 10. Classificação final

> **CANDIDATO APROVADO PARA HOMOLOGAÇÃO.**
>
> Integração sem conflitos, 0 correções, 3489 testes verdes, documentação
> completa, Compose validado estaticamente, ambos os P0 da demo corrigidos.
>
> **NÃO aprovado para produção:** migração real, backup/restore real e
> validação operacional (dispositivo/WhatsApp) nunca executados; 12
> pendências P1/P2 documentadas. Não informar "pronto para produção".

## 11. Próxima ação

Abrir a janela de homologação progressiva conforme
`docs/integration/OPS_01C_LAB_PLAN.md`: stack do lab em servidor dedicado,
APK em aparelho, pareamento WhatsApp supervisionado — sempre com backup
prévio obrigatório antes de qualquer `alembic upgrade head` (guarda OPS-01D).

## 12. Verificação git final

| Item | Valor |
|---|---|
| Branch | `release/home-server-candidate` |
| HEAD | `ebaf84e` (HEAD de fechamento da INT-01; ver atualização OPS-01C-A abaixo) |
| Commits auditáveis | base `213c187` + 9 cherry-picks (+ docs) |
| Árvore | limpa |
| Push/merge | nenhum realizado |
| Worktrees preservados | `GasFlow`, `GasFlow-freebuff`, `GasFlow-opencode` nas revisões originais |

## 13. Atualização de pré-homologação OPS-01C-A — 2026-10-27

Esta seção registra a auditoria posterior sem alterar os resultados históricos
da INT-01 acima.

- Estado inicial local: branch `release/home-server-candidate`, HEAD
  `ebaf84ee00eaa352731dc1feefbb1fe021663f62`, sem commits posteriores.
  `GasFlow-integration` existia; os outros três worktrees permaneceram intactos.
- A árvore já estava modificada antes desta execução: `.pre-commit-config.yaml`,
  `deploy/home-server/README.md`, `docker-compose.homeserver.lab.yml`,
  `backend/tests/test_ops01c_lab_pre_homologation.py` e
  `docs/integration/`. Esses arquivos foram preservados e concluídos.
- O Compose resolvido foi testado com variáveis de processo hostis:
  `DATABASE_URL` externo, `POSTGRES_DB`/`POSTGRES_USER` diferentes,
  `FRONTEND_PORT=0.0.0.0:80` e `COMPOSE_PROJECT_NAME` diferente. O overlay
  agora fixa o DSN em `postgres:5432/gasflow_lab`, o bind em
  `127.0.0.1:8088`, e os comandos fixam o projeto com `-p gasflow-hs-lab`.
- Validação desta etapa: **47 testes OPS-01B/01C aprovados**; `ruff check`
  e `ruff format --check` aprovados; `verify-static.sh` aprovado via Git Bash;
  Compose `config` resolvido nos perfis real/lab com e sem observabilidade.
  `git diff --check`, validação YAML do pre-commit e scan de padrões de segredo
  nos 9 arquivos textuais alterados passaram (0 correspondências). Os 3.489
  testes históricos da INT-01 não foram repetidos.
- Docker CLI 29.6.2 e Compose 5.3.1 estão instalados; daemon indisponível.
  WSL2 disponível, RAM/disk e portas consultadas somente para leitura.
  Nenhum container, `up/down`, migration, backup/restore ou serviço operacional
  foi iniciado ou alterado.
- `data/prototype-contacts/app.db` permanece versionado: 2.195.456 bytes,
  SQLite íntegro, 9 tabelas; a tabela `contacts` tem 8.601 registros e campos
  pessoais (`phone`, `jid`, `name`, `push_name`, `business_name`). Só esquema,
  integridade e contagens foram consultados; nenhum registro foi impresso.
  Os filtros atuais do Electron e do contexto Docker não incluem diretamente
  esse arquivo, mas dados pessoais versionados continuam bloqueando publicação
  até decisão do proprietário. O histórico não foi reescrito.
- A configuração estática protege o início do LAB-01, mas não equivale a teste
  em runtime. Classificação OPS-01C-A: **CONCLUÍDA COM RESTRIÇÕES**; o LAB-01
  permanece pendente de autorização humana e início manual do Docker.
- Sem push, merge em `main` ou deploy.
