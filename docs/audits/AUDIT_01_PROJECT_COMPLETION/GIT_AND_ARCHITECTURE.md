# Git and Architecture

> AUDIT-01B: resultados operacionais datados de 28/10 em `docs/integration/LAB_01_04_RUNTIME_REPORT.md` prevalecem sobre as notas anteriores de pré-homologação. Esta cronologia não afirma que o daemon continua ativo.

## Estado real dos worktrees

A auditoria confirmou quatro worktrees no diretório do projeto:

- `GasFlow`: branch `sec-02-whatsapp-gateway`, `HEAD 213c187`, 4 commits além de `origin/main`, com um arquivo não rastreado `docs/OPS_00_HOME_SERVER_READINESS.md`.
- `GasFlow-freebuff`: branch `parallel/freebuff-mobile-p0`, `HEAD 92e3d50`, 7 commits além de `origin/main`.
- `GasFlow-opencode`: branch `parallel/opencode-data`, `HEAD d256ac6`, 10 commits além de `origin/main`.
- `GasFlow-integration`: branch `release/home-server-candidate`, `HEAD e989f70`, 15 commits além de `origin/main`.

### Candidato mais atualizado e seguro

O candidato mais atualizado e mais relevante para a auditoria operacional é `GasFlow-integration`, por três razões:

1. Tem a branch mais avançada em preparação de Home Server e laboratório.
2. A linha de commits inclui a correção de porta e de dialeto do banco.
3. Sinaliza uma base de integração para a próxima etapa de homologação.

A ressalva é importante: a branch local está com modifications pendentes e arquivos não rastreados; ela ainda não é uma versão final de release pronta para merge ou operação. Consulta somente leitura em 30/10 confirmou branch `release/home-server-candidate`, HEAD `e989f70` e daemon Docker indisponível. `docker ps` falhou ao abrir o named pipe do Docker Desktop; estado de runtime atual, portanto, não observável.

## Cronologia reconciliada

- **26/10 — INT-01:** integração concluída e classificada como candidata à homologação, não à produção. 3.489 testes passaram; Docker up, migrations contra banco real, restore real, dispositivo e WhatsApp real não fizeram parte daquela frente.
- **27/10 — OPS-01C-A:** plano estático e gates definidos; naquele momento o daemon estava indisponível e LAB-01 ainda não havia começado. Esse era um retrato anterior, não o estado após a homologação.
- **28/10 — LAB-01/02/03:** execução runtime posterior documenta cinco containers saudáveis, PostgreSQL/Redis, backend/frontend e nove smoke checks aprovados.
- **28/10 — LAB-05:** dump PostgreSQL custom do banco fictício restaurado independentemente e comparado. LAB-04 permaneceu sem pareamento/envio; LAB-06 ficou pendente.
- **28/10 — R-1:** `init_db.py` corrigido no working tree e testado com testes e PostgreSQL descartável real. O relatório declara explicitamente que a imagem do lab ainda contém o código pré-correção.
- **30/10 — consulta desta reconciliação:** daemon não responde; nenhum serviço foi iniciado. Resultados de 28/10 permanecem evidência histórica, não prova de runtime atual.

O último commit em HEAD é `e989f70` (27/10). R-1 e outros itens estão como alterações locais/não rastreadas, não como commit incorporado. O digest da imagem em execução não foi registrado; não é possível determinar qual commit exato originou a imagem anterior.

## Arquitetura real do projeto

A estrutura do monorepo continua coerente com a documentação, especialmente na arquitetura de domínio com FastAPI, frontend React/TypeScript, mobile React Native, WhatsApp em Node.js e infraestrutura em Docker/PostgreSQL/Redis.

### Backend

- `backend/app` com camadas de domínio/aplicação/infraestrutura/apresentação.
- Modelos e migrações onde há prova de evolução de schema.
- `init_db.py` foi corrigido para distinguir SQLite e PostgreSQL, evitando a execução de migrações SQLite em PostgreSQL.

### Frontend

- SPA em React, com dashboard, clientes, pedidos e integradores.
- Há documentação e testes de integridade e UI, embora não seja possível afirmar operação real sem ambiente vivo.

### WhatsApp

- Gateway em Node.js com autenticação e hardening.
- Há testes específicos e documentação de segurança e rotas de infraestrutura.

### Home Server

- Compose separado para produção e laboratório isolado.
- O plano de laboratório foi documentado e a correção de porta e DSN foi registrada em código e testes.

## Divergências importantes

- `GasFlow` está mais recente em segurança de gateway e hardening de auth, mas não é a linha mais avançada em infraestrutura de laboratórios.
- `GasFlow-freebuff` se concentra em correção de mobile e home server, mas ainda não é a base mais integradora.
- `GasFlow-opencode` segue em dados e backup/restore, mas menos alinhado com a operação principal do painel e do serviço WhatsApp.
- `GasFlow-integration` concentra a linha de operação e laboratório, exigindo disciplina de merge e validação antes de qualquer go-live.

## Conclusão arquitetural

A arquitetura do monorepo é coerente e há homologação real de laboratório comprovada. O que continua faltando é aceite completo dos gates, incorporação rastreável de R-1 à imagem, execução de WhatsApp com número de teste, validação física do app e controles de backup/migração próprios da Marcos Gás. A auditoria OPS-00B também conclui que o notebook com HDD mecânico e CPU de 2 núcleos não é recomendado para Home Server completo em produção contínua.
