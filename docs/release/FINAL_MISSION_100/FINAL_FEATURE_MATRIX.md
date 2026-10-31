# Final Feature Matrix

Estados são separados em implementação, evidência técnica, operação e produção.
Teste unitário não equivale a campo; runtime histórico do lab não equivale a
runtime atual.

| Área | Estado | Evidência disponível | Pendência de aceite |
| --- | --- | --- | --- |
| Auth/RBAC/tenant | Código/testes executados nesta missão | Suíte completa 2552 passed inclui `test_auth_*`, `test_sec01_*`, `test_sec01c_*` | Repetir adversarialmente e aceitar com contas sintéticas |
| CRM/endereço | Parcialmente implementado | Código e testes CRM na suíte verde | Requisitos de endereços alternativos, importação segura, histórico e dedupe |
| Produto/estoque | Implementado e testado | Reversão idempotente por referência (`reverse_delivery_stock_atomic`) + `test_delivery_stock_reversal` na suíte | Aceite de movimentos e não-negatividade em operação |
| Pedido/entrega | Fluxo existente | Suíte completa verde, incluindo readiness do fluxo `start → arrive → complete` | E2E contra stack e aceite operacional não executados |
| Financeiro/caixa | Parcial | `test_financial`, `test_finance_*`, `test_pix_service` verdes na suíte | Imutabilidade, estorno compensatório, conciliação e fechamento |
| Relatórios/dashboard | Parcial | `test_finance_reports_p2`, `test_finance_period_report` verdes | Reconciliar cada KPI com dados sintéticos e exports |
| App entregador | **Fila offline persistente + idempotência implementadas e provadas** | 86 testes mobile verdes (`node --test`), `tsc --noEmit` limpo, `app-release.apk` gerado com `gasflow.driver.queue.v1` e `PersistentQueueStorage` no bundle | Instalação em aparelho, GPS em background (P1-2), tela bloqueada, prova de entrega em campo |
| CI mobile | **Job `mobile` adicionado** | YAML validado (8 jobs) e comandos executados localmente | Primeira execução no runner do GitHub (depende de push/PR) |
| WhatsApp inbound | Configurado, sem teste com contas da empresa nesta sessão | Suite simulada e bridge | Número de teste e aceite humano |
| WhatsApp outbound | Fail-closed reforçado | `WA_SEND_MODE=live` obrigatório e **`WA_BROADCAST_ENABLED` agora defaulta `false`** em produção; 162 testes verdes | Rebuild de imagem e homologação apenas com número de teste autorizado |
| Desktop SQLite | Preservado por regressões focadas | `test_schema_migration`, `test_desktop_migrations`, `test_init_db_dialect_selection` verdes na suíte completa | Regressão completa e teste no pacote instalado; suíte Electron não rodou (`desktop/node_modules` ausente) |
| PostgreSQL bootstrap | Guard contra schema fora do head | 13 testes focados + suíte completa verde | Imagem buildada/testada e runtime atual indisponível |
| Backup pré-migration | Gate implementado/testado com doubles | 6 testes isolados: dump falhou ⇒ Alembic **não** executado | Destino off-host e ensaio em DB descartável com Docker autorizado |
| Restore PostgreSQL | Homologação histórica com DB sintético | LAB-05: 69 tabelas, 299 índices, 113 constraints, 1108 linhas comparadas | Política off-host, retenção, RPO/RTO e restore periódico |
| Home Server Compose | Isolamento histórico e configuração atual | LAB-01/03 histórico; teste de configuração do lab (48 passed) | Estado de containers desconhecido; imagem/digest atual não provado |
| SaaS isolation | Dois tenants sintéticos isolados em nível de API | `test_cross_tenant_isolation` (TestClient, tenant A/B) passou na suíte de 2552 | Isolamento por jobs, arquivos, cache, relatórios, WhatsApp e backup em runtime de serviço |
| Provisionamento/billing SaaS | Não demonstrado | Nenhuma evidência de fluxo pronto nesta sessão | Contrato de produto, onboarding, planos e provedor sandbox |
| PII/LGPD | Risco aberto | OPS-01C registra material pessoal versionado em histórico/árvore | Decisão do proprietário; não foi lido/exposto/limpo nesta missão |

Matriz atômica e notas completas: `FINAL_COMPLETION_MATRIX.csv`. Os itens sem
aceite permanecem pendentes.
