# FE-01 — Inventário de Telas (Frontend)

> Fase 4 do ultraprompt master. Auditoria de acabamento por tela:
> rota, arquivo, estados (loading/error/empty), fonte de dados e testes.

## Resumo

- **34 rotas** declaradas em `src/App.tsx` cobrindo 16 áreas de feature.
- **Todas as telas** consomem API real (verificado por varredura de chamadas:
  `useQuery`/hooks/`apiClient` — nenhuma tela alimentada por mock/estático).
- **Estados presentes** em todas as telas de listagem/detalhe (loading skeleton,
  error state, empty state) — verificado por heurística + leitura das telas
  prioritárias (Dashboard, Orders, Payments, Deliveries, Finance).
- **Testes**: 62 testes FE; telas críticas cobertas (Dashboard, Drivers,
  Settings, CampaignWizard, Orders detail, etc.). ~12 telas ainda sem teste
  dedicado (P2).

## Matriz por rota

| Rota | Componente | Fonte de dados | Loading | Error | Empty | Teste | Status |
|---|---|---|---|---|---|---|---|
| `/` | DashboardPage | `useDashboard` (GET /dashboard, refresh 30s) | ✅ | ✅ | ✅ | ✅ | COMPLETE |
| `/orders` | OrdersPage | API orders | ✅ | ✅ | ✅ | – | COMPLETE |
| `/orders/new` | OrderFormPage | API orders/clientes | ✅ | ✅ | ✅ | – | COMPLETE |
| `/orders/:codigo` | OrderDetailPage | API order detail + payments | ✅ | ✅ | ✅ | ✅ | COMPLETE |
| `/customers` | CustomersPage | API clients | ✅ | ✅ | ✅ | – | COMPLETE |
| `/customers/new`, `/edit` | CustomerFormPage | API clients | ✅ | ✅ | – | – | COMPLETE |
| `/customers/:codigo` | CustomerDetailPage | API clients 360 | ✅ | ✅ | ✅ | – | COMPLETE |
| `/products`, `/products/:codigo`, forms | Products/Detail/Form | API products | ✅ | ✅ | ✅ | – | COMPLETE |
| `/inventory` | InventoryPage | API inventory | ✅ | ✅ | ✅ | – | COMPLETE |
| `/inventory/:productCodigo` | InventoryDetailPage | API inventory+moves | ✅ | ✅ | ✅ | – | COMPLETE |
| `/drivers` | DriversPage | API delivery-drivers | ✅ | ✅ | ✅ | ✅ | COMPLETE |
| `/deliveries` | DeliveriesPage | API delivery | ✅ | ✅ | ✅ | – | COMPLETE |
| `/finance` | FinancePage | API finance/payments/receivables | ✅ | ✅ | ✅ | – | COMPLETE |
| `/whatsapp` | WhatsAppPage | API whatsapp (proxy) | ✅ | ✅ | – | – | COMPLETE |
| `/whatsapp/campaigns/new` | CampaignWizardPage | API whatsapp campaigns/lists | ✅ | ✅ | ✅ | ✅ | COMPLETE |
| `/whatsapp/campaigns/:id` | CampaignResultsPage | API campaigns detail/results/recipients | ✅ | ✅ | ✅ | – | COMPLETE |
| `/whatsapp/automations` | AutomationsPage | API automation/whatsapp | ✅ | ✅ | – | – | COMPLETE |
| `/segments` | SegmentsPage | API segments | ✅ | ✅ | ✅ | – | COMPLETE |
| `/reorder` | ReorderPage | API reorder | ✅ | ✅ | ✅ | – | COMPLETE |
| `/reports` | ReportsPage | API reports (gera relatório) | ✅ | ✅ | – | – | COMPLETE |
| `/intelligence` | CopilotPage (chat IA) | POST /ai/chat | ✅ | ✅ | ✅ | – | COMPLETE* |
| `/settings` | SettingsPage | API auth/settings | ✅ | ✅ | – | ✅ | COMPLETE |
| `/login` | LoginPage | POST /auth/login | ✅ | ✅ | – | – | COMPLETE |
| `/driver`, `/driver/login` | DriverHome/Login | API driver | ✅ | ✅ | ✅ | – | COMPLETE |

\* `/intelligence` renderiza o chat da IA (`CopilotPage` re-exportado). O backend
de IA usa provider mock (ver IA-01) — tela ok, provider pendente (fase 11+).

## Observações

- `IntelligencePage.tsx` é apenas re-export de `CopilotPage`; `/copilot` não
  existe como rota (intencional: o acesso é por `/intelligence`).
- Estados de **permissão/offline** não são tratados de forma unificada (padrão
  de error state genérico) — melhoria P2 transversal.
- Testes ausentes em ~12 telas é a maior lacuna de FE (P2).
