# Central Financeira — Fase 1: auditoria do projeto

**Data:** 2026-09-24 · **Escopo:** unificar "Financeiro" + "Relatórios" numa tela
única e remover as duas antigas · **Estado:** relatório da Fase 1 (sem código de
solução, conforme a regra de ouro da missão).

> **Aviso de escopo:** o protótipo HTML navegável citado na missão **não está no
> repositório** e não foi anexado a esta sessão. Este relatório mapeia os blocos
> pelos **nomes das seções** citados no brief (14 seções). Para conferir
> estrutura de informação e comportamento bloco a bloco, o HTML é necessário
> (ver R1).

---

## 1. Stack e estrutura

| Item | Realidade do repositório |
|---|---|
| Framework | **SPA React 19.3 + Vite 8.3** (`frontend/`) — não é Next/SSR |
| Tipos | **TypeScript 6.0.3**; build = `tsc -b && vite build` (sem `typecheck` isolado) |
| Estilização | **Tailwind CSS 4.3** via `@tailwindcss/vite`. **Não existe `tailwind.config.js`**: os tokens são CSS variables + bloco `@theme` em `frontend/src/index.css` |
| Componentes | Próprios, em `frontend/src/components/ui/` (25 arquivos: `Card`, `Button`, `Table`, `Badge`, `Input`, `Tabs`, `Dialog`, `StatCard`, `EmptyState`, `ErrorState`, `LoadingSpinner`, `Toast`, `Select`, `Alert`, `Skeleton`, `Switch`, `Tooltip`, `StatusBadge`…). Sem Radix e sem shadcn instalados — só `class-variance-authority`, `clsx`, `tailwind-merge` |
| Gráficos | **Recharts 3.10.1 (SVG)** — usado só em `features/reports/*` (`ReportsPage`, `DeliveryCharts`). Mapa: **Leaflet 1.9.4** + tiles OSM |
| State/query | **TanStack Query 5** (`@tanstack/react-query`) + **axios** (`src/lib/api/client.ts`, base `/api`, refresh *single-flight*). Sem Redux/Zustand no painel |
| Router | **react-router-dom 7**, rotas declarativas em `frontend/src/App.tsx`, aninhadas sob `/` dentro de `ProtectedRoute` + `DashboardLayout` |
| Testes | **Vitest 5** + Testing Library + jsdom (`npm test`), ESLint 10 (`npm run lint`), E2E **Playwright** em `e2e/` (11 specs) |
| Guard de integridade | `backend/tests/test_app_integrity.py` + `tests/integrity_audit.py` cruzam tela ↔ endpoint ↔ rota ↔ componente. **Roda no CI** e reprova finding fora da allowlist (`integrity_allowlist.json`, 20 entradas, **0 pendentes**) |
| Padrão de fetch | **Misto**: `FinancePage`/`ReportsPage`/`HeatmapPage`/`DeliveryCharts` chamam `apiClient` direto; existem hooks React Query equivalentes em `src/lib/api/hooks.ts` (`useFinancePayments`, `useReceivables`, `useFinanceExpenses`, `useCashMovements`, `useCashBalance`, `useCreateExpense`, `useRegisterPayment`) — a `FinancePage` usa hooks só para *recebíveis* e *saldo* |

---

## 2. Estado atual das telas a substituir

### 2.1 Arquivos

| Caminho | Linhas | Papel |
|---|---|---|
| `frontend/src/features/finance/FinancePage.tsx` | 561 | tela "Financeiro" |
| `frontend/src/features/finance/__tests__/FinancePage.test.tsx` | 58 | 3 testes (loading, cards, erro) |
| `frontend/src/features/finance/index.ts` | 1 | barrel |
| `frontend/src/features/reports/ReportsPage.tsx` | 412 | tela "Relatórios" |
| `frontend/src/features/reports/DeliveryCharts.tsx` | 202 | 4 gráficos de entregas (Recharts) |
| `frontend/src/features/reports/HeatmapPage.tsx` | 119 | "Mapa de Calor" (Leaflet, entregas por bairro) |
| `frontend/src/features/reports/periodCsv.ts` | 84 | CSV do período (BOM, `;`, vírgula decimal) |
| `frontend/src/features/reports/*.test.tsx` / `periodCsv.test.ts` | 179 + 129 + 86 + 47 | 7 + 7 + 4 + 3 testes |

### 2.2 Rotas registradas (`frontend/src/App.tsx`)

```tsx
<Route path="finance"        element={<FinancePage />} />   // sem guard de permissão
<Route path="reports"        element={<ReportsPage />} />   // sem guard
<Route path="reports/heatmap" element={<HeatmapPage />} />  // sem guard
```

### 2.3 Componentes reaproveitáveis (usados pelas duas telas e por outras)

`Card` (51 arquivos usam), `Button` (55), `Table` (9), `Badge` (40), `Input` (32),
`EmptyState` (26), `ErrorState` (33), `LoadingSpinner` (49), `Toast` (10),
`Page`/`PageHeader`/`PageTitle`/`PageActions` (`components/layout/Page.tsx`).
**Nenhum** componente de `components/ui` é usado exclusivamente por essas telas —
a remoção não deixa órfão em `ui/`.

### 2.4 Candidatos a remoção (uso exclusivo dessas telas)

| Arquivo | Uso | Destino sugerido |
|---|---|---|
| `features/reports/DeliveryCharts.tsx` | **só** `ReportsPage.tsx` (import + `<DeliveryCharts />` na linha 409) | manter se o bloco de entregas sobreviver na tela nova; senão sai |
| `features/reports/periodCsv.ts` | **só** `ReportsPage.tsx` | o CSV da nova tela provavelmente reusa (é a peça madura: BOM/`;`/decimal) |
| `features/reports/index.ts`, `features/finance/index.ts` | barrels | ajustar ao novo layout de pastas |

### 2.5 Detalhes que a missão precisa saber

- A `FinancePage` **não** usa `Tabs` nem `Dialog` nem `StatCard`: as abas são
  `Button` em fila; confirmações são `window.confirm`; os 4 KPIs são `Card`
  escritos à mão.
- A `FinancePage` é a **única tela** onde se cria despesa, cancela pagamento,
  cancela despesa e navega para registrar recebimento (`/orders/{codigo}`) —
  ver **R10**.
- Cores hardcoded fora do design system: `bg-green-100 text-green-800`,
  `#16a34a`, `#dc2626`, `#2563eb`, `#64748b`, `#eab308` (contrasta com os tokens
  `--success/--destructive/--info/--warning` que já existem).

---

## 3. Shell de layout

`frontend/src/components/layout/DashboardLayout.tsx` monta: `Sidebar` (desktop),
`MobileSidebar` (drawer), `Header`, `<main id="main-content" className="flex-1
overflow-y-auto p-6">` com `<Outlet />`, `RealtimeBridge` e `FloatingCopilot`.
Existe *skip link* e sessão de entregador é isolada (`isDriverOnlySession`).

**Conclusão:** existe shell global → a nova tela **não** traz header próprio além
do padrão `Page` + `PageHeader`/`PageTitle`/`PageActions` (as duas telas atuais já
seguem isso). O que o protótipo pede e **não** existe: `@media print` e modo TV.

---

## 4. Design tokens reais (`frontend/src/index.css`)

- **Tema:** escuro é o padrão (`:root, .dark`); existe `.light`. Nenhuma tela usa
  `next-themes`; a classe é aplicada manualmente.
- **Marca:** `--brand-primary: #f97316` (laranja), `--brand-secondary: #7c3aed`
  (violeta) — **o protótipo usa roxo/indigo literal**, que a missão manda descartar.
- **Semânticos:** `--primary #f97316`, `--success #22c55e`, `--warning #eab308`,
  `--info #3b82f6`, `--destructive/#danger #ef4444`, `--muted-foreground #a1a1aa`,
  `--border #27272a`, `--ring #f97316`.
- **Tipografia:** `--font-sans` (Inter), `--font-mono` (JetBrains Mono);
  escala `--text-display 2.25rem` … `--text-kpi 2rem` (token de KPI já existe).
- **Espaço:** `--space-1…--space-16`. **Raios:** `--radius-xs…--radius-full`.
  **Sombras:** `--shadow-xs…--shadow-xl`. **Motion:** `--duration-*`, `--easing-*`,
  keyframes `gf-*` + utilitários `gf-anim-*` (já neutralizados por
  `prefers-reduced-motion`).
- **Z-index:** `--z-base…--z-tooltip`. **Chrome:** `--sidebar-width 256px`,
  `--header-height 64px`.
- **Mapeamento Tailwind:** bloco `@theme` expõe `bg-background`, `text-foreground`,
  `text-success`, `border-border`, `ring-ring`, etc. — é por aí que a tela nova
  deve falar (nada de paleta literal).

---

## 5. Contrato de dados

### 5.1 O que as telas consomem hoje

| Tela | Chamada | Shape |
|---|---|---|
| FinancePage | `GET /finance/payments` | `{items: Payment[], …}` (`id, order_codigo, amount, method, status, paid_at, reference, idempotency_key, notes, created_at`) |
| FinancePage | `GET /finance/expenses` | `{items: Expense[]}` (`id, description, amount, category, date, payment_method, notes, status, created_at`) |
| FinancePage | `GET /finance/cash` | `{items: CashMovement[]}` (`type, amount, description, balance_after, created_at`) |
| FinancePage | `GET /finance/cash/balance` | `{balance}` |
| FinancePage | `GET /finance/receivables` | `{items: Receivable[]}` (`original_amount, paid_amount, remaining_amount, due_date, status, settled_at`) |
| FinancePage | `POST /finance/expenses`, `POST /finance/expenses/{id}/cancel`, `POST /payments/{id}/cancel` | mutações |
| ReportsPage | `GET /finance/reports/period?days=` | `{from, to, days, total_receipts, total_expenses, net_result, daily[], previous, comparison{receipts_pct, expenses_pct, net_pct}}` |
| ReportsPage | `GET /finance/cash/balance` | idem |
| DeliveryCharts | `GET /reports/deliveries?days=` | série por dia + por motorista + tempo médio + por bairro |
| HeatmapPage | `GET /reports/heatmap?days=` | entregas por bairro (centroide + contagem) |

Outros endpoints financeiros disponíveis e **não** usados por nenhuma tela:
`GET /payments/summary`, `GET|POST|PATCH|DELETE /payments/methods` (mutação =
`require_admin`), `/payments/pix*`, `GET /finance/reports/daily?date=`,
`GET /reports/daily`, `GET /reports/daily.pdf`, `GET /reports/summary`.

**Nota de armadilha:** existem **dois** "daily" diferentes —
`/finance/reports/daily` (financeiro do dia) e `/reports/daily` + `/reports/daily.pdf`
(negócio/entregas do dia). Não confundir no mapa.

### 5.2 Bloco do protótipo → endpoint → campos → o que falta

| Seção do protótipo | Endpoint existente | Campos que existem | O que falta |
|---|---|---|---|
| **1. Visão Geral** — 4 KPIs | `/finance/reports/period`, `/finance/cash/balance` | saldo, recebimentos, despesas, resultado + variação vs período anterior (`comparison.*_pct`) | **meta** (não existe alvo/orçamento) |
| Visão Geral — insights (ticket médio, vendas, a receber, em atraso) | `/dashboard` (`summary.avg_ticket`), `/finance/receivables` | ticket médio, contagem de pedidos, `remaining_amount` + `due_date`/`status OVERDUE` | agregação de "a receber/atrasado" é client-side sobre paginação |
| Visão Geral — fluxo (barras) | `/finance/reports/period` → `daily[]` | `receipts`, `expenses`, `net_result` por dia | — |
| Visão Geral — donut por categoria | `/finance/expenses` (paginado, `page_size ≤ 100`) | `category` (7 valores fixos no front) | **agregação por categoria**: hoje só client-side sobre página → número enganoso |
| Visão Geral — tabela com abas/busca/filtro/ordenação/rodapé | `/finance/payments`, `/finance/expenses`, `/finance/receivables`, `/finance/cash` | todos os campos das abas | busca/ordenação/total só existem no cliente |
| **2. DRE Gerencial** | `/finance/reports/period` | receita e despesa do período | **CMV/custo** (não existe custo de produto) e agregação por categoria |
| **3. Projeção de caixa** | — | série diária serve de insumo | **endpoint/regra de projeção** (nada existe) |
| **4. Orçamento vs Realizado** | — | — | **orçamento/meta** (tabela inexistente) |
| **5. Produtos (margem)** | — (`/products` tem só `preco`) | preço de venda | **custo por produto** |
| **6. Clientes + aging + cobrança** | `/finance/receivables` | `due_date`, `remaining_amount`, `settled_at`, status | *aging* é derivável; **cobrança/régua de aviso** não existe |
| **7. Equipe (operacional-financeiro)** | `/reports/deliveries` (por motorista) | entregas/dia por motorista | **vínculo financeiro por pessoa** (nada além de despesa `SALARY`) |
| **8. Pagamentos por forma** | `/finance/payments`, `/payments/methods`, `/payments/summary` | `method`, cadastro de métodos | agregação por forma (client-side hoje) |
| **9. Calendário + heatmap** | `/finance/reports/daily`, `period.daily` | valores por dia | heatmap **financeiro**; o `/reports/heatmap` existente é de **entregas por bairro** |
| **10. Tendência (média móvel/regressão)** | `period.daily` | série diária | nada no backend — é cálculo puro no cliente |
| **11. Conciliação** | — | — | **status de conciliação** (nenhum campo) |
| **12. Auditoria** | `/admin/audit` (permissão `audit.view`) | `auth_audit_log` — mas **sem ações financeiras** registradas (só `driver.*`, auth…) | **auditoria financeira** (eventos `payment.confirmed`/`pending` existem só no barramento) |
| **13. Simulador What-If** | `period.daily` + `receivables` | insumos bastam | — (cálculo no cliente) |
| **14. Relatórios salvos** | — | — | **persistência de relatório salvo** (tabela inexistente) |

Resumo: **7 das 14 seções** dependem de campo/tabela que não existe
(3, 4, 5, 7 parcial, 11, 12, 14) e **3** dependem de agregação no servidor para
não mentir (donut por categoria, DRE, pagamentos por forma).

---

## 6. Menu / navegação

`frontend/src/components/layout/nav.tsx` (fonte única de `Sidebar` e `MobileSidebar`):

```tsx
{
  label: 'Financeiro & Relatórios',            // linha 97 (grupo colapsável)
  icon: DollarSign,
  items: [
    { label: 'Financeiro',     href: '/finance',          icon: DollarSign },  // 100
    { label: 'Relatórios',     href: '/reports',          icon: BarChart3 },   // 101
    { label: 'Mapa de Calor',  href: '/reports/heatmap',  icon: Flame },       // 102
  ],
}
```

- Remover as duas entradas e acrescentar uma é uma edição de 3 linhas — desde que
  se decida o destino de **Mapa de Calor**, que mora no mesmo grupo e **não** está
  no escopo da missão (**R11**).
- `frontend/src/components/layout/MobileSidebar.test.tsx:39` assere o texto
  `'Financeiro & Relatórios'` → **quebra** se o grupo for renomeado.

---

## 7. Riscos e bloqueios

| # | Risco / bloqueio | Evidência |
|---|---|---|
| **R1** | **Protótipo ausente.** Não há HTML navegável no repositório nem anexo nesta sessão; o mapa da §5.2 usa só os nomes das 14 seções. Sem o arquivo não dá para conferir bloco, ordem e comportamento | `glob docs/**` não tem protótipo |
| **R2** | **7 seções pedem dado que não existe** (orçamento, projeção, custo/margem, conciliação, cobrança, relatórios salvos, equipe financeira) → "requer backend" ou mock com flag | §5.2 |
| **R3** | **Agregação client-side sobre endpoint paginado** (`page_size ≤ 100` em `/finance/payments` e `/finance/expenses`) → donut/DRE por categoria com dado real exige endpoint de agregação aditivo | `finance/finance.py` (`page_size: le=100`) |
| **R4** | **`@media print` NÃO existe** em `frontend/src` nem em `index.html` — a missão assume que já existe. Impressão por seção é implementação nova | `grep "@media print"` → vazio |
| **R5** | **Modo TV não existe**: nenhum uso de `requestFullscreen`, nenhuma rota/estado de TV, nenhum tema escuro alternável por tela | `grep -i fullscreen\|modo tv` → vazio |
| **R6** | **Guard de integridade**: checks `tela-sem-link`, `rota-nao-existe`, `componente-orfao`, `dado-invisivel` rodam no CI contra allowlist de 20 entradas com **0 pendentes**. Remover rota mantendo link → reprova; deixar `DeliveryCharts` órfão → reprova | `backend/tests/integrity_audit.py` + `integrity_allowlist.json` |
| **R7** | **Sem E2E para finance/reports**: nenhum spec toca essas rotas → a validação da Fase 5 é 100% manual ou exige spec novo | `grep finance\|reports e2e/tests/` → vazio |
| **R8** | **Armadilhas do brief são de canvas/Chart.js e o projeto usa Recharts (SVG)**: itens 1–3 (save/restore, hex→rgba, stagger via `options.animations`) **não se aplicam**; valem o 4 (`animation-fill-mode`), o 7 (CSS caro) e, adaptado, o 5 (altura fixa no wrapper do gráfico) | `ReportsPage.tsx`/`DeliveryCharts.tsx` usam `ResponsiveContainer` + `height={300}` |
| **R9** | **Presets divergentes**: a UI oferece 1/7/30/90; o brief pede 7/30/90/**180**. O backend aceita (`days: ge=1, le=365` no período; `/reports/*` sem limite) | `finance/finance.py:305`, `finance/reports.py:64,89` |
| **R10** | **Perda de capacidade se as telas caírem sem levar as funções**: criar despesa, cancelar despesa, cancelar pagamento e "Registrar Pagamento" só existem na `FinancePage` | `FinancePage.tsx` (handlers + `POST /finance/expenses*`, `/payments/{id}/cancel`) |
| **R11** | **Mapa de Calor** está no grupo que será mexido e não está no escopo (é entregas por bairro). Opções: item próprio, seção da tela nova, ou grupo órfão — decisão sua | `nav.tsx:102` |
| **R12** | **Permissão**: `finance.read` existe no seed (ADMIN tem `finance.*`; MANAGER tem `finance.*`; OPERATOR e VIEWER têm `finance.read`), mas **as rotas `/finance/*` e `/reports/*` não exigem permissão** (só `methods`/`pix` em `/payments/*` usam `require_admin` — cancel/refund de pagamento **não** exigem; verificado em Fase 2, `payments.py:370,380`). Colocar `PermissionRoute` na tela nova **muda o acesso** de quem hoje entra sem a permissão | `rbac_seed.py:42-46,121,151,180`; `finance/*.py` usam `get_tenant_context` |
| **R13** | **Cores fora do design system** na tela atual (hardcoded) — reaproveitar o markup literal significaria copiar a dívida; a missão manda o design system vencer | §2.5 |
| **R14** | `Dialog`, `Select`, `Tabs` e `StatCard` existem e são pouco usados (1, 4, 3 e 6 arquivos) — a tela nova pode se apoiar neles sem criar componente novo | contagem de imports |

### Decisões que a Fase 2 precisa de você

1. **Protótipo**: anexar o HTML (R1) — sem ele, a Fase 2 mapeia seções só por nome.
2. **Escopo das funções**: as capacidades de escrita (R10) entram na tela nova na
   Fase 3.2 ou ficam para um PR próprio? Nada pode sair do ar na Fase 4.
3. **Mapa de Calor** (R11): item próprio, seção da Central, ou fica como está.
4. **Agregações** (R3) + campos ausentes (R2): o que vira **endpoint aditivo** de
   backend e o que fica **mock com flag** até existir?
5. **Guard de permissão** (R12): `finance.read` na rota nova ou manter aberto como hoje?
6. **Presets** (R9): padronizar 7/30/90/180 (e manter "Hoje"?).

---

## O que a Fase 1 entregou

- Stack, tokens e shell mapeados com caminho de arquivo.
- As duas telas inventariadas: arquivos, rotas, testes, componentes
  reaproveitáveis e o que é exclusivo (só `DeliveryCharts` e `periodCsv`).
- Contrato de dados montado bloco a bloco, com o que existe e o que falta
  (7 seções dependem de backend, 3 de agregação no servidor).
- Navegação e os 14 riscos/bloqueios, com evidência.

**Nada de código foi escrito.** A Fase 2 (decisões + plano de PRs) espera as
respostas acima.

> **Correção posterior (Fase 2, commit `…`):** R12 dizia que toda mutação de
> `/payments/*` exige `require_admin` — falso: só `methods` e `pix` exigem;
> `POST /payments/{id}/cancel|refund` usam `get_tenant_context`
> (`payments.py:370,380`). O texto de R12 foi corrigido no lugar.
