# AUDIT-01B — Reconciliação com a homologação real

**Data:** 30/10/2026
**Branch consultada:** `release/home-server-candidate`
**HEAD consultado:** `e989f70`
**Escopo:** corrigir a avaliação AUDIT-01 com evidência histórica e estado atual somente leitura. Nenhum container foi iniciado/reiniciado/reconstruído; nenhuma migration, banco, sessão WhatsApp, commit, push, merge, reset ou deploy foi executado.

## Resultado executivo

A AUDIT-01 afirmou incorretamente que o Home Server nunca havia sido iniciado e que não existia prova de backup/restore real. O relatório `docs/integration/LAB_01_04_RUNTIME_REPORT.md`, produzido em 28/10, documenta runtime real de laboratório e recuperação independente de um PostgreSQL **fictício**. Essa evidência é válida historicamente mesmo que o Docker esteja desligado na consulta atual.

Em 30/10, uma consulta somente leitura de `docker ps` não conseguiu conectar ao named pipe `dockerDesktopLinuxEngine`. Portanto, o runtime presente hoje é **não observável**, não “nunca executado”. A consulta não iniciou o daemon.

## Tabela de reconciliação

| Resultado anterior da AUDIT-01 | Evidência nova ou recuperada | Resultado corrigido | Impacto percentual / motivo |
| --- | --- | --- | --- |
| “Nenhum laboratório foi iniciado; Home Server apenas estático.” | LAB-01/02/03 executados em 28/10. Cinco containers healthy: PostgreSQL, Redis, backend, frontend e WhatsApp. Única porta publicada `127.0.0.1:8088`. | Histórico de runtime real confirmado. Estado atual em 30/10 não observável porque daemon indisponível. | Home Server: validação operacional corrigida para 64,00%. Não equiparar a disponibilidade contínua. |
| “Backend e frontend não foram testados em runtime.” | LAB-02: 25 upgrades em banco novo até `a4b5c6d7e8f9`, backend healthy e 69 tabelas. LAB-03: frontend/Nginx e smoke `9 ok / 0 falhas`. | Backend/frontend aprovados nos gates históricos indicados; não há aceite de produção. | Incluído em HS-01/02/03/04 e MVP; a dimensão operacional agora é separada da técnica. |
| “Não há prova de backup/restore PostgreSQL real.” | LAB-05: `pg_dump` custom de `gasflow_lab`, 225.526 bytes; `pg_restore` independente em banco descartável; 69 tabelas, 299 índices, 113 constraints, zero constraints não validadas; 1.108 linhas e schema comparados sem diferença. | Restore real de **dado fictício de laboratório** comprovado. Não é restore de produção nem backup da Marcos Gás. O dump mock de 69 bytes não foi usado no restore. | HS-07: operacional 1,00 para restore fictício; prontidão 0,25. Backup off-host/agendamento/retention permanece 0,00 de prontidão (HS-08). |
| “R-1 de `init_db.py` só foi testado em unit tests.” | R-1 corrigido localmente em 28/10; regressões 26 + 32 passed; container descartável com código montado read-only contra PostgreSQL descartável: `RESULT=PASS`, 69→69 tabelas e zero ERROR. | Correção de fonte testada em PostgreSQL real descartável. O relatório afirma que a imagem do lab ainda era pré-R-1; não registra digest da imagem. | HS-03: técnica 1,00, operação 0,75 e produção 0,25. Não creditar à imagem do lab a correção que ela ainda não continha. |
| “WhatsApp do laboratório não validado.” | LAB-04: container healthy, zero restarts, volumes exclusivos, rotas protegidas, broadcast false, webhook vazio; contas disconnected, sem QR/sessão. | Isolamento e saúde do serviço validados; pareamento e mensagem de prova continuam pendentes. Não existe simulador E2E no runtime. | Serviço isolado recebe crédito operacional parcial; envio/recebimento real permanece 0,00 operacional e 0,00 produção. |
| “Home Server operacional estimado em 82,5% de implementação / 47,5% validação.” | Evidência real de runtime/restore, mas também ausência de off-host backup, restore periódico, RPO/RTO, continuidade e host apropriado. | Home Server: 66,75% implementação; 77,50% técnica; 64,00% operacional; 21,50% prontidão. | Implementação: -15,75 pp. A validação anterior misturava teste e operação; não é comparável à nova divisão. |
| “MVP Marcos Gás: 67,5% implementação / 41,3% validação.” | INT-01 demonstra testes e demo com dados fictícios; não há migração, fluxo em campo ou aceite com dados da empresa. Relatórios oficiais mantêm pendentes mobile físico, offline, GPS, WhatsApp, idempotência e backup pré-migration. | MVP: 55,00% implementação; 56,75% técnica; 24,25% operacional; 15,00% prontidão. | Implementação: -12,50 pp. Validação antiga não comparável; requisitos funcionais e de dados antes ausentes foram incluídos. |
| “SaaS: 38,0% implementação / 7,6% validação.” | Testes de tenant/RBAC existem, mas não há execução multitenant, onboarding, cobrança ou backup/restore por tenant. | SaaS: 42,50% implementação; 46,00% técnica; 0,00% operacional; 0,00% prontidão. | Implementação: +4,50 pp por reponderação/cobertura; nenhuma elevação por evidência operacional nova. |
| “Global: 67,6% implementação / 38,1% validação.” | A matriz anterior só tinha duas colunas de pontuação e misturava evidências diferentes; a nova matriz tem 34 requisitos e quatro dimensões. | Global 55/30/15: 56,65% implementação; 61,36% técnica; 32,54% operacional; 14,70% prontidão. | Implementação: -10,93 pp. Antiga validação não comparável. P0 é bloqueador absoluto, não compensável pelo global. |
| “Próximo passo: iniciar LAB-01 e provar backup/restore.” | LAB-01 e LAB-05 já aprovados historicamente; LAB-04 está aberto, LAB-06 não aprovado. OPS-00B não recomenda o notebook para serviço Home Server contínuo. | Não repetir gates já comprovados sem nova autorização. Priorizar proteção de dados/deploy, proveniência de imagem, número de teste e aceite final. | Roadmap reordenado para proteção de dados da Marcos Gás e segurança antes de expansão. |

## O que foi confirmado

### Runtime e gates

- **LAB-01 aprovado:** PostgreSQL e Redis healthy; database `gasflow_lab`; portas 5432/6379 não publicadas no host.
- **LAB-02 aprovado com ressalva R-1:** Alembic aplicou 25 upgrades; `alembic current = head = a4b5c6d7e8f9`; 69 tabelas; backend healthy. A imagem do runtime era pré-R-1.
- **LAB-03 aprovado:** frontend/Nginx respondendo; nove smoke checks aprovados; 8088 bind em loopback.
- **LAB-04 em andamento:** isolamento do serviço comprovado; sem pareamento, QR, sessão ou envio/recebimento. Ação de pareamento deve ser humana e usar número de teste dedicado.
- **LAB-05 aprovado para banco fictício:** dump custom e restore independente; a base de comparação contém dados de teste. A divergência posterior em duas tabelas vivas (`auth_audit_log` e `auth_sessions`) foi explicada por escrita do backend depois do dump.
- **LAB-06 pendente:** exige LAB-01…05 aprovados, testes estáticos, status Git limpo e checklist final. LAB-04 não passou; o worktree atual também está modificado/não limpo.

### Última correção e imagem

A última correção funcional identificada nesta linha é R-1, alteração local em `backend/app/infrastructure/database/init_db.py`: o caminho de migração leve SQLite passa a ser selecionado pelo dialeto e o PostgreSQL deixa de executar `PRAGMA`. Os testes de dialeto e o teste em PostgreSQL descartável passaram conforme o relatório.

A correção **não foi incorporada à imagem Docker de laboratório** na homologação documentada. Não há digest da imagem para identificar precisamente o código carregado. O HEAD local continua `e989f70`; a correção e novos testes aparecem como alterações locais/não rastreadas. Não houve rebuild durante esta reconciliação.

### Estado atual do host

Em 30/10, `docker ps` falhou ao conectar a `//./pipe/dockerDesktopLinuxEngine`. Nenhum serviço foi iniciado ou reiniciado. Isso somente informa que o daemon não estava acessível nesta consulta. Não desclassifica LAB-01/02/03/05 históricos.

**Intervalo de incerteza:** a conformidade da imagem que eventualmente esteja instalada agora com R-1 é indeterminada, intervalo de pontuação `[0.00, 1.00]` (0–100%): não foi possível consultar o daemon e o relatório de 28/10 não registra digest. Para a imagem efetivamente testada em 28/10, a evidência é conclusiva: era pré-R-1 (0% de incorporação da correção). Se a imagem atual fosse comprovada como contendo R-1, o máximo impacto matemático isolado seria +4,00 pp na prontidão Home Server e +1,20 pp na prontidão global; esses pontos **não** foram concedidos nos percentuais publicados.

OPS-00B descreve o host como notebook i3 2c/4t, HDD mecânico 5400 rpm e 12 GB de RAM, e **não recomendado** para Home Server completo em produção contínua. Um laboratório limitado em execução controlada é diferente de hospedagem contínua.

## Lacunas de método corrigidas

- A matriz anterior continha notas `0.40` e `0.10`, incompatíveis com a escala declarada. Todas as notas agora pertencem a `{0, 0.25, 0.50, 0.75, 1.00}`.
- Status “concluído e validado” foi substituído por estados específicos: teste técnico, runtime de lab, pareamento pendente, imagem divergente, produção não validada.
- “Validação” foi dividida em validação técnica, operacional e prontidão para produção.
- Cada requisito declara justificativa do peso em `weight_rationale`; cada escopo soma 100.
- Foram adicionados requisitos antes ausentes: aparelho/campo, migração de dados da Marcos Gás, privacidade/PII, backup off-host, recuperação de host, identidade da imagem e adequação do host.
- A avaliação de SaaS não recebe validação operacional sem execução multitenant. A existência de testes de tenant só pontua validação técnica.
- A nova prontidão de produção é uma dimensão de gates; não significa percentual de chance nem substitui critérios de go/no-go.

## PII e segurança de dados

`docs/integration/OPS_01C_LAB_PLAN.md` e `docs/delivery/PENDENCIAS_BLOQUEANTES.md` registram arquivo de contatos/exports versionados com dados pessoais e risco de publicação. Esta reconciliação não leu registros, copiou arquivos, alterou histórico ou modificou worktrees. Não publicar/distribuir cópias do repositório contendo esses artefatos antes de decisão do proprietário e tratamento aprovado.

## Bloqueadores reais e sequência de trabalho

### Cinco maiores bloqueadores

1. Não há gate de release comprovado que exija backup verificável off-host e aborte antes de Alembic se o backup falhar.
2. Migração SQLite→PostgreSQL e reconciliação de clientes, pedidos, entregas e saldos da Marcos Gás não foram executadas em cópia autorizada.
3. R-1 ainda não está comprovadamente na imagem executada; build/digest/proveniência faltam.
4. Host avaliado não é recomendado para Home Server contínuo; destino de backup off-host também não foi comprovado.
5. Operação de campo e comunicação seguem incompletas: LAB-04 sem pareamento; app sem validação em aparelho; LAB-06 não aceito.

### Próximas cinco tarefas

1. Implementar o gate de backup off-host pré-migration, fail-closed, com teste que prova que Alembic não é chamado quando backup falha e com relatório/hash do artefato.
2. Definir host e destino de backup apropriados para a Marcos Gás; formalizar autorização e política de dados/PII.
3. Incorporar R-1 a uma imagem versionada e identificada; validar em banco descartável e repetir o smoke no laboratório, mediante autorização operacional futura.
4. Concluir LAB-04 com número de teste dedicado; em seguida concluir LAB-06 e registrar exceções/aceite.
5. Ensaiar a migração da Marcos Gás em cópia segura, reconciliar contagens/totais, ensaiar rollback e só então avaliar uma janela de corte.

## Primeira tarefa exata de desenvolvimento

**Criar o gate de deploy `backup → verificação do backup → Alembic`, onde qualquer falha ou ausência de backup aborta o deploy antes de executar migrations; guardar o backup fora do host, registrar hash/manifesto e identificar a imagem por versão/digest.**

Critérios de aceite mínimos: teste automatizado demonstra que backup inválido/indisponível nunca chama Alembic; backup aprovado produz artefato verificável off-host; execução de teste restaura em banco descartável e compara contagens/schema; logs não contêm DSN/segredos nem dados pessoais. Essa tarefa é de desenvolvimento/teste em ambiente descartável, não autorização para executar migration, backup ou deploy na operação da Marcos Gás.

## Fontes examinadas

- `docs/integration/LAB_01_04_RUNTIME_REPORT.md`
- `docs/integration/INT_01_FINAL_REPORT.md`
- `docs/integration/OPS_01C_LAB_PLAN.md`
- Os seis documentos anteriores da AUDIT-01 e `COMPLETION_MATRIX.csv`
- `docs/delivery/PENDENCIAS_BLOQUEANTES.md`, `docs/delivery/STATUS_DE_ENTREGA.md`, `docs/ops/OPS_00B_PC_HEALTH_AUDIT.md`
- `backend/tests/test_ops01d_pg.py`, `backend/tests/test_init_db_dialect_selection.py`, `backend/tests/test_init_db_alembic_boot.py`
- Git status/log e diff local de `init_db.py` consultados sem edição; `docker ps` consultado sem iniciar serviços.
