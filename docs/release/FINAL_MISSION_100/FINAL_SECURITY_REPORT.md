# Final Security Report

## Alterações de segurança desta missão

- WhatsApp outbound exige `WA_SEND_MODE=live`; ausência ou valor desconhecido bloqueia texto/mídia antes do engine.
- O worker de campanhas não inicia nem processa destinatários em dry-run.
- **Nova camada:** `docker-compose.prod.yml` defaulta `WA_BROADCAST_ENABLED=false`. Um operador que libere `WA_SEND_MODE=live` para mensagens transacionais **não** ganha campanha em massa por acidente — ambas as chaves passam a ser explícitas. Nenhuma mensagem foi enviada nesta missão.
- Cobertura do chokepoint verificada por leitura: existe **uma única** implementação de `WhatsAppProvider` (`AccountInstance`), e os três pontos que emitem mensagem (rota manual, resposta automática em `incoming.ts`, worker de campanha em `broadcast.ts`) passam por `sendMessage`/`sendMedia`, onde o guard está. Não há provedor alternativo que fuja do guard.
- Compose de produção defaulta para `dry-run`; template e overlay do laboratório também forçam dry-run. O overlay fixa o modo mesmo que `.env.lab` seja alterado.
- Logs do bloqueio registram apenas id da conta e tipo (`text`/`media`), sem destinatário, texto, mídia ou credencial.
- Testes fake verificaram que o provider não recebe chamadas no modo bloqueado. WhatsApp suite: 162 passed.
- PostgreSQL sem Alembic head é recusado no boot; nenhuma migration implícita é executada.

## Evidência prévia e limites

SEC-01, SEC-01C e SEC-02 têm commits/testes históricos nos worktrees; esta missão não fez revisão adversarial completa de todas as rotas nem teste multitenant em runtime. Os testes WhatsApp SEC-02 foram incluídos na suite de 162.

OPS-01C documenta PII em artefatos versionados do repositório/histórico. Não inspecionei registros, não imprimi dados, não removi arquivos e não reescrevi histórico. Publicação/distribuição continua bloqueada até decisão do proprietário e tratamento aprovado.

## Não validado

- IDOR e autorização em todos os endpoints, SSRF, upload/path traversal, CORS/CSP, dependências e segredos em todos os worktrees.
- Dry-run em uma imagem/container de runtime; Docker daemon indisponível.
- Live mode com número de teste; não foi habilitado nem usado.
- Política LGPD formal de retenção/exclusão/incident response.

Não há aprovação de segurança para exposição à internet ou uso com dados reais. O modo outbound deve permanecer em dry-run.
