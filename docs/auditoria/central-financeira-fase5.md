# Central Financeira — Fase 5: validação (P12)

**Data:** 2026-09-25 · **Atualizado:** 2026-10-08 · **Escopo:** fechar a missão da Central Financeira com o E2E
de ponta a ponta (checklist §6 de `central-financeira-fase2.md`) · **Estado:**
E2E **executado** contra o stack `docker-compose.e2e.yml` — 20 testes, 19 pass
/ 1 skip — e evidências gravadas em `central-financeira-fase5-evidencias/`
(8 PNGs + o PDF do Electron, `09`, gerado pelo `printToPDF` real via
`f33ad0c`). Ainda abertos (§4): o roteiro manual das 15 seções — que também
é onde falta repetir a impressão nas demais seções.

---

## 1. O que foi entregue (P1–P12)

| PR | Commit | Conteúdo |
|---|---|---|
| P1 | `2ee58ab` | backend aditivo — params de lista, breakdowns e aging |
| —  | `73deed9` | revisão pós-P1: tenant no `update_overdue`, enum inválido vira 400 |
| P2 | `065e464` | `dre`, `products`, `projection`, `team`, `hourly`, `conciliation` |
| P3 | `97be41b` | `finance_budgets` + `finance_saved_reports`, audit e `finance.write` |
| P4 | `1b291a9` | shell da Central + presets V1 + guard `finance.read` (rota transitória) |
| P5 | `83e54ea` | Visão Geral (KPIs, insights, meta, gráficos, tabela) + 4 escritas em Dialog |
| P6 | `aed9a85` | analíticas I — DRE, Produtos, Orçamento, Projeção |
| P7 | `2d6f5ee` | analíticas II — Clientes, Pagamentos, Calendário, Tendência, Simulador |
| P8 | `5e280f9` | analíticas III — Conciliação, Auditoria, Salvos, Equipe, Mapa de Calor |
| P9 | `fcd5733` | impressão/PDF — `@media print`, `data-no-print`, botão Imprimir |
| P10 | `f332de1` | modo TV — fullscreen, rotação 15 s, tema escuro, ESC |
| P11 | `b5b6c7c` | remoção atômica — rota final `/finance`, redirects, telas velhas apagadas |
| **P12** | `7f5d742` | E2E `central-financeira.spec.ts` + este relatório |
| — | `06953d9` | fix Fase 8 — recebível criado na confirmação do pedido; pagamento de pedido legado materializa o título |
| — | `4986317` | fix — aba Recebíveis deixa de mandar `date_from/date_to` (filtravam por vencimento `NULL` e escondiam a ação de recebimento) |
| — | `2d097b5` | evidências — 8 screenshots + config `npm run evidencias` |
| — | `f33ad0c` | evidências — PDF do Electron (`printToPDF`) — harness do desktop + teste `fase5-pdf-electron.spec.ts` + `09-impressao-electron.pdf` |

---

## 2. Gates automáticos

Todos executados nesta sessão (frontend em `GasFlow/frontend`, backend em `GasFlow/backend`):

| Gate | Comando | Resultado |
|---|---|---|
| Typecheck | `npx tsc -b` (frontend) | **OK** (sem erros) |
| Lint | `npx eslint src` / `npx run lint` | **OK** (sem avisos) |
| Unit/integração (frontend) | `npx vitest run` | **74 arquivos / 441 testes passando** |
| Unit/integração (backend) | `python -m pytest tests/ -q` (cwd `backend/`) | **2239 passed / 30 skipped** |
| Formato (backend) | `ruff check app tests` + `ruff format` | **OK** (o pre-commit também roda os dois) |
| Guard de integridade | `ADMIN_PASSWORD=audit-password-123 python -m tests.integrity_audit` | **`findings=19 pendentes=0`** (9 `dado-invisivel` + 10 `whatsapp-sem-consumidor`) |
| E2E (execução) | `npx playwright test` com o stack em `:8080` | **20 testes — 19 passed / 1 skip em 2,8 min**; `tsc --noEmit --strict` da spec **limpo** |
| Evidências | `npm run evidencias` | **3 testes passando (1,1 min) → 8 PNGs + `09-impressao-electron.pdf`** em `central-financeira-fase5-evidencias/` |
| mypy (backend) | `python -m mypy app` | **4 erros pré-existentes** em `app/application/contacts/renamer.py` (92, 715, 728, 736) — outra missão; ver §7 |

> **Nota de ambiente (pytest):** não rode o `pytest` com `ADMIN_PASSWORD=audit-password-123`.
> `backend/tests/conftest.py` faz `os.environ.setdefault("ADMIN_PASSWORD", "test_password_123")`,
> então a variável do integrity audit **quebra todas as fixtures de login** (`/auth/login` → 401).
> O `pytest` usa o default dele; o `integrity_audit` usa `audit-password-123`.

> **Nota de ambiente (pre-commit):** nesta máquina o hook
> `check-added-large-files` não executa — o AppLocker bloqueia o
> `check-added-large-files.exe` do cache do pre-commit (`WinError 4551`), com
> ou sem diff. Os commits desta fase usaram `SKIP=check-added-large-files`
> **com o cheque feito na mão** (arquivo maior stagingado: 367 KB — o PDF da
> evidência `09`, limite do hook: 500 KB) e os demais hooks
> (`trailing-whitespace`, `end-of-file-fixer`, `check-json/yaml`, `ruff`,
> `ruff-format`) rodaram e passaram. Não é problema do repo: em ambiente sem
> AppLocker o hook roda normal.

---

## 3. E2E novo — `e2e/tests/central-financeira.spec.ts`

Cobre o roteiro do §6 num único arquivo, reaproveitando o padrão da suíte
(sessão de admin via `storageState` do `global-setup`; login real pela UI só no
1º caso, por causa do rate limiter de 5 tentativas/5 min).

| Teste | Verifica |
|---|---|
| login pela UI e menu com uma única entrada "Financeiro" | login real → `/` → sidebar com **1** link `Financeiro` e **0** de `Financeiro & Relatórios`/`Relatórios`/`Mapa de Calor`/`Central Financeira` → clique leva a `/finance` (h1 "Central Financeira") |
| sem movimentações no período mostra o empty da Visão Geral | base limpa → `Sem movimentações neste período` e a tabela (`vg-tabela`) nem existe; em base suja o caso **pula com mensagem** explicando como voltar à base limpa |
| presets de período, inclusive 180 dias | `30 dias` ativo por padrão → clicar `180 dias` → `aria-pressed` alterna e o subtítulo confirma `· 180 dias` |
| cada seção abre com o seu título e atualiza `?secao=` | itera **todas** as abas do grupo "Seções da Central Financeira" (15 com `audit.view`, 14 sem) conferindo o `h2` de cada uma e o deep-link; fecha com deep-link direto em `?secao=conciliacao` |
| cria uma despesa pela UI e ela aparece na tabela | aba Despesas → Dialog "Nova despesa" → Registrar → Dialog fecha + toast → busca no servidor (`q`) e a linha aparece |
| registrar recebimento pela tabela de Recebíveis | `seedReceivable` confirma pedido pela API (é o fix de `06953d9` que cria o título) → linha `Aberto` → Dialog "Registrar recebimento" com `R$ 120,00` → Registrar → a linha **sai** da lista de abertos e o pagamento aparece na aba Pagamentos com badge `Pago` |
| redirects de `/reports` e `/reports/heatmap` não dão 404 | `/reports` → `/finance` ✓; `/reports/heatmap` → `/finance?secao=mapa-de-calor` com `h2` "Mapa de Calor" ✓ |
| botão Imprimir usa o fallback do navegador | sem ponte do Electron, `exportCurrentViewPdf()` chama `window.print()` (stub) e o toast "Abrindo a impressão do sistema" aparece |
| modo TV entra e sai com ESC | `aria-pressed` alterna, chip "Modo TV · Visão Geral · ESC para sair" aparece e sai com `Escape` |

**Como rodar** (o stack sobe nginx no `:8080` → backend → PostgreSQL):

```bash
docker compose -f docker-compose.e2e.yml up -d --build
cd e2e && npm ci && npx playwright install chromium
ADMIN_PASSWORD=<senha-do-admin> npx playwright test central-financeira.spec.ts
```

O `global-setup` já falha com mensagem clara se o stack não estiver no ar.

**Resultado (2026-10-08, base limpa `down -v` + `up -d --build`):** suíte
inteira **19 passed / 1 skip em 2,8 min**. Os 9 casos deste arquivo passam; o
único skip é `whatsapp.spec.ts` (pareamento de QR, exige
`E2E_WHATSAPP_CONNECTED=1`), como já era o caso antes desta fase.

Duas mudanças vieram desta execução: `seedExpense`/`seedReceivable` em
`tests/helpers.ts` semeiam pela API real (o `count()` numérico virou asserção
por linha), e o teste de recebimento nasceu do bug real — sem `06953d9` o
título não existe e sem `4986317` ele é escondido pelo filtro de vencimento.

---

## 4. Checklist §6 do plano

- [x] **E2E novo** (`central-financeira.spec.ts`, 9 casos) — login → menu com uma
  entrada → `/finance` abre → presets (inclusive 180) → seções/deep-link →
  caminho vazio → criar despesa → registrar recebimento → redirects sem 404 →
  Imprimir no fallback → modo TV entra/sai. *Executado contra o stack: 19
  passed / 1 skip na suíte inteira (2026-10-08).*
- [ ] **Manual por seção (15)** — roteiro pronto na §5. Parcialmente coberto de
  forma automática (abertura, `h2` e `?secao=` das 15 abas, empty da Visão
  Geral, presets, escritas, redirects); **falta** o que só o roteiro faz —
  estados de loading/error por seção, gate `VIEWER` sem botão de escrita e
  aba Auditoria escondida sem `audit.view`.
- [ ] **Impressão de cada seção principal** — quase: os dois meios estão
  fotografados. O CSS de impressão do browser está na evidência `07`
  (cabeçalho `print-only` + conteúdo sem sidebar/header) e o fallback
  `window.print` está coberto pelo E2E; o PDF real do Electron (**`f33ad0c`**)
  passou a ser evidência: `fase5-pdf-electron.spec.ts` sobe o desktop de
  verdade (`dist/main` + handler `reports:export-pdf` + gate
  `finance.export_pdf`) com userData isolado, clica **Imprimir** e grava
  `09-impressao-electron.pdf` (3 páginas, `printToPDF`, 367 KB), assegurando
  que nenhum toast "Falha ao gerar o PDF" aparece. **Falta** repetir a
  impressão nas demais seções principais pelo roteiro manual.
- [x] **Screenshots + evidências** — 8 capturas do stack real em
  `central-financeira-fase5-evidencias/`, geradas por `npm run evidencias`
  (ver §5), mais o PDF `09` do mesmo run.

> Os dois itens abertos se resumem ao roteiro manual da §5 (o de impressão só
> falta repetir nas demais seções): o que era automatizável (E2E, evidências e
> o PDF do Electron) foi executado e validado, e o que depende de ritual humano
> (estados de loading/error, gate VIEWER, aba Auditoria sem `audit.view`,
> impressão seção a seção) segue explicitamente pendente.

---

## 5. Roteiro manual (seções, impressão e gate de permissão)

**Por seção (15)** — para cada uma em `?secao=<slug>`, conferir os 5 estados:
loading (com rede lenta/throttle), error (derrubar o endpoint → `ErrorState` com
retry), empty (preset "Hoje" num dia sem movimento), dado real e o gate de
permissão (sessão **VIEWER** → sem botões de escrita; **sem `audit.view`** → a
aba Auditoria some e o deep-link mostra "Sem permissão").

| Seção | Ponto de atenção |
|---|---|
| Visão Geral | 4 escritas em `Dialog`; CSV só habilitado com período carregado |
| DRE | `empty` quando sem receita e sem despesa; aviso de `cmv_coverage` |
| Produtos | `cost_known=false` → margem "—" |
| Orçamento | aviso "Orçamento = mês corrente" quando o preset ≠ 30 dias; salvar exige `finance.write` |
| Projeção | série diária vazia → empty |
| Clientes | aging + lista de cobrança (sem automação — V6 fora de escopo) |
| Pagamentos | agrupamento por forma |
| Calendário | heatmap dia×hora |
| Tendência | média móvel 7d + regressão (cálculo no cliente) |
| Simulador | what-if (cálculo no cliente) |
| Conciliação | semântica "a revisar", nunca "erro" |
| Auditoria | gate `audit.view` no front **e** no backend; aviso "sem backfill" |
| Relatórios Salvos | criar/remover em `Dialog`; exige `finance.write` |
| Equipe | embute `DeliveryCharts` (4 gráficos) |
| Mapa de Calor | `MapaCalorSection` (Leaflet) |

**Impressão** — por seção principal: (a) no Electron, o botão **Imprimir** deve
gerar o PDF via `printToPDF` do conteúdo renderizado (modo `pdf`) — **já
provado para a Visão Geral** pelo teste `fase5-pdf-electron.spec.ts` (evidência
`09` abaixo), que sobe o app real pelo harness
`desktop/scripts/evidence-pdf-harness.js` (userData isolado em `%TEMP%`,
apontado ao stack em `:8080` com sufixo `/api` no gate, WhatsApp/impressão
desligados, diálogos nativos auto-recusados e `shell.openPath` capturado);
(b) no browser, deve abrir o diálogo do sistema (modo `print`) com o cabeçalho
`print-only` (marca + "Central Financeira · <seção>" + período + gerado em) e o
rodapé com as 3 assinaturas; sidebar/header/ações ficam ocultos (`data-no-print`).

**Evidências** — gravadas em `docs/auditoria/central-financeira-fase5-evidencias/`:

| Arquivo | Mostra |
|---|---|
| `01-visao-geral-30d.png` | Visão Geral, preset de 30 dias, KPIs com dado real (recebimentos, despesas, a receber) |
| `02-visao-geral-180d.png` | mesma tela no preset de 180 dias |
| `03-secao-dre.png` | DRE (seção analítica do P6) |
| `04-secao-clientes.png` | Clientes com aging (P7) |
| `05-secao-conciliacao.png` | Conciliação (P8) |
| `06-recebiveis-aba.png` | aba Recebíveis com título **Aberto** e a ação "Registrar pagamento" — o registro de `06953d9` + `4986317` |
| `07-impressao-visao-geral.png` | `@media print`: sidebar/header ocultos, cabeçalho `print-only` com marca, seção, período e "Gerado em" |
| `08-modo-tv.png` | modo TV ativo com o chip "ESC para sair" |
| `09-impressao-electron.pdf` | PDF de 3 páginas gerado pelo `printToPDF` do Electron (`f33ad0c`) sobre a Visão Geral — magic `%PDF-1.4`, Skia/PDF, 367 KB |

Regenerar (base limpa → seed determinístico → 8 capturas + PDF):

```bash
docker compose -f docker-compose.e2e.yml down -v
docker compose -f docker-compose.e2e.yml up -d --build
cd e2e && npm run evidencias
```

São 3 testes: `fase5-evidencias.spec.ts` (as 8 capturas), a sanidade dos
nomes e `fase5-pdf-electron.spec.ts` (o PDF, que precisa do `desktop/node_modules`
e do `dist/main` versionado). Tudo numa config própria
(`playwright.evidencias.config.ts`, `testDir: ./scripts`), então a suíte de CI
nunca depende de nem altera o estado da base para fotografar.

---

## 6. Riscos residuais (§7 do plano) — situação

| Risco | Situação |
|---|---|
| HTML do protótipo (R1) | Mitigado por D1: nenhuma arquitetura dependeu dele |
| CMV/margem vazia sem notas | Coberto: `cmv_coverage`/`cost_known` + empty explicando o que preencher |
| Auditoria sem histórico | Coberto: seção avisa que a trilha começa no deploy |
| Conciliação "divergência legada" | Coberto: semântica "a revisar" |
| `/reports/*` sem cache com 180d | Endpoints pesados com cache de 5 min |
| `tela-sem-link` latente | Não dependemos (regra 5 do §4) |
| VIEWER perde escrita (V3) | Aceito no veto; `finance.write` não vai para VIEWER |

**Fora de escopo (mantido):** régua automática de cobrança (V6) · UI de estorno ·
guard de permissão nos **GETs** do backend (V7, PR próprio pós-P3) · app Android ·
lib nova de gráficos/UI.

---

## 7. CI — constatações desta fase

| Achado | Detalhe | Efeito |
|---|---|---|
| `e2e.yml` roda incondicionalmente | dispara em push para `main` **e** em `pull_request`; job `playwright` com `timeout-minutes: 45` | run **132** (push em `main`, `68dfcc1`, 2026-10-07) foi **cancelado** no step "Deps E2E + navegador Chromium": o Playwright nunca rodou e o artifact ficou vazio. CI cego por tempo, não por skip |
| Existe um 2º E2E no `ci.yml` | job `e2e:` ("E2E (Playwright, full stack)") com `needs: [backend, frontend]` | quando o job Backend falha, o E2E de lá aparece **skipped** (ex.: run 37165841946, PR do dependabot) — duas pipelines disputando o mesmo papel |
| `mypy` vermelho no `main` | `python -m mypy app` → 4 erros pré-existentes em `app/application/contacts/renamer.py` (92, 715, 728, 736) | job Backend falha ⇒ o `e2e` do `ci.yml` nunca executa. É do renomeador, não desta fase |
| Runs de PR passam rápido demais | runs 127–131 verdes em ~2,5 min, com o step "Run Playwright" em **~11 s** e relatório de 208 KB | incompatível com os **2,8 min** medidos localmente; os logs de job exigem login (403 na API pública) e não puderam ser auditados |
| Único skip legítimo da suíte | `whatsapp.spec.ts` exige `E2E_WHATSAPP_CONNECTED=1` (pareamento de QR) | **19 pass / 1 skip** é o resultado esperado de uma base limpa |

Follow-up sugerido (fora do escopo desta fase): corrigir o `mypy` de
`renamer.py`, desempilhar os dois E2Es (remover o de `ci.yml` ou condicionar o
`e2e.yml` ao backend verde) e investigar os ~11 s do step de Playwright nos PRs.
