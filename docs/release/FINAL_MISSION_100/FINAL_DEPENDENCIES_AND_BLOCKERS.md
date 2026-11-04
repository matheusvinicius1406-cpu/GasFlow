# Final Dependencies and Blockers

Atualizado em 31/10/2026 após a continuação da missão.

## Atualização de 31/10/2026

**Tratado:** `CVE-2026-111181` (`body-parser` 2.3.0 transitivo via `express`).
Correção por atualização para `2.4.0` **dentro da faixa `^2.3.0`** que o `express`
já declara — sem `overrides`, sem mudar `package.json`. PR **#80**, branch
`fix/security-body-parser-cve`. Todos os checks verdes, **incluindo Trivy
(passou em 3m44s)**. Validado localmente: 106 testes WhatsApp, typecheck, lint e
build limpos.

**Confirmado ainda bloqueado (físico/humano, não é código):**

- **Dispositivo Android.** `adb` disponível mas **nenhum aparelho anexado**
  (`List of devices` vazio). Instalação e teste em aparelho seguem impossíveis
  nesta máquina. Detalhes em `docs/mobile/MOBILE_USB_LAB_01_REPORT.md`.
- **Docker daemon parado.** Etapa de lab (backup off-host real, imagem R-1 com
  digest) continua bloqueada até o Docker Desktop subir.
- **Backup off-host real**, PII versionado, migração Marcos Gás, aceite
  financeiro e de isolamento de tenant: inalterados, dependem de decisão humana.

## P0

1. **Backup realmente off-host.** O gate existe e é testado com doubles
   (6 testes), mas nunca rodou com `pg_dump` real nem com destino fora do host.
   Sem isso, migrations/deploy continuam bloqueados. Dependência: escolher o
   dispositivo/share externo e autorizar ambiente descartável com Docker.
2. **Imagem R-1 com digest.** A correção está em `init_db.py` e nos testes, mas
   nenhuma imagem foi reconstruída nesta missão (daemon Docker indisponível).
   Exige: build da imagem, tag + digest registrados, bootstrap em PostgreSQL
   descartável, healthcheck e logs. O teste do lab anterior era pré-R-1.
3. **Host para operação contínuo.** Notebook i3-10110U / 12 GB / HDD não é
   recomendado para Home Server contínuo; falta critério mensurável de
   estabilidade, armazenamento e energia.
4. **PII versionado.** Histórico Git e árvore contêm material pessoal
   (OPS-01C). Exige decisão do proprietário. Não lido, exposto, apagado nem
   reescrito nesta missão; publicação continua bloqueada.
5. **Migração da Marcos Gás.** Só em cópia verificável, ambiente isolado,
   com reconciliação antes/depois e plano de rollback. Nunca no banco
   operacional.
6. **Integridade financeira.** A reversão de estoque é idempotente por
   referência (código lido e coberto), mas estornos compensatórios,
   conciliação e fechamento de caixa não têm aceite de negócio.
7. **Isolamento de tenant.** Testes de dois tenants sintéticos passaram na
   suíte completa (`2552 passed`), mas não houve aceite operacional por
   superfície (jobs, arquivos, cache, relatórios, WhatsApp, backup).

## P1

1. **Dispositivo Android.** O APK existe e foi analisado, mas não foi
   instalado/rodado em aparelho: GPS em background (P1-2), tela bloqueada,
   prova de entrega e comportamento offline real seguem **pendentes de
   hardware**. Teste de campo = pendente, não concluído.
2. **Número WhatsApp de teste + autorização.** Sem pareamento, envio ou
   recebimento real. Requer ação humana explícita.
3. **LAB-04 e LAB-06.** Evidência histórica, não revalidada com o runtime de
   hoje.
4. **Provisionamento SaaS.** Onboarding, convites, suspensão/encerramento com
   retenção, planos e cobrança não implementados como produto.
5. **E2E do operador.** Ciclo cliente→pedido→pagamento→estoque→entrega→
   relatório não executado de ponta a ponta nesta sessão.
6. **Destino off-host, retenção, alertas, RPO/RTO aceitos.**
7. **Caminho do repositório com acento.** O build Android só compilou o ABI
   `arm64-v8a`: o CMake do `react-native-screens` entra em loop para
   `armeabi-v7a` porque o caminho `automação zap` é corrompido para `automa??o`
   na cadeia de build. Correção real = repositório em caminho ASCII ou
   `react-native-architectures` fixado; documentado no FINAL_RUNBOOK.

## Concluídos nesta continuação

- **P1-1 (fila offline volátil) — CORRIGIDO** e provado com testes de
  restart/replay; código dentro do APK.
- **P1-3 (sem job mobile no CI) — CORRIGIDO**; job `mobile` no workflow.
- Divergência `client_action_id` / `idempotency_key` — corrigida no adapter
  mobile e coberta por teste de replay sem duplicidade.

## Dependências não contratadas

Nenhum VPS, domínio, certificado, PSP, serviço comercial ou API paga foi
contratado. Orçamento mantido em R$ 0,00. As dependências acima exigem
decisão, hardware, credencial ou ação humana — não código.
