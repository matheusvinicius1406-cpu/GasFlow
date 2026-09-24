# Central Financeira — Fase 2: decisões e plano de PRs

**Data:** 2026-09-24 · **Pré-requisito:** Fase 1 (`docs/auditoria/central-financeira-fase1.md`, commit `fcf28a7`) · **Estado:** plano aguardando aprovação — nenhum código de solução escrito, conforme a regra da missão.

---

## 1. Decisões

### 1.1 Fechadas (aprovadas por você)

| # | Decisão | Efeito no plano |
|---|---|---|
| D1 | **Protótipo = referência.** O HTML vale como inspiração; a tela final usa stack + design system do projeto | Nenhuma dependência de lib nova; tokens do `index.css` mandam (§2.3). O mapa bloco→endpoint usa os **14 nomes de seção** do brief — se o HTML chegar depois, só reordena blocos, não muda arquitetura |
| D2 | **Funções de escrita entram no PR da Visão Geral** | Criar/cancelar despesa, cancelar pagamento e registrar recebimento migram juntos com a tabela/listas da Visão Geral → nada perde capacidade na Fase 4 (fecha R10) |
| D3 | **Backend aditivo já** (nada de mock) | ~11 endpoints novos + 2 tabelas novas; todos aditivos, defaults preservam comportamento atual (fecha R2/R3) |
| D4 | **Mapa de Calor vira seção da Central Financeira** | `HeatmapPage` é movida para `sections/MapaCalorSection.tsx`; rota antiga `/reports/heatmap` redireciona na Fase 4 (fecha R11) |

### 1.2 Recomendações — precisam do seu veto antes do PR1

| # | Ponto | Recomendação | Se você vetar |
|---|---|---|---|
| V1 | **Presets de período (R9)** | **Hoje(1) / 7 / 30 / 90 / 180**; estender `VALID_DAYS` e `VALID_PERIODS` para `(1, 7, 30, 90, 180)` | Só `7/30/90/180` como o brief pede (perde o "Hoje" que a tela atual tem) |
| V2 | **Guard de permissão (R12)** | `PermissionRoute permissions={['finance.read']}` na rota — ADMIN/MANAGER/OPERATOR/VIEWER entram como hoje; DRIVER/CUSTOMER (sessão de painel) ficam de fora; precedente: `purchase.read`, `whatsapp.read` | Manter aberto como hoje (sem guard), espelhando o backend que também não exige |
| V3 | **Permissão de escrita** | Criar `finance.write` no catálogo RBAC e **não** dar para VIEWER (read-only de verdade); ADMIN/MANAGER/OPERATOR recebem. Gate só no front nesta missão | Sem `finance.write` (escrita aberta como hoje) **ou** grant também para VIEWER (paridade total) |
| V4 | **Modelo de orçamento** | Tabela mensal: `(tenant, ano, mês, categoria, valor)` — comparado ao realizado do período; seção avisa "orçamento = mês corrente" quando o preset ≠ 30 dias | Orçamento por categoria **sem data** (vigente sempre) — mais simples, mas some o "mês" |
| V5 | **Bloco de Entregas (do Relatórios atual)** | Manter: `DeliveryCharts` vira parte da seção **Equipe** (o backend `/reports/deliveries` já existe e atende) | Cortar: apaga `DeliveryCharts.tsx` + teste no Fase 4 (perde os 4 gráficos de entregas) |
| V6 | **Régua automática de cobrança** | **Fora de escopo.** Saem aging + lista de cobrança (dados existem); automação de aviso é feature de produto, não de tela | — (se discordar, vira PR de produto separado, depois desta missão) |
| V7 | **Guard de permissão no backend** (`require_permission("finance.read")` nos GETs de `/finance/*` e `/reports/*`) | Deixar para um PR próprio **depois** de checar `mobile_api_paths` do audit (se o app do entregador chamar esses rotas, o token DRIVER não tem `finance.read` e quebraria) | — |

---

## 2. Arquitetura alvo

### 2.1 Rota e navegação (estado final)

- **URL final: `/finance`** — o nome que o projeto já usa (brief permite: "ou o nome que o projeto já usa"). Mantém qualquer bookmark/link futuro e segue a convenção de rotas em inglês do `App.tsx`.
- **Rota transitória de construção: `/finance/central`** — a tela nova é montada nela durante a Fase 3, para você poder clicar/revisar a cada PR **sem tirar a tela velha do ar**. Sai na Fase 4 junto do item de menu temporário.
- **Menu final:** o grupo `'Financeiro & Relatórios'` (3 itens) vira **item único** `Financeiro → /finance` (padrão `href` direto, como o Dashboard). `BarChart3` e `Flame` saem dos imports se ficarem órfãos (ESLint reprova).
- **Redirects na Fase 4** (a Fase 5 valida "nenhum 404 em rota antiga"):
  - `/reports` → `/finance`
  - `/reports/heatmap` → `/finance?secao=mapa-de-calor`
  - (a rota `/finance/central` é simplesmente removida junto do seu href — bookmark só existe de dev)
- **Deep-link de seção:** `?secao=<slug>` via `useSearchParams`. Motivo: redirects acima e link direto para a seção certa; padrão `visao-geral`.

### 2.2 Estrutura de arquivos

```
frontend/src/features/finance/
├── CentralFinanceiraPage.tsx        # shell: Page/PageHeader + filtros globais + abas + ?secao=
├── index.ts                         # barrel (Fase 4: só a página nova)
├── usePeriodFilter.ts               # estado global: período, busca, seção (searchParams)
├── SectionShell.tsx                 # wrapper por seção: título + loading/error/empty padronizados
├── exportPeriodCsv.ts               # movido de features/reports/periodCsv.ts (D1 mantém a peça)
├── tv/
│   └── TvMode.tsx                   # useTvMode: fullscreen + rotação + tema + ESC
├── sections/
│   ├── VisaoGeralSection.tsx        # 4 KPIs + insights + meta + fluxo + donut + tabela (escritas aqui)
│   ├── DreSection.tsx
│   ├── ProjecaoSection.tsx
│   ├── OrcamentoSection.tsx
│   ├── ProdutosSection.tsx
│   ├── ClientesSection.tsx          # aging + lista de cobrança (V6)
│   ├── EquipeSection.tsx            # inclui DeliveryCharts movido (V5)
│   ├── PagamentosSection.tsx        # por forma
│   ├── CalendarioSection.tsx        # calendário + heatmap dia×hora
│   ├── MapaCalorSection.tsx         # movido de HeatmapPage (D4)
│   ├── TendenciaSection.tsx         # média móvel + regressão — cálculo no cliente
│   ├── ConciliacaoSection.tsx
│   ├── AuditoriaSection.tsx
│   ├── SimuladorSection.tsx         # what-if — cálculo no cliente
│   └── SalvosSection.tsx            # relatórios salvos
└── __tests__/                       # 1 teste por página + 1 por seção (padrão do repo)
```

Regras por seção: componente único por bloco, `({ data }: { data: T })`, **sem** fetch interno (o shell busca e injeta); estados `loading / error / empty` sempre; sem `window.confirm` (usa `Dialog` + `Toast` que já existem).

### 2.3 Design system (o brief diz: design system vence)

- Tokens do `frontend/src/index.css` via `@theme`: `text-success`, `text-warning`, `text-destructive`, `text-info`, `text-muted-foreground`, `border-border`, `--text-kpi` para os KPIs. **Zero cor literal** (fecha R13 — nada de `#16a34a`/`bg-green-100` copiados da tela velha).
- Componentes existentes: `Card`, `StatCard`, `Table`, `Tabs`, `Dialog`, `Badge`, `StatusBadge`, `Select`, `Input`, `Button`, `EmptyState`, `ErrorState`, `LoadingSpinner`, `Toast`, `Skeleton`, `Tooltip` — sem Radix/shadcn novo.
- Gráficos: **Recharts (SVG)** já instalado — sparklines, donut, barras empilhadas, linhas. **Nenhuma lib nova.** Mapa: Leaflet já instalado.
- Shell: herda `DashboardLayout`; só `Page` + `PageHeader`/`PageTitle`/`PageActions` + `Section`. **Nenhum header próprio.**
- Armadilhas do brief adaptadas (R8): canvas/Chart.js **não se aplicam**; valem `animation-fill-mode` (não depender de estilos pós-animação), altura fixa no wrapper do `ResponsiveContainer` e CSS barato (sem `filter: blur`/`box-shadow` animado).

### 2.4 Export / impressão / TV

- **CSV:** move `periodCsv.ts` (BOM, `;`, decimal — peça madura) para `features/finance/exportPeriodCsv.ts`.
- **PDF/Imprimir:** reaproveita `lib/exportPdf.ts` → `exportCurrentViewPdf()` (ponte Electron `printToPDF`, fallback `window.print()`) — mesmo comportamento da ReportsPage de hoje.
- **`@media print` (novo, fecha R4):** bloco no `index.css` — esconde `Sidebar`, `Header`, `MobileSidebar`, `FloatingCopilot`, `PageActions` (marcados `data-no-print` no PR de impressão), fundo branco, `print-color-adjust: exact` para os gráficos, cabeçalho `print-only` com `branding.companyName` + período + gerado em, rodapé `print-only` com as 3 linhas de assinatura. Como `Tabs` desmonta a aba oculta, **imprimir a seção atual é automático**.
- **Modo TV (novo, fecha R5):** `useTvMode` — `requestFullscreen()` no container da página, rotação de seção a cada 15 s, força tema escuro via `useTheme().setThemeMode('dark')` (restaura ao sair), `ESC` sai, sem animação cara se `prefers-reduced-motion`. Botão em `PageActions`.

---

## 3. Contrato de dados final (D3)

Legenda: **E** = endpoint existente · **N** = novo endpoint aditivo (backend desta missão) · **C** = cálculo no cliente sobre dado existente · **T** = tabela nova.

| Seção | Origem do dado | Nota de honestidade |
|---|---|---|
| Visão Geral — 4 KPIs | **E** `/finance/reports/period`, `/finance/cash/balance` | comparação vs período anterior já vem em `comparison.*_pct` |
| Visão Geral — meta | **N** `/finance/budget` (**T** `finance_budgets`) | V4: modelo mensal |
| Visão Geral — insights | **E** `/dashboard` + **N** `/finance/receivables/summary` | "a receber/atrasado" deixa de ser conta sobre página de 100 |
| Visão Geral — fluxo diário | **E** `period.daily` | — |
| Visão Geral — donut por categoria | **N** `/finance/reports/categories` | fecha a agregação sobre endpoint paginado (R3) |
| Visão Geral — tabela (4 abas, busca, sort, total) | **E** `/finance/payments\|expenses\|receivables\|cash` **+ params novos** `q, date_from, date_to, order_by, order` | defaults = comportamento atual; busca/total passam a ser do servidor |
| Visão Geral — **escritas** | **E** `POST /finance/expenses`, `…/cancel`, `POST /payments/{id}/cancel`, `POST /finance/orders/{codigo}/payments` (registrar recebimento) | gates front: `finance.write` (V3) e `finance.receive`; backend hoje: só `get_tenant_context` em cancelar pagamento (**correção da Fase 1**: `require_admin` cobre só `methods`/`pix`, não `/{id}/cancel` — `payments.py:370`) |
| DRE Gerencial | **N** `/finance/reports/dre` | CMV = `purchase_note_items` (notas `CONFIRMED`) ponderado; retorno leva `cmv_coverage` ( % de receita com custo conhecido ) |
| Projeção de caixa | **N** `/finance/reports/projection?horizon=30` | modelo declarado: saldo + recebíveis com `due_date` + média histórica de despesas — **sem ML**, rótulo honesto na UI |
| Orçamento vs Realizado | **T** `finance_budgets` + **N** `/finance/budget` (GET/PUT) | realizado = `/finance/reports/categories` |
| Produtos (margem) | **N** `/finance/reports/products` | receita = `order_items` (`OrderItemModel` existe) ligado a pagamento; custo = notas de compra; produto sem nota → `cost_known: false` |
| Clientes + aging + cobrança | **N** `/finance/receivables/summary` (buckets 0-30/31-60/61-90/90+) | régua automática **fora de escopo** (V6) |
| Equipe | **N** `/finance/reports/team` = entregas por motorista (`/reports/deliveries`-style) + despesas `SALARY` | sem "custo exato por entregador" — rótulo honesto |
| Pagamentos por forma | **N** `/finance/reports/methods` | fecha R3 para esta seção |
| Calendário + heatmap dia×hora | **E** `period.daily` (calendário) + **N** `/finance/reports/hourly` | hourly usa `payments.paid_at`; despesas **não têm hora** → só entram o fluxo diário |
| Tendência | **C** sobre `period.daily` | média móvel 7d + regressão linear + projeção 15d — puro cliente |
| Conciliação | **N** `/finance/reports/conciliation` | cruza pagamento ↔ movimento de caixa ↔ recebível; **sem campo novo na tabela** — divergências são "a revisar", nunca "erro" |
| Auditoria | **N** escrita em `auth_audit_log` nas mutações financeiras (precedente: `purchase_service.py:55`, `admin.py:_log_audit`) + **N** `GET /finance/audit?days=` | **sem backfill**: só eventos a partir do deploy; leitura exige `audit.view` (seção oculta sem permissão) |
| Simulador what-if | **C** sobre `period.daily` + `receivables` | puro cliente |
| Relatórios salvos | **T** `finance_saved_reports` + **N** `GET/POST/DELETE /finance/saved-reports` | — |
| Mapa de Calor (D4) | **E** `/reports/heatmap` | Leaflet movido sem mudança de API |
| Entregas (V5) | **E** `/reports/deliveries` | `DeliveryCharts` movido para a seção Equipe |

### 3.1 Lista fechada do backend aditivo

**Endpoints GET novos (sem tabela):** `/finance/reports/categories`, `/finance/reports/methods`, `/finance/reports/dre`, `/finance/reports/products`, `/finance/reports/projection`, `/finance/reports/team`, `/finance/reports/hourly`, `/finance/reports/conciliation`, `/finance/receivables/summary`, `/finance/audit`.

**Params aditivos** (opcionais, defaults preservam hoje) em `/finance/payments`, `/finance/expenses`, `/finance/receivables`, `/finance/cash`: `q`, `date_from`, `date_to`, `order_by`, `order`.

**Endpoints novos com tabela:** `GET|PUT /finance/budget` (migration `finance_budgets`), `GET|POST|DELETE /finance/saved-reports` (migration `finance_saved_reports`). Ambas precisam de repository + router no mesmo commit (aí passam em `dado-invisivel`).

**Validadores:** `VALID_DAYS`/`VALID_PERIODS` → `(1, 7, 30, 90, 180)` (V1). **Quebra testada e conhecida:** `backend/tests/test_delivery_report.py:145` assere `VALID_DAYS == (7, 30, 90)` — atualizar no mesmo PR.

**RBAC:** novo código `finance.write` no `PERMISSIONS` + grants (V3). Front: `hasPermission('finance.receive')` no botão registrar recebimento (código **já existe** no catálogo).

---

## 4. Plano de PRs

Cada PR é um commit, CI verde no merge, fase nunca misturada. Restrições do guard de integridade que dão a regra de ordem (evidência: `backend/tests/integrity_audit.py:349-424`):

1. `rota-nao-existe` (l.358): href de menu entra **só junto com a rota** no mesmo commit.
2. `tela-sem-endpoint` (l.371): chamada `apiClient` só entra **depois** do endpoint estar no OpenAPI → **backend PR primeiro**.
3. `componente-orfao` (l.418): export de barrel precisa de uso fora de teste/index — apagar arquivo **e** barrel **e** import do `App.tsx` juntos.
4. `dado-invisivel` (l.412): tabela nova entra com repository+router no mesmo commit.
5. `tela-sem-link` (l.361) hoje é **latente** (pula toda rota porque `linked` contém `/` vindo do `<Navigate to="/">` do AuthProvider) — **não construímos em cima desse achado**: href/rota/link seguem coerentes de verdade.
6. **Allowlist não cresce** (hoje 20 entradas, 0 pendentes).

| PR | Fase | Escopo | Aceite |
|---|---|---|---|
| **P1** | 3 (backend) | `categories`, `methods`, `receivables/summary` + params de lista + `VALID_DAYS/PERIODS` + teste `test_delivery_report:145` atualizado | pytest verde; nenhuma mudança no front; `python -m tests.integrity_audit` → 19 findings / 0 pendentes |
| **P2** | 3 (backend) | `dre` (CMV de purchase notes + `cmv_coverage`), `products` (`cost_known`), `projection`, `team`, `hourly`, `conciliation` | idem; casos de "sem custo conhecido" testados |
| **P3** | 3 (backend) | tabelas `finance_budgets` + `finance_saved_reports` (migrations + repos + endpoints); escrita de `auth_audit_log` nas mutações financeiras + `GET /finance/audit`; código `finance.write` no RBAC (V3) | migrations idempotentes; audit grava antes/depois como o purchase; `dado-invisivel` verde |
| **P4** | 3 (front) | rota `finance/central` + `CentralFinanceiraPage` shell (Page/PageHeader, filtros globais com presets V1, abas, estados) + **item temporário de menu** + barrel + teste + guard `finance.read` (V2) | `rota-nao-existe` verde (href↔rota juntos); telas antigas intactas |
| **P5** | 3 (front) | **Visão Geral** + **todas as escritas** (D2): KPIs com tokens, insights, meta, fluxo, donut, tabela 4 abas com sort/busca/total do servidor, `Dialog` no lugar de `window.confirm`, CSV movido | teste de cada escrita; `tela-sem-endpoint` verde; R10 fechado (as funções já vivem na tela nova) |
| **P6** | 3 (front) | analíticas I: **DRE, Produtos, Orçamento (V4), Projeção** | 1 teste/seção (loading/error/empty/dado) |
| **P7** | 3 (front) | analíticas II: **Clientes/aging, Pagamentos por forma, Calendário+hourly, Tendência, Simulador** | idem |
| **P8** | 3 (front) | analíticas III: **Conciliação, Auditoria (gate `audit.view`), Relatórios salvos** + **Equipe** (com `DeliveryCharts` movido, V5) + **Mapa de Calor** como seção (D4) | `componente-orfao` verde (DeliveryCharts e periodCsv com uso novo **antes** de apagar o antigo) |
| **P9** | 3 (front) | **Impressão + PDF/CSV**: `@media print`, `data-no-print` no shell, cabeçalho+assinatura `print-only`, botão usando `exportCurrentViewPdf()` | impressão da seção atual sai limpa (testes de fallback `window.print` como ReportsPage:121-139) |
| **P10** | 3 (front) | **Modo TV**: `useTvMode` (fullscreen, rotação 15 s, dark forçado, ESC, reduced-motion) | botão em `PageActions`; jsdom não quebra (fullscreen com feature-detect) |
| **P11** | **4** | **Remoção atômica** — checklist §5 | lint + `tsc -b` + `npm test` + pytest + integrity **19/0** + redirects sem 404 |
| **P12** | **5** | E2E `central-financeira.spec.ts` + relatório `docs/auditoria/central-financeira-fase5.md` | checklist §6 todos marcados |

Docs: Fase 2 = este arquivo (1 commit); Fase 5 = relatório (1 commit). Nada de push sem pedido.

---

## 5. Fase 4 — remoção atômica (P11, tudo num commit)

- [ ] `App.tsx`: `path="finance"` → `element={<CentralFinanceiraPage />}`; apagar rota `finance/central`; acrescentar `<Navigate to="/finance" replace />` em `reports` e `<Navigate to="/finance?secao=mapa-de-calor" replace />` em `reports/heatmap`; apagar imports de `FinancePage`, `ReportsPage`, `HeatmapPage`.
- [ ] `nav.tsx`: grupo `'Financeiro & Relatórios'` → item único `{ label: 'Financeiro', href: '/finance', icon: DollarSign }`; limpar `BarChart3`/`Flame` se ficarem órfãos.
- [ ] Apagar `FinancePage.tsx` + `__tests__/FinancePage.test.tsx`; apagar `ReportsPage.tsx`, `HeatmapPage.tsx` + os 4 testes deles; apagar `features/reports/` inteiro (`DeliveryCharts` e `periodCsv` **já movidos** em P8/P5).
- [ ] Barrles: `features/finance/index.ts` só com o que sobrevive; `features/reports/index.ts` deixa de existir.
- [ ] `MobileSidebar.test.tsx:39`: assert do label novo (hoje assere `'Financeiro & Relatórios'`).
- [ ] Rodar: `npm run lint`, `npm test`, `npx tsc -b`, `pytest`, `python -m tests.integrity_audit` (espera **19 findings / 0 pendentes**, allowlist intacta).

## 6. Fase 5 — validação (P12)

- [ ] E2E novo: login → menu tem **uma** entrada → `/finance` abre → presets (inclusive 180) → abas/seções → criar despesa → redirects `/reports` e `/reports/heatmap` não dão 404 → botão Imprimir chama o fallback → modo TV entra/sai.
- [ ] Manual por seção (15): loading, error, empty, dado real, gate de permissão (com VIEWER e sem `audit.view`).
- [ ] Impressão de cada seção principal (PDF do Electron e `window.print` do browser).
- [ ] Screenshots + evidências no `docs/auditoria/central-financeira-fase5.md`.

---

## 7. Riscos residuais (aceitos ou mitigados)

| Risco | Mitigação |
|---|---|
| HTML do protótipo ainda não chegou (R1) | Arquitetura não depende dele (D1); se chegar, muda ordem/rotulagem de blocos dentro das seções já previstas |
| CMV/margem vazia sem notas de compra | `cmv_coverage` + `cost_known` na API; empty state explicando o que preencher |
| Auditoria sem histórico (sem backfill) | Seção mostra "eventos a partir de dd/mm/aaaa" |
| Conciliação acusando divergência legada | Semântica "a revisar", nunca "erro" |
| `/reports/*` sem cache com 180 dias | Espelhar o cache de 5 min do heatmap nos endpoints novos pesados |
| `tela-sem-link` latente no guard | Não dependemos dele — regra 5 do §4 |
| VIEWER perde escrita com V3 | Flag aberto no veto; paridade total é opção |

## 8. Fora de escopo

Régua automática de cobrança (V6) · UI de estorno (endpoint existe, sem tela — não é consolidação) · guard de permissão nos GETs do backend (V7, PR próprio pós-P3) · app Android / item 3 (adiado para o Android Studio) · lib nova de gráficos/UI.

---

**Aguardando:** seus vetos em **V1–V5** (V6 é default; V7 ganhou verificação do `mobile/src` e pode ser aprovado junto) para abrir o **P1**.

> **Correção sobre a Fase 1:** o relatório da Fase 1 afirma que as mutações de
> `/payments/*` exigem `require_admin`. Verificado em `payments.py`: isso vale
> só para `methods` e `pix`; `POST /payments/{id}/cancel` e `…/refund` usam
> `get_tenant_context` (qualquer usuário autenticado do tenant). O texto da §3
> já reflete o código real.
