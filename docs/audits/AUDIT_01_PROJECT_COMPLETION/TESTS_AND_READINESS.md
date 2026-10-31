# Tests and Readiness — AUDIT-01B

## Evidência histórica verificada

| Data/evidência | Resultado | O que prova | O que não prova |
| --- | --- | --- | --- |
| INT-01, 26/10 | Backend 2.526 passed/30 skipped; frontend 528/528 + build; WhatsApp 160/160; mobile 75/75; total declarado 3.489 passed, 0 falhas | Suites/builds executados na integração | E2E, runtime Docker, aparelho, WhatsApp real ou backup/restore real naquela frente |
| LAB-01/02/03, 28/10 | 5 containers healthy; PG/Redis; backend/frontend; 9 smoke checks sem falha | Runtime isolado, API/SPA e login/dashboard no laboratório | Produção contínua, operação da Marcos Gás ou disponibilidade sustentada |
| LAB-05, 28/10 | Dump custom 225.526 bytes; restore em DB descartável; 69 tabelas, 299 índices, 113 constraints; 1.108 linhas comparadas sem diff | Restore real de banco fictício e integridade do artefato restaurado | Backup de produção, off-host, retenção, scheduler, RPO/RTO ou migração do cliente |
| R-1, 28/10 | Correção montada read-only em container descartável contra PostgreSQL real; `RESULT=PASS`, 69→69 tabelas, zero ERROR; regressões 26 + 32 passed | Código corrigido não dispara a cadeia SQLite no PostgreSQL | Correção incorporada à imagem do lab; relatório afirma que imagem era pré-correção |
| AUDIT-01, subset | `test_init_db_dialect_selection.py` + `test_ops01b_homeserver_profile.py`: 39 passed em 91,45s | Testes no checkout auditado | Runtime atual ou produção |

## Gates

- **LAB-01: aprovado.** PostgreSQL/Redis saudáveis, `gasflow_lab`, sem portas DB publicadas.
- **LAB-02: aprovado com ressalva R-1.** 25 upgrades, Alembic em `a4b5c6d7e8f9`, backend healthy. A imagem testada antecede R-1.
- **LAB-03: aprovado.** Frontend/Nginx e smoke `9/9`; `127.0.0.1:8088` como única porta do lab.
- **LAB-04: em andamento.** Isolamento e health aprovados, mas sem conta pareada, sessão, QR, mensagem enviada ou mensagem recebida.
- **LAB-05: aprovado para dado fictício.** Restore independente verificado; não confundir com backup/restore de produção.
- **LAB-06: pendente.** O plano exige todos os gates anteriores aprovados; LAB-04 continua aberto. `docker ps` não conectou ao daemon na consulta de 30/10, então runtime atual não é observável.

## Dimensões que não devem ser confundidas

1. **Implementação:** medida no CSV em quatro dimensões com notas discretas.
2. **Validação técnica:** testes de unidade/integração, análise estática e comparação de schema/dados conforme o escopo.
3. **Validação operacional:** execução controlada do laboratório. Há provas históricas de LAB-01/02/03/05, não de operação contínua.
4. **Prontidão de produção:** inclui backup off-host, retenção/restauração recorrente, migração de dados da Marcos Gás, segurança/PII, recuperação, host adequado, dispositivo e WhatsApp; continua baixa e bloqueada.

O texto antigo que dizia “nenhum laboratório foi iniciado” e “não há prova de backup/restore em ambiente vivo” foi supersedido. O estado correto é: **runtime histórico de laboratório e restore fictício comprovados; runtime atual indisponível para consulta; produção não validada**.
