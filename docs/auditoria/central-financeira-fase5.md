# Central Financeira — Fase 5: validação (P12)

**Data:** 2026-09-25 · **Escopo:** fechar a missão da Central Financeira com o E2E
de ponta a ponta (checklist §6 de `central-financeira-fase2.md`) · **Estado:**
spec E2E entregue e validada (carrega + tipa); a **execução** contra o stack
`docker-compose.e2e.yml` é o único passo que ainda depende de ambiente.

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
| **P12** | este commit | E2E `central-financeira.spec.ts` + este relatório |

---

## 2. Gates automáticos

Todos executados nesta sessão (frontend em `GasFlow/frontend`, backend em `GasFlow/backend`):

| Gate | Comando | Resultado |
|---|---|---|
| Typecheck | `npx tsc -b` | **OK** (sem erros) |
| Lint | `npx eslint src` | **OK** (sem avisos) |
| Unit/integração | `npx vitest run` | **73 arquivos / 434 testes passando** |
| Guard de integridade | `ADMIN_PASSWORD=audit-password-123 python -m tests.integrity_audit` | **`findings=19 pendentes=0`** (9 `dado-invisivel` + 10 `whatsapp-sem-consumidor`) |
| E2E (carga/tipos) | `npx playwright test central-financeira.spec.ts --list` | **7 testes listados**; `tsc --noEmit` da spec **limpo** |

> **Nota de ambiente (pytest):** não rode o `pytest` com `ADMIN_PASSWORD=audit-password-123`.
> `backend/tests/conftest.py` faz `os.environ.setdefault("ADMIN_PASSWORD", "test_password_123")`,
> então a variável do integrity audit **quebra todas as fixtures de login** (`/auth/login` → 401).
> O `pytest` usa o default dele; o `integrity_audit` usa `audit-password-123`.

---

## 3. E2E novo — `e2e/tests/central-financeira.spec.ts`

Cobre o roteiro do §6 num único arquivo, reaproveitando o padrão da suíte
(sessão de admin via `storageState` do `global-setup`; login real pela UI só no
1º caso, por causa do rate limiter de 5 tentativas/5 min).

| Teste | Verifica |
|---|---|
| login pela UI e menu com uma única entrada "Financeiro" | login real → `/` → sidebar com **1** link `Financeiro` e **0** de `Financeiro & Relatórios`/`Relatórios`/`Mapa de Calor`/`Central Financeira` → clique leva a `/finance` (h1 "Central Financeira") |
| presets de período, inclusive 180 dias | `30 dias` ativo por padrão → clicar `180 dias` → `aria-pressed` alterna e o subtítulo confirma `· 180 dias` |
| cada seção abre com o seu título e atualiza `?secao=` | itera **todas** as abas do grupo "Seções da Central Financeira" (15 com `audit.view`, 14 sem) conferindo o `h2` de cada uma e o deep-link; fecha com deep-link direto em `?secao=conciliacao` |
| cria uma despesa pela UI e ela aparece na tabela | aba Despesas → Dialog "Nova despesa" → Registrar → Dialog fecha + toast → busca no servidor (`q`) e a linha aparece |
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

---

## 4. Checklist §6 do plano

- [x] **E2E novo** (`central-financeira.spec.ts`) — login → menu com uma entrada →
  `/finance` abre → presets (inclusive 180) → seções/deep-link → criar despesa →
  redirects sem 404 → Imprimir no fallback → modo TV entra/sai. *Spec escrita,
  listada e tipada; execução contra o stack é o passo de ambiente.*
- [ ] **Manual por seção (15)** — roteiro pronto na §5; falta rodar com dado real.
- [ ] **Impressão de cada seção principal** — roteiro pronto na §5; falta o PDF do
  Electron e o `window.print` do browser com dado real.
- [ ] **Screenshots + evidências** — capturar rodando o stack (§6).

> Os três itens abertos dependem de um ambiente com o stack no ar. Nada neles foi
> "marcado por engano": o que é automatizável foi entregue e validado; o que é
> visual/presencial permanece explicitamente pendente.

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
gerar o PDF via `printToPDF` do conteúdo renderizado (modo `pdf`); (b) no
browser, deve abrir o diálogo do sistema (modo `print`) com o cabeçalho
`print-only` (marca + "Central Financeira · <seção>" + período + gerado em) e o
rodapé com as 3 assinaturas; sidebar/header/ações ficam ocultos (`data-no-print`).

**Screenshots** — sugerido anexar: `/finance` (Visão Geral, 30 e 180 dias),
uma seção analítica por PR (P6–P8), a impressão limpa e o modo TV ativo.

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
