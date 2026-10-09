# Diagnóstico de CI — 2026-10-09

Escopo: entender por que o CI do `main` está vermelho, por que o E2E passou de
45 min e foi cancelado, e o que Trivy/E2E "skipped" significam. Sessão de
diagnóstico — nenhum código de produto foi alterado; as únicas mudanças são de
workflow (`.github/workflows/*`).

Método: API pública do GitHub Actions (`gh` CLI não está instalado neste
ambiente; logs de job exigem autenticação e retornam 403 anônimo), mais
reprodução local em worktrees descartáveis (`git worktree add` em
`%TEMP%`, removidos ao final).

## Estado das runs (evidência)

Runs do workflow `CI` (id 330638959), pushes para `main`:

| Run | Conclusão  | Commit  | Data (UTC)        |
|-----|------------|---------|-------------------|
| 174 | **failure**  | `68dfcc1` | 2026-10-07 18:21  |
| 161 | success    | `1acd033` | 2026-09-24 12:51  |
| 160 | success    | `5302c09` | 2026-09-24 12:44  |

Última `main` verde: **run 161 @ `1acd033` (24/09)**. A run 174 é o primeiro
push de CI após a Fase 3 do renomeador (`aaa7c42`, 07/10) e falhou.

Jobs da run 174 (API `/actions/runs/37666209440/jobs`):

| Job                              | Conclusão |
|----------------------------------|-----------|
| Backend (ruff + pytest)          | **failure** — falhou no step `Type check (mypy baseline)` |
| WhatsApp service                 | success   |
| Frontend (typecheck + build + tests) | success |
| Agent                            | success   |
| Migrations (PostgreSQL, banco zerado) | success |
| Trivy                            | **skipped** (cascata do `needs: [backend, frontend, whatsapp, agent]`) |
| E2E (Playwright, full stack)     | **skipped** (cascata do `needs: [backend, frontend]`) |

Ou seja: **uma única causa real** (mypy no backend) deixa Trivy e o E2E do
`ci.yml` "skipped" — não são falhas independentes.

## 1. Backend vermelho = 4 erros de mypy no `renamer.py`

- Reproduzido localmente em worktree do commit `68dfcc1`:
  `python -m mypy app` → `Found 4 errors in 1 file (checked 337 source files)`
  (todos em `app/.../renamer.py`, introduzidos pela Fase 3 do renomeador).
- O step `ruff` e o `pytest` não são o problema: o job morre no mypy antes.
- **Já corrigido localmente** no commit `215238d` ("chore(ci): mypy zero
  errors — corrige 4 erros de tipos no renomeador"); em `cab9be4` o mypy
  roda com `Success: no issues found`. Os 12 commits ainda não foram
  pushados (`main...origin/main [ahead 12]`), então o CI remoto nunca viu a
  correção.
- Pin atual do tipo: `mypy==2.3.1` (idêntico ao de `1acd033`; o código de
  `1acd033` é limpo sob esse pin — verificado em worktree: `Success: no
  issues found in 314 source files`).

**Conclusão:** o push dos commits pendentes torna o job Backend verde. Nenhuma
mudança de workflow é necessária para esse item.

## 2. E2E ">45 min cancelado" = travou na instalação de deps, não nos testes

Run 132 do workflow `E2E` (`e2e.yml`, id 355889490) em `68dfcc1`:
`cancelled` após 45,5 min (bateu o `timeout-minutes: 45`). Timings dos steps
(API `/actions/runs/37666209430/jobs`):

| Step                                    |Resultado| Duração   |
|-----------------------------------------|--------|-----------|
| Subir stack E2E (docker-compose)        | success| 56 s      |
| Aguardar stack saudável                 | success| <1 s      |
| **Deps E2E + navegador Chromium** (`npm ci` + `npx playwright install --with-deps chromium`) | **cancelled** | **~44 min** |
| Run Playwright                          | skipped| —         |

Os 20 testes descobertos (`npx playwright test --list` local: 20 tests em 8
files) **nunca começaram**. A stack sobe em menos de 1 minuto; o tempo foi
todo gasto (provavelmente no download do Chromium via CDN ou no `npm ci`) num
bloco único sem timeout de step — o job inteiro morreu sem dizer qual dos
dois travou.

Contexto histórico: o E2E costuma passar — das 10 últimas runs do workflow,
9 `success` e apenas essa 1 `cancelled` (a run 125, de 27/09, é uma falha
pontual de teste). O cancelamento de 45 min é, até agora, um evento de infra
(não uma regressão de teste), mas precisa de blindagem para não repetir.

**Correção aplicada nesta sessão** (`e2e.yml`):

1. `actions/cache@v6` em `~/.cache/ms-playwright`, com chave por
   `hashFiles('e2e/package-lock.json')` — elimina o download do navegador em
   runs futuras (o componente lento e fora do nosso controle).
2. O bloco único virou dois steps (`npm ci` / `playwright install`), cada um
   com `timeout-minutes: 10` — se travar de novo, o nome do step aponta o
   culpado em minutos, não em 45.

## 3. Frontend "TS7/typescript-eslint" — não é um bloqueio no CI

O job Frontend da run 174 está **verde** (`tsc -b && vite build`, `eslint .`,
`vitest`). O `frontend/package.json` usa TypeScript `^6.0.3`,
`typescript-eslint` `^8.70.0` e ESLint `^10.10.0`, e a combinação passa no
CI. Nenhuma ação necessária — a suspeita de incompatibilidade não se
confirma contra a evidência remota.

## 4. PRs do Dependabot vermelhos no mypy (sem causa conhecida)

Todas as 9 últimas runs do Dependabot (27/09 e 04/10, ex.: runs 165–173)
falham no **mesmo step de mypy**, mesmo sendo PRs que só mexem em deps de
`whatsapp/` e tendo base `1acd033` — cujo código é limpo sob o mesmo pin
`mypy==2.3.1` (verificado localmente). Com logs anônimos (403) não dá para
ver o erro; as hipóteses são drift de dependências transitivas no `pip
install` daquelas datas ou alguma particularidade do ambiente do runner na
janela.

**Ação registrada (baixa prioridade):** instalar o `gh` CLI com autenticação
para ler esses logs, e fechar/superseded os PRs do Dependabot antigos. Não
bloqueia nada do plano — os commits pendentes já resolvem a `main`.

## 5. E2E duplicado: dois boots do mesmo stack por push

Hoje, cada push para `main` sobe o `docker-compose.e2e.yml` **duas vezes**:
o job `e2e` do `ci.yml` (com `needs: [backend, frontend]`, sem
`timeout-minutes`, artefato só em falha) e o workflow `e2e.yml` (com
health-gate, artefato sempre e `down -v`; é o que levou o cancelamento de
45 min). O gate do `release.yml` só exige os 4 jobs de teste
(backend/frontend/whatsapp/agent) — **E2E não é exigido pelo release**.

Opções (pendente de decisão):

- **B (recomendada)** — remover o job `e2e` do `ci.yml` e manter o
  `e2e.yml` como única definição: diff menor, o `e2e.yml` já é o mais
  completo (health-gate, artefato sempre, teardown, timeout de job), o E2E
  roda em paralelo ao resto da CI (sinal mais rápido) e o release não muda
  de comportamento.
- **A** — remover o `e2e.yml` e concentrar tudo no `ci.yml`: E2E passa a
  esperar backend+frontend (sinal mais lento) e exige portar
  health-gate/artefato/teardown/timeout para o job do `ci.yml`.

## Resumo executivo

| Sintoma                          | Causa raiz                                   | Status |
|----------------------------------|----------------------------------------------|--------|
| CI main vermelha (run 174)       | 4 erros de mypy no `renamer.py` (Fase 3)     | Corrigido em `215238d`, **pendente de push** |
| Trivy / E2E do `ci.yml` skipped | Cascata do `needs` do job Backend            | Resolve-se com o push |
| E2E cancelado >45 min (run 132)  | `npm ci` + `playwright install` sem timeout de step / download do Chromium | **Blindado nesta sessão** (cache + steps separados + timeout 10 min) |
| Frontend TS/eslint              | Job verde no CI; suspeita não se confirma    | Nada a fazer |
| PRs Dependabot vermelhos no mypy | Causa desconhecida; precisa de logs com auth | Item aberto (baixa prioridade) |
| E2E rodando duas vezes por push  | `ci.yml` (job e2e) + `e2e.yml` duplicados     | **Pendente de decisão** (opção B recomendada) |

## Evidências

- Runs: [174 (CI, failure)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/runs/37666209440),
  [132 (E2E, cancelled)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/runs/37666209430),
  [161 (CI, última main verde)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/runs/36001798787)
- Reprodução local: worktrees em `%TEMP%` dos commits `68dfcc1` (4 erros de
  mypy) e `1acd033` (limpo, 314 arquivos) — removidos após a coleta.
- Contagem do E2E: `npx playwright test --list` → 20 testes em 8 arquivos
  (suite pequena; o gargalo nunca foi o volume de testes).
