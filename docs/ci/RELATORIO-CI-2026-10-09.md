# Diagnóstico de CI — 2026-10-09

Escopo: entender por que o CI do `main` estava vermelho, por que o E2E passou
de 45 min e foi cancelado, e o que Trivy/E2E "skipped" significavam. Sessão de
diagnóstico + estabilização: as mudanças ficaram em `.github/workflows/*`,
anotações de tipo em 6 arquivos do backend, o pin do `sqlalchemy` e este
relatório.

Método: API pública do GitHub Actions (`gh` CLI não está instalado; logs de
job exigem autenticação e retornam 403 anônimo), reprodução local em worktrees
e **reprodução do ambiente de CI em WSL Ubuntu 24.04** (python 3.12 + resolve
fresco do PyPI em `~/gfdeps`; o mypy foi validado também em Windows).

## Cadeia causal completa (estado final do entendimento)

| # | Fato | Evidência |
|---|------|-----------|
| 1 | Última `main` verde: run 161 @ `1acd033` (24/09 12:51Z), com sqlalchemy 2.0.x | API `/actions/workflows/330638959/runs` |
| 2 | **sqlalchemy 2.1.0 publicado no PyPI às 24/09 20:36Z** — horas depois. `requirements.txt` tem `sqlalchemy` sem pin | `pypi.org/pypi/sqlalchemy/2.1.0/json` → `upload_time_iso_8601`; `requirements.txt:9` |
| 3 | Desde então, todo resolve fresco (CI, E2E, produção, Docker) traz 2.1.x. Os stubs novos de `Query.filter` reprovam comparadores de **colunas datetime** em estilo legado `Column(...)` — 16 erros em 6 arquivos | Reprodução em WSL: `pip install` fresco → `sqlalchemy-2.1.4` → `python -m mypy app` = `Found 16 errors in 6 files`; mesmo resultado no Windows após atualizar o `.venv-ci` para 2.1.4 |
| 4 | O `.venv-ci` local (Windows) ficou em **2.0.52**, onde os stubs são lenientes — por isso "mypy 0 erros" local nunca pegou os 16 | `pip show sqlalchemy` antes/depois: 2.0.52 → 2.1.4; mypy passa no 2.0.52, falha no 2.1.4 |
| 5 | Isso **também explica os PRs do Dependabot** (27/09 e 04/10) vermelhos no mypy com base `1acd033` "limpa": mesma causa, 16 erros, sem relação com os bumps de `whatsapp/` | Runs 165–173: falham no step de mypy; base verificada limpa sob mypy 2.3.1 + sqlalchemy 2.0.52 |
| 6 | A Fase 3 do renomeador (`aaa7c42`, 07/10) acrescentou **mais 4** erros de mypy (`renamer.py`) — corrigidos em `215238d` (commit desta série) | Worktree de `68dfcc1`: `Found 4 errors in 1 file`; `cab9be4`: `Success` |
| 7 | E2E "cancelado >45 min" (run 132, 07/10): a stack subiu em 56 s; o job morreu preso no bloco único `npm ci && playwright install --with-deps chromium` (~44 min). Os 20 testes **nunca começaram**. Evento pontual de infra (9 das 10 últimas runs do E2E foram `success`) | Timings de step da run 132 via API |
| 8 | Trivy e o E2E do `ci.yml` "skipped" eram **cascata** do `needs` do job Backend — não falhas independentes | Jobs da run 174 |

## O que foi feito nesta sessão

1. **`e2e.yml` blindado** — `actions/cache@v6` do Chromium
   (`~/.cache/ms-playwright`, chave por `hashFiles('e2e/package-lock.json')`);
   o bloco único virou dois steps (`npm ci` / `playwright install`), cada um
   com `timeout-minutes: 10`. Se travar de novo, o nome do step aponta o
   culpado em minutos, não em 45.
2. **Fim da duplicação do E2E** (opção B) — o job `e2e` saiu do `ci.yml`; o
   `e2e.yml` é a única definição (health-gate, artefato sempre, teardown,
   timeout de job). O gate do `release.yml` só exige os 4 jobs de teste,
   então nada muda no release.
3. **mypy verde nas duas plataformas** — os 16 erros corrigidos com anotações
   (`List[Any]` onde o `.all()` do 2.1.4 virou `Row[...]`) e
   `# type: ignore[arg-type]` nos 10 comparadores datetime (limitação de stub
   do 2.1.4 com colunas legadas `Column(...)`; o runtime é idêntico — o E2E
   full-stack já rodava em 2.1.4). Arquivos: `finance_reports.py`,
   `heatmap.py`, `delivery_metrics.py`, `snapshot_service.py`, `finance.py`
   (auditoria), `driver_location_service.py`.
4. **`sqlalchemy==2.1.4` fixado** no `requirements.txt` (com justificativa no
   arquivo): o gate não pode quebrar de novo porque um minor novo do PyPI
   mudou os stubs. Atualizar daqui é decisão consciente.

## Validações (evidência)

| Verificação | Resultado |
|---|---|
| `python -m mypy app` — Windows (.venv-ci, 2.1.4, mypy 2.3.1) | `Success: no issues found in 337 source files` |
| `python -m mypy app` — Linux (WSL, resolve fresco, sqlalchemy 2.1.4) | `Success: no issues found in 337 source files` |
| Suíte direcionada dos arquivos tocados (finance reports/p3, heatmap, delivery report, inventory snapshot, driver purge, p0 regression com boot completo de alembic) — Linux + 2.1.4 | **91 passed** (os 2 testes de boot do p0 só estouravam o `--timeout=180` artificial do diagnóstico sob o WSL lento; passam com timeout folgado e passavam/Passarão no CI nativo) |
| E2E full-stack no CI (20 testes, stack docker com resolve fresco = 2.1.4) | **success** — run 37950103638, no mesmo push |
| Build & Push das imagens | **success** |
| `pytest` completo em 2.1.4 local | Não viável no ambiente (Windows: AppLocker bloqueia a extensão C nova `_processors_cy` do 2.1.4; WSL: lento demais para 2264 testes). O job `Backend` do CI é o árbitro final da suíte completa. |

## Estado do CI após o push do diagnóstico

- Run 37950103714 (`101d793`, CI): Backend falhava no mypy (os 16 erros
  acima — o push anterior saiu antes da correção). **Este changeset é a
  correção.**
- E2E e Build & Push: verdes no mesmo push.
- Próximos passos naturais: (a) acompanhar a run disparada por este commit —
  Backend deve ficar verde (mypy 0 + suíte direcionada 91/91 em 2.1.4);
  (b) instalar o `gh` CLI com autenticação para poder ler logs de job sem
  restrição (destrava o diagnóstico de qualquer futura falha de pytest);
  (c) considerar pinar as demais dependências diretas do backend pelo mesmo
  motivo do sqlalchemy (determinismo do gate).

## Evidências

- Runs: [174 (CI, mypy, 4 erros do renomeador)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/runs/37666209440),
  [132 (E2E, cancelado 45min na instalação de deps)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/runs/37666209430),
  [161 (CI, última main verde)](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/runs/36001798787),
  [E2E verde no push de hoje](https://github.com/matheusvinicius1406-cpu/GasFlow/actions/runs/37950103638)
- Reproduções locais: worktrees de `68dfcc1` (4 erros) e `1acd033` (limpo);
  WSL com resolve fresco (16 erros → 0 após o fix); contagem do E2E
  (`npx playwright test --list` → 20 testes em 8 arquivos).
- PyPI: sqlalchemy 2.1.0 → `2026-09-24T20:36:01Z`.
