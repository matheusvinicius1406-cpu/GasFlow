# Final Home Server Report

## Evidência histórica

Relatório de 28/10: LAB-01/02/03 e LAB-05 aprovados; cinco containers healthy; 9 smoke checks; PostgreSQL `gasflow_lab` com 69 tabelas; dump custom e restore independente fictício com 69 tabelas, 299 índices, 113 constraints e 1108 linhas comparadas sem diferença. LAB-04 sem pareamento e LAB-06 pendente.

## Alterações desta missão

- Produção não executa mais `alembic upgrade head` implicitamente no boot.
- Backend exige PostgreSQL com `alembic_version` no head; fora do head recusa iniciar.
- Compose do lab conserva Alembic explícito no banco descartável.
- Criado gate host-side backup → verificação → migration → verificação de head, sem iniciar serviços.
- Testes do gate usam doubles; 6 passaram.
- `WA_BROADCAST_ENABLED` passou a defaultar `false` em produção (duas chaves explícitas para campanha), validado por `test_prod_stack_config.py` + `test_ops01b_homeserver_profile.py` (**48 passed** após a alteração).

## Estado atual

Em 30/10, `docker ps` não conectou ao daemon; a sessão inteira foi executada sem Docker. Nenhum serviço foi iniciado/reiniciado/reconstruído, nenhum volume foi tocado e nenhum `down -v` foi executado. A imagem que rodará as alterações não foi gerada; o digest histórico não está registrado. Portanto, config/código atual não comprovam que um container atual contém R-1, guard de head ou dry-run.

A suíte completa do backend (**2552 passed, 0 failed**) roda apenas contra SQLite descartável — ela sustenta o código do guard, não o runtime do servidor.

## Hardware

i3-10110U (2C/4T), 12 GB RAM, HDD 5400 rpm: **não declarado apto** para hospedagem contínua. Não foram medidos: estabilidade de longa duração, temperatura, I/O sustentado, SMART, consumo e tempo de recuperação após queda de energia.

## Prontidão

LAB-01/03/05 são evidência histórica, não runtime contínuo. O gate novo não foi executado com Docker nem com destino real off-host. Sem política de backup/retention, host adequado, monitoramento runtime, rollback e imagem identificada, Home Server **não está pronto para uso contínuo**. O daemon permaneceu indisponível nesta missão.
