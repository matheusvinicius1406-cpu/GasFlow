# Spec — Release v1.1.7, Atualizações de Dependências e Auditoria de Integridade do App

**Data:** 21/09/2026 · **Status:** 📋 AGUARDANDO APROVAÇÃO — spec executável · **nenhuma linha de código desta spec foi escrita ainda**
**Origem:** pedido do dono — fechar a release v1.1.7 mergeando as atualizações do dependabot **e** rodar uma auditoria de integridade do app, para "não ficarem telas fantasmas ou quebradas" e "nada ficar perdido, quebrado ou sem conexão".
**Formato:** fases numeradas com critérios de aceite objetivos (mesmo padrão de `docs/entregas-cupons-spec.md`).

---

## 0. Diagnóstico — o que JÁ existe (medido no código em 21/09/2026)

A base está verde e consolidada; o trabalho aqui é **integrar, auditar e publicar** — não criar features novas.

| Área | Estado atual | Evidência |
|---|---|---|
| Backend | ruff ✅ · mypy ✅ (294 arquivos, 0 issues) · pytest 1646 passed / 27 skipped | rodado nesta sessão (15 falhas locais = só `tzdata` ausente no Windows) |
| Frontend web | build ✅ · lint ✅ · 299 testes (53 arquivos) | rodado nesta sessão |
| WhatsApp (Node) | typecheck ✅ · build ✅ · 94 testes | rodado nesta sessão |
| Agent (Node) | typecheck ✅ · build ✅ · 27 testes | rodado nesta sessão |
| Desktop (Electron) | typecheck ✅ · 71 testes | rodado nesta sessão |
| Mobile (RN) | typecheck ✅ · 33 testes | rodado nesta sessão |
| CI | jobs `backend`, `frontend`, `whatsapp`, `agent`, `migrations`, `e2e`, `trivy` | `.github/workflows/ci.yml` |
| Release | `release.yml` dispara por tag `v*`, com `ci-gate` (aguarda CI do SHA da tag) + `build-windows` (PyInstaller + electron-builder, publica no GitHub Releases) | `.github/workflows/release.yml` |
| Última tag | `v1.1.6` — HEAD está **36 commits à frente** | `git describe` → `v1.1.6-36-gd4005cc` |
| CHANGELOG | tudo em `[Unreleased]` (F1a→F10 + correção de CI/E2E/Trivy) | `CHANGELOG.md` |
| Pendências locais | `backend/requirements.txt` e `backend/gasflow-backend.spec` com a correção do `tzdata` (não commitadas) | `git status` |

### 0.1 Inventário do app (para a auditoria)

- **Navegação:** 7 grupos em `frontend/src/components/layout/nav.tsx` (`NAV_GROUPS`), fonte única usada pelo Sidebar (desktop) e MobileSidebar. Dashboard é o único item direto.
- **Rotas:** ~38 rotas em `frontend/src/App.tsx` (públicas `/login`, `/cadastro`, `/driver/login`, `/driver`; o resto sob `DashboardLayout` + `ProtectedRoute`; três sob `PermissionRoute`).
- **Páginas:** 38 `*Page.tsx`; **nenhuma órfã** — `PaymentSettingsPage`, `ConversasPage` e `WhatsAppWebPanelPage` não têm rota própria porque são renderizadas **embutidas** dentro de `SettingsPage` / `WhatsAppPage` (falso positivo clássico a tratar na allowlist).
- **Backend:** routers montados em `app/main.py` na raiz, em `/api/v1` (`api_v1_router`) e em `/api` (modo `FRONTEND_DIST`), + WebSocket de realtime. ~42 arquivos com `APIRouter`.
- **Desktop:** `desktop/src/preload/index.ts` expõe uma API `window.*` com dezenas de canais IPC (`settings:*`, `agent:*`, `ai:*`, `orders:*`, `gasflow:*`, `purchase:*`, `reports:*`, `dialog:*`, `wa:*`) + eventos (`ai:status-changed`, `ai:download-progress`, `gasflow:driver-location`).
- **WhatsApp (Node):** rotas Express em `whatsapp/src/routes.ts` (`/whatsapp/*`, `/contacts/*`, `/customers/*`, `/lists/*`).
- **Mobile:** telas `ConsentScreen`, `DeliveryDetailScreen`, `LoginScreen`, `RouteTodayScreen` + `navigation/RootNavigator.tsx` + `logic/*` (api, connection, offlineQueue, session, tracking, workHours).

---

## 1. Decisões travadas (do dono — não reabrir)

| # | Decisão |
|---|---|
| D1 | **Escopo = 3 coisas juntas:** release v1.1.7 + atualizações do dependabot + auditoria de integridade do app. |
| D2 | **Motivação é preventiva** — nada foi visto quebrado ainda; é para não publicar a v1.1.7 com telas mortas. |
| D3 | **"Perdido/quebrado/sem conexão" cobre as 6 categorias:** tela sem endpoint, tela sem link, feature fantasma, backend órfão, botão sem handler, dado invisível. |
| D4 | **Dependabot:** aceitar **tudo**, **agrupado por área**, validando cada área. |
| D5 | **Política de correção:** **corrigir tudo na hora**, com o que já existe no app. |
| D6 | **Auditoria = ambíguo? Não:** **relatório agora + guard permanente no CI** (ambos). |
| D7 | **Superfícies:** frontend web, backend, desktop, whatsapp, agent e mobile. |
| D8 | **Release vai até o fim:** preparar **e criar a tag** `v1.1.7` (dispara o `release.yml`, que publica o instalador). |
| D9 | **Critério de pronto:** todas as suítes locais verdes **e** CI verde. |
| D10 | **Falsos positivos:** **allowlist versionada**, cada exceção com motivo documentado. |
| D11 | **Ordem:** auditoria (baseline) → dependabot → re-auditoria → release. |
| D12 | **Dados invisíveis:** toda tabela **surge em alguma tela/relatório OU é declarada interna por design** (com justificativa). |
| D13 | **Guard em Python** (`backend/tests/`), rodando no job `backend` do CI — **e nada vai para a `main` se o guard não estiver correto, funcionando e aprovado**. |
| D14 | **Bump:** os **5 pacotes** de produto (`desktop`, `frontend`, `whatsapp`, `agent`, `mobile`) → **1.1.7**. |
| D15 | **Se um bump quebrar:** **corrigir o código**, adaptando à nova versão; reverter só em último caso. |
| D16 | **PRs originais do dependabot:** **fechar todas as 22** após incorporar. |
| D17 | **Checagem de endpoint é estrita:** toda chamada do app tem de resolver para um endpoint real (backend/whatsapp); externas entram em allowlist explícita. |
| D18 | **Liberdade de reestruturar** rotas/arquivos se a integridade pedir, desde que tudo continue conectado. |
| D19 | **Profundidade:** varredura **estática completa + automatizada** (não executa o app). |
| D20 | **Botões sem handler:** heurística estática como sinalizador **+** revisão manual para confirmar. |
| D21 | **Artefatos:** spec em `docs/`, relatório em `docs/auditoria/`, guard em `backend/tests/`. |
| D22 | **Formato da spec:** fases numeradas com critérios de aceite (este documento). |

---

## 2. Definições operacionais (o que cada categoria significa)

| Categoria | Definição operacional | Como detectar |
|---|---|---|
| **Tela sem endpoint** | Rota renderizada cuja(s) fonte(s) de dados chamam API que não existe (404) ou falha sempre. | Cruzar chamadas de API do front com a tabela de rotas do FastAPI. |
| **Tela sem link** | Rota definida em `App.tsx` que não é alcançável pela `NAV_GROUPS` nem por nenhum link `to=` no app. | Cruzar rotas × `href` da nav × `to=`/`navigate()` do código. |
| **Feature fantasma** | Export/componente que não é renderizado em **nenhum** ponto (nem embutido, nem em teste). | Referência de símbolos a partir de `features/*/index.ts`. |
| **Backend órfão** | Endpoint registrado que nenhum consumidor do projeto chama (front, desktop, mobile, agent, e2e, webhooks internos). | Cruzar rotas do backend × chamadas dos consumidores. |
| **Botão sem handler** | Controle clicável sem ação: `onClick` vazio, `href="#"`, TODO, handler inexistente. | Heurística estática (sinal) + revisão manual (confirmação). |
| **Dado invisível** | Tabela/modelo persistido que não aparece em nenhuma tela, relatório ou exportação. | Cruzar modelos SQLAlchemy × uso na API/UI; o resto entra em "interno por design". |

---

## 3. Dependabot — 22 branches do `origin`, agrupadas por área

Cada área vira **um** PR consolidado (as PRs originais são fechadas ao final — D16). Vários pacotes têm PRs **conflitantes entre si** e precisam ser fundidos manualmente:

| Área | Branches (origem) | Consolidação |
|---|---|---|
| **GitHub Actions** | `actions/checkout-7`, `actions/setup-node-7`, `actions/setup-python-7`, `docker/setup-qemu-action-4` | 1 PR (4 bumps de actions) |
| **Backend / pip** | `pyinstaller-6.22.3`, `python-multipart-gte-0.0.32`, `ruff-gte-0.16.6`, `ruff-gte-0.16.8` | 1 PR — **ruff: pegar a maior (0.16.8)** |
| **Frontend / npm** | `react-b433a1a1ae`, `react-bb70ab9641`, `react-c3539c2691`, `vite-3860fda845`, `vite-4b52c90628`, `eslint-10.10.0`, `lucide-react-1.43.0`, `vitest/coverage-v8-5.0.0` | 1 PR — **3 PRs de `react` colidem → fundir num só**; **2 de `vite`/`vitest` colidem → fundir**. ESLint 9→10 (major) |
| **WhatsApp / npm** | `typescript-7.0.2` (major), `eslint-10.10.0` (major, era 8), `dotenv-17.4.2`, `hapi/boom-10.0.1`, `types/node-26.6.1` | 1 PR |
| **E2E / npm** | `playwright/test-1.63.0` | 1 PR |

**Maiores riscos de ruptura:** React (grupo), Vite (grupo), ESLint 9→10 (frontend) e 8→10 (whatsapp), TypeScript 6→7 (whatsapp), Playwright 1.63.
**Estratégia (D15):** rodar a suíte da área após cada bump; se quebrar, **adaptar o código**; reverter só se for incompatível de fato (registrar no relatório).

**Contexto que favorece a release:** o `release.yml` instala `backend/requirements.txt` no runner Windows — com o `tzdata` já declarado (mudança pendente), o exe passa a ser reprodutível e o `print_queue`/`snapshot` deixam de depender de o pacote existir por acaso na máquina de build.

---

## 4. Auditoria de integridade — matriz superfície × categoria

| Categoria ↓ / Superfície → | Frontend web | Backend | Desktop | WhatsApp | Mobile | Agent |
|---|---|---|---|---|---|---|
| Tela sem endpoint | ● | ○ | ○ | ○ | ○ | — |
| Tela sem link | ● | — | — | — | ● | — |
| Feature fantasma | ● | ● | ● | ● | ● | ● |
| Backend órfão | ● | ● | ● | ● | ● | ● |
| Botão sem handler | ● | — | ○ | ○ | ● | — |
| Dado invisível | ○ | ● | — | — | — | — |

● automatizável no guard · ○ heurística/revisão manual · — não se aplica

---

## 5. Guard de integridade (artefato permanente)

- **Onde:** `backend/tests/` (Python) → roda no job `backend` do CI, junto do pytest (D13).
- **Quando roda:** em `pull_request` **e** `push` para `main`; **falha** o CI em finding não previsto (D13 + D10).
- **Allowlist versionada:** `backend/tests/integrity_allowlist.json` — cada entrada `{ck, target, motivo, responsável?}`; **adicionar algo novo exige justificar** ou o guard quebra.
- **Checagens automatizáveis (bloqueiam):**
  1. **Rota ↔ nav/link:** todo `href` da nav resolve para rota existente; toda rota sob o layout é alcançável via nav **ou** está na allowlist ("alcançável por link a partir de X").
  2. **Chamada de API ↔ endpoint:** toda chamada do front (e de `lib/api`) casa com uma rota real do backend/whatsapp; externas (Vercel, relay, etc.) na allowlist (D17).
  3. **IPC do desktop ↔ handlers:** todo `invoke(...)`/`on(...)` do preload tem `ipcMain.handle/on` correspondente no main, e nenhum handler fica sem ponte no preload.
  4. **Rotas do whatsapp ↔ consumo:** cada rota do serviço Node é consumida por algum dos consumidores (ou allowlist).
  5. **Mobile ↔ `/driver` e `/auth/mobile`:** telas do `RootNavigator` alcançáveis; chamadas de `logic/api.ts` resolvem.
  6. **Modelo/tabela ↔ superfície:** cada tabela surge em API/tela/relatório **ou** entra em "interno por design" com motivo (D12).
  7. **Componentes órfãos:** export de `features/*/index.ts` renderizado em algum lugar **ou** allowlist (embutidos/re-exports).
- **Sinalizadores (não bloqueiam, vão para o relatório):** botões/controles suspeitos (heurística), endpoints só-internos sem doc.

**Arquivos previstos:** `backend/tests/test_app_integrity.py` (ou módulo equivalente), `backend/tests/integrity_allowlist.json`, `docs/auditoria/integridade/RELATORIO_v1.1.7.md` (+ `integrity-report.json` gerado).

---

## 6. Release v1.1.7 — mecânica

| Item | Decisão |
|---|---|
| Versão | **1.1.7** em `desktop`, `frontend`, `whatsapp`, `agent`, `mobile` (D14). `e2e` fica como está (pacote só de teste). |
| CHANGELOG | `[Unreleased]` → `## [1.1.7] - 2026-09-21`; acrescentar as seções de **dependências** e **auditoria de integridade**. |
| Tag | `v1.1.7` — **criada e empurrada nesta execução** (D8), com aprovação explícita registrada. |
| Gate | `release.yml` → `ci-gate` espera o CI do SHA da tag (jobs `backend`, `frontend`, `whatsapp`, `agent`); `build-windows` só roda depois. |
| Publicação | `build-windows` compila o backend (PyInstaller, agora com `tzdata`) e publica o instalador (electron-builder `--publish always`). |
| Pré-condição dura | **Nada vai para a `main` sem o guard correto, funcionando e aprovado** (D13). |

---

## 7. Fases de execução

> Ordem obrigatória (D11): **baseline → guard/auditoria → correções → dependabot por área → re-auditoria → release**.

### F0 — Baseline e commit do `tzdata`
**Entrega:** rodar todas as suítes e registrar o baseline; commitar a mudança pendente do `tzdata`.
- **O que já existe:** mudança do `tzdata` já aplicada em working tree (`requirements.txt` + `gasflow-backend.spec`).
- **O que falta:** instalar `tzdata` no `.venv-ci` e re-rodar o backend para confirmar 0 falhas; commitar.
- **Critério de aceite:** backend 100% verde local (ou todas as falhas remanescentes explica das como ambiente) e `tzdata` commitado.
- **Validação:** `pytest tests/ -q`, `git show --stat` do commit.

### F1 — Guard de integridade (D13)
**Entrega:** `test_app_integrity.py` + `integrity_allowlist.json` + wiring no CI.
- **Critério de aceite:** o guard roda no job `backend`, detecta as 7 checagens, falha em finding não listado e passa com a allowlist base do §4/§10.
- **Validação:** rodar o guard localmente com um finding sintético (deve falhar) e sem ele (deve passar).

### F2 — Relatório de auditoria + correções (baseline)
**Entrega:** `docs/auditoria/integridade/RELATORIO_v1.1.7.md` com todos os findings por superfície/categoria/severidade; **corrigir tudo na hora** (D5), reusando componentes e padrões existentes.
- **Critério de aceite:** zero finding não-previsto (só sobra o que estiver justificado na allowlist); nenhuma tela/rota/botão/dado fica órfão.
- **Validação:** guard verde + suíte das áreas tocadas + inspeção manual dos pontos alterados.

### F3 — Dependabot: GitHub Actions + pip
**Entrega:** 2 PRs/commits consolidados (actions; backend pip).
- **Critério de aceite:** CI verde; `pyinstaller` e `python-multipart` atualizados; ruff na maior versão.
- **Validação:** job `backend` + `migrations` + `trivy` verdes.

### F4 — Dependabot: frontend
**Entrega:** 1 PR consolidado (React fundido, Vite/Vitest fundidos, ESLint 10, lucide-react, coverage-v8).
- **Critério de aceite:** build + lint + 299 testes verdes; **nenhuma tela quebrada** (guard + revisão).
- **Validação:** `npm run build`, `npm run lint`, `npm test`, guard.

### F5 — Dependabot: WhatsApp + E2E (+ agent, se houver)
**Entrega:** 2 PRs consolidados (whatsapp npm; e2e playwright).
- **Critério de aceite:** typecheck + build + 94 testes (whatsapp) e suíte e2e verde no CI.
- **Validação:** job `whatsapp` + `e2e`.

### F6 — Re-auditoria
**Entrega:** rodar o guard sobre o app já atualizado; atualizar relatório/allowlist.
- **Critério de aceite:** guard verde e nenhuma regressão de integridade introduzida pelos bumps.
- **Validação:** todas as 6 suítes + guard.

### F7 — Release v1.1.7
**Entrega:** bump dos 5 pacotes, CHANGELOG `[1.1.7]`, tag `v1.1.7` criada e empurrada; acompanhar o `release.yml` até o fim.
- **Critério de aceite:** CI verde no commit da tag; `ci-gate` libera; instalador publicado (ou falha documentada com causa).
- **Validação:** `git describe`, run do workflow, artefato no GitHub Releases.

---

## 8. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Bumps **major** (ESLint 10, TS 7, Playwright, Vite 8, React) quebrarem telas | Validar por área; **corrigir o código** (D15); reverter só em último caso |
| 3 PRs de `react` e 2 de `vite` colidirem entre si | Consolidação manual num único PR por área (§3) |
| Falso positivo no guard (componentes embutidos, re-exports) | Allowlist versionada com motivo (D10) |
| Guard bloquear a `main` indevidamente | Allowlist + revisão humana antes do push (D13) |
| Suíte local do backend vermelha no Windows | Instalar `tzdata` no `.venv-ci` (F0) |
| Publicação da tag é praticamente irreversível | `ci-gate` obriga CI verde no SHA da tag; revisão antes do push |
| Reestruturar rotas (D18) quebrar links | Guard de rota↔nav roda a cada PR/push |
| E2E não está no gate da tag (só os 4 jobs de teste) | Rodar o E2E no CI antes da tag como parte do critério de pronto (D9) |

---

## 9. Definition of Done (v1.1.7)

1. Guard de integridade correto e **aprovado**, rodando em PR + push, verde.
2. Relatório de auditoria commitado, **sem findings não-previstos**.
3. Todas as 22 branches do dependabot incorporadas (por área) e as **22 PRs fechadas**.
4. Suítes locais verdes (backend c/ `tzdata`, frontend, whatsapp, agent, desktop, mobile).
5. CI verde nos jobs `backend`, `frontend`, `whatsapp`, `agent`, `migrations` e `e2e`.
6. 5 pacotes em **1.1.7**; CHANGELOG com `## [1.1.7] - 2026-09-21`.
7. Tag `v1.1.7` criada e empurrada; `release.yml` concluído (instalador publicado ou falha documentada).

---

## 10. Allowlist base (categorias já conhecidas — D "faça o melhor pro projeto")

Entradas legítimas de "não consumido pela UI":

1. **Infra externa / por design:** `/health`, `/metrics`, webhooks (`alerts`, `whatsapp/cloud`), e tabelas internas (`outbox_entries`, `idempotency_keys`, `auth_audit_log`/`ai_audit_log` quando não têm tela dedicada).
2. **Consumido só pelo Desktop/agent:** endpoints usados via IPC/bridge do Electron.
3. **Consumido só pelo WhatsApp embedded:** rotas do serviço Node usadas pelo desktop embutido.
4. **Consumido só pelo mobile:** `/driver/*`, `/auth/mobile/*`.
5. **Consumido só pelo e2e:** rotas exclusivas das specs Playwright.
6. **Componentes embutidos / re-exports:** `PaymentSettingsPage`, `ConversasPage`, `WhatsAppWebPanelPage` (renderizados embutidos) e re-exports de `index.ts`.

---

## 11. Pendências e resíduos conhecidos

- **Falhas locais do backend sem `tzdata`:** 15 (snapshot diário, fila de impressão) — resolvidas declarando o pacote (F0); CI (Ubuntu) sempre esteve verde.
- **Empacotamento:** o exe deve continuar embutindo o `tzdata` (`hiddenimports` adicionado no spec); validar no build da release.
- **E2E no gate:** hoje o `release.yml` só exige os 4 jobs de teste; o E2E entra como requisito de processo (D9), não como gate automático — decisão a revisitar se o E2E ficar estabilizado.
- **Roadmap maior (P0 RBAC/estoque/JWT)** de `docs/ROADMAP_BLOCKERS.md` **não** faz parte desta spec.

---

## 12. Perguntas em aberto (para a sessão de execução)

1. Formato exato do `integrity_allowlist.json` (chave por `kind`+`target`) — decidir na F1.
2. Caminho final do guard (`test_app_integrity.py` único vs. módulo `tests/integrity/` + teste fino) — decidir na F1.
3. Se o E2E falhar de forma instável antes da tag, publicar mesmo assim ou segurar a release — decidir na F6.
