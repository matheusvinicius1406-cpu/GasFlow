# FE-02: Testes de Frontend — Cobertura das Telas

## Telas Testadas

| Tela | Arquivo de teste | Stmts |
|------|------------------|-------|
| OrdersPage | `orders/__tests__/OrdersPage.test.tsx` | 75% |
| OrderFormPage | `orders/__tests__/OrderFormPage.test.tsx` | 54% |
| ProductsPage | `products/__tests__/ProductsPage.test.tsx` | 72% |
| ProductFormPage | `products/__tests__/ProductFormPage.test.tsx` | 79% |
| CustomersPage | `customers/__tests__/CustomersPage.test.tsx` | 53% |
| CustomerFormPage | `customers/__tests__/CustomerFormPage.test.tsx` | 79% |
| DeliveriesPage | `deliveries/__tests__/DeliveriesPage.test.tsx` | 43% |
| InventoryPage | `inventory/__tests__/InventoryPage.test.tsx` | 76% |
| DriverFormPage | `drivers/__tests__/DriverFormPage.test.tsx` | 82% |
| FinancePage | `finance/__tests__/FinancePage.test.tsx` | 57% |
| ReportsPage | `reports/__tests__/ReportsPage.test.tsx` | 100% |

DriversPage já possuía teste (73% stmts). Todas as telas acima passaram de **0% → cobertura real** nesta fase (antes do FE-02 não existiam arquivos de teste para elas).

## Utilitário de Teste

`src/test/utils.tsx` (novo):
- `renderWithProviders(ui, { route })` — QueryClientProvider + MemoryRouter (padrão para páginas)
- `renderWithRoute(ui, path, route)` — adiciona `<Routes>` com `<Route path>` para páginas que dependem de `useParams` (formulários em modo edição)

## Cobertura Antes × Depois

| Métrica | Antes (62 testes / 8 arquivos) | Depois (102 testes / 19 arquivos) | Δ |
|---------|-------------------------------|-----------------------------------|----|
| % Stmts | 50.39 | 57.02 | **+6.63 pp** |
| % Branch | 45.47 | 50.25 | +4.78 pp |
| % Funcs | 45.62 | 40.80 | −4.82 pp* |
| % Lines | 53.23 | 60.13 | **+6.90 pp** |

*Funcs caiu porque os novos testes exercitam telas grandes com muitos handlers (ex.: linhas 218-443 do FinancePage, 58-282 do CampaignWizardPage existente) — caminhos de funções não exercitados diluem a média. As linhas executáveis cobertas subiram em todas as telas testadas.

`@vitest/coverage-v8@4.1.11` adicionado como devDependency (test-only) para permitir `vitest run --coverage`.

## Bugs Reais Encontrados e Corrigidos

1. **ReportsPage — estado de erro inalcançável**: `fetchData` usava `Promise.allSettled`, que nunca rejeita → o `catch` que setava `setError(true)` era código morto; se os dois endpoints falhassem a página mostrava "Sem dados para exibir" em vez da mensagem de erro. Corrigido para `Promise.all` (mesmo padrão do FinancePage): falha de qualquer endpoint → `ErrorState` com retry.

## Comandos de Validação

```bash
npm test                 # vitest run → 102 passed (19 files)
npm run typecheck        # npx tsc --noEmit → 0 erros
npx vitest run --coverage  # All files 57.02% stmts
```

## Próximos Passos

- SettingsPage (16.8%) e CampaignWizardPage (50.4%) — os menores índices restantes
- Telas de automação (Automations) sem testes
- Testes E2E (Playwright) — fase E2E-01 futura
