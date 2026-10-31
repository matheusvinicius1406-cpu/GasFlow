# Feature Matrix — AUDIT-01B

> Estado reconciliado com INT-01, OPS-01C-A e runtime de 28/10. “Validado em lab” significa execução controlada histórica com dados fictícios; não significa produção, uso contínuo ou validação com dados da Marcos Gás.

| Recurso | Estado corrigido | Evidência atual | Lacuna / próxima ação | Prioridade |
| --- | --- | --- | --- | --- |
| Auth e RBAC | Testado tecnicamente; homologação com equipe pendente | Testes de auth/RBAC; login e dashboard responderam no smoke do lab | Validar papéis e limites com contas de teste | P0 |
| CRM de clientes | Testado tecnicamente; sem aceite da Marcos Gás | Código e testes CRM/contacts; nenhum fluxo de cliente real homologado | Homologar CRUD com dados sintéticos; só migrar após gates de dados | P1 |
| Produto e estoque | Testado tecnicamente; sem aceite operacional | Testes de inventário e reversão | Reconciliar saldos em cenário sintético | P1 |
| Pedido e entrega web/Desktop | Testado; demo documentada com dados fictícios | INT-01 e testes backend; E2E contra stack não executado | Homologar fluxo completo antes de uso comercial | P1 |
| Financeiro/caixa | Testado tecnicamente; sem fechamento homologado | Testes financeiros/contratos | Validar valores sintéticos e reversões | P1 |
| App do entregador | Lógica testada; aparelho não validado | INT-01 registra 75 testes/typecheck e correções MOBILE-P0 | APK, GPS, tela bloqueada, offline e reconexão em aparelho | P1 |
| Rastreamento | Parcial; sem GPS físico | Testes de ingest/ETA | GPS em background não comprovado; aparelho pendente | P1 |
| Gateway WhatsApp isolado | Validado em lab | LAB-04 container healthy, volumes exclusivos, rotas protegidas e broadcast desligado | Não implica conta conectada | P1 |
| WhatsApp envio/recebimento | Bloqueado; sem pareamento | Contas disconnected, sem QR/sessão; mock só em unit tests | Parear número de teste e comprovar mensagem; não usar conta Marcos Gás | P0 |
| Home Server Compose e runtime | LAB-01/02/03 aprovados historicamente | Cinco containers healthy, porta única `127.0.0.1:8088`, backend/frontend saudáveis | Estado atual desconhecido: daemon indisponível em 30/10 | P1 |
| Smoke de aplicação | Aprovado historicamente | LAB-03 reporta 9 ok / 0 falhas, incluindo SPA, health/readiness, API, auth e dashboard | Não é E2E abrangente nem aceite da empresa | P1 |
| PostgreSQL/Redis | Aprovados em lab | LAB-01, DB `gasflow_lab`, ambos healthy, sem portas DB no host | Banco apenas fictício; nenhuma produção | P1 |
| Boot/migration do backend | LAB-02 aprovado com ressalva R-1 | 25 migrations até `a4b5c6d7e8f9`, 69 tabelas; imagem histórica pré-R-1 | R-1 testado em PG descartável, não incorporado à imagem do lab | P0 |
| Backup/restore PostgreSQL fictício | LAB-05 aprovado | Dump custom 225.526 bytes; restore independente; 69 tabelas, 299 índices, 113 constraints, 1.108 linhas sem diff | Não é backup de cliente ou produção | P0 |
| Backup off-host, retenção e agendamento | Não homologado | Nenhuma evidência de destino externo, retenção ou job agendado | Projetar e testar backup verificável fora do host | P0 |
| Migração SQLite→PostgreSQL / dados Marcos Gás | Não executada | Ferramentas e rehearsal sintético existem; nenhum dado real migrado | Cópia autorizada, reconciliação, rollback e aprovação antes de corte | P0 |
| Recuperação de host/rollback | Parcial | Restore de DB fictício provado; falha de host, RPO/RTO e rollback de release não | Simular recuperação completa em ambiente seguro | P0 |
| Imagem Docker ↔ código-fonte | Divergência reportada | Imagem do lab pré-R-1; digest/build não registrado | Incorporar fix em release rastreável e testar imagem identificada | P0 |
| Host Home Server contínuo | Não recomendado no host avaliado | OPS-00B: i3 2c/4t, HDD 5400 rpm, 12 GB RAM | Escolher host adequado; lab curto não comprova disponibilidade | P0 |
| Desktop / frontend / relatórios | Vários testes e build históricos; sem aceite operacional completo | INT-01: 528/528 frontend + build; testes Desktop identificados | E2E e fluxos reais não comprovados pela integração | P2 |
| SaaS: isolamento de tenant | Código/testes; sem operação multitenant | Testes tenant/cross-tenant existentes | Validar endpoints, jobs, cache, arquivos e admin com empresas isoladas | P0 |
| SaaS: onboarding, cobrança e export/restore tenant | Não demonstrado ou não iniciado | Sem evidência operacional; LAB-05 foi banco fictício único | Definir e implementar após segurança da Marcos Gás | P1/P3 |
| Privacidade e dados versionados | Risco aberto | OPS-01C-A documenta PII em `data/prototype-contacts/app.db` e exports versionados | Não copiar nem expor; decisão do proprietário antes de distribuir/publicar | P0 |

## Critério de leitura

INT-01 (26/10) é evidência de integração e testes, não de runtime. O relatório LAB posterior (28/10) comprova runtime de laboratório e restore fictício. OPS-01C-A anterior (26–27/10) dizia “não iniciado”, mas foi superado pelos resultados datados de 28/10. Em 30/10, o daemon não respondeu; não presumir continuidade nem apagar os resultados históricos.
