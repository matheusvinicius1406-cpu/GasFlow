# Prioritized Roadmap — AUDIT-01B

## P0 — dados e segurança antes de qualquer corte

| Ordem | Ação | Evidência da lacuna | Critério de aceite | Risco |
| --- | --- | --- | --- | --- |
| 1 | Desenvolver gate fail-closed de backup antes de Alembic/deploy | LAB-05 só prova restore fictício local; PENDENCIAS_BLOQUEANTES P1-8 registra migration no boot sem backup automático | Backup off-host identificado por hash/relatório; backup inválido/indisponível aborta antes da migration; teste prova a ordem backup→migration | Altíssimo: perda/corrupção de dados |
| 2 | Proteger e autorizar os dados da Marcos Gás | Nenhuma migração real; OPS-01C-A registra PII versionado no repositório | Política e dono aprovam cópia; nenhuma PII em logs/lab; inventário e reconciliação sem expor registros | Altíssimo: privacidade e integridade |
| 3 | Selecionar host adequado e destino de backup off-host | OPS-00B não recomenda o notebook para Home Server contínuo; sem prova de backup fora do host | Host/energia/armazenamento definidos; restore periódico e retenção fora do mesmo host | Alto: indisponibilidade/perda simultânea |
| 4 | Incorporar R-1 em imagem rastreável | Fonte corrigida e testada em PG descartável; imagem do lab era pré-correção e digest não foi registrado | Build/digest identificado contém R-1; gate em DB descartável e smoke aprovados | Alto: correção ausente em execução |
| 5 | Validar isolamento e migração da Marcos Gás em cópia autorizada | Rehearsal sintético não equivale a migrar clientes/pedidos/saldos | Antes/depois reconciliados, rollback ensaiado e autorização formal antes de janela | Altíssimo: perda de operação |

## P1 — fechar homologação sem risco à operação

| Ordem | Ação | Critério de aceite | Dependência |
| --- | --- | --- | --- |
| 6 | Completar LAB-04 WhatsApp | Parear somente número dedicado; sessão fica em volume lab; enviar/receber mensagem de prova; sem QR/segredo em documento | Operador e número de teste |
| 7 | Fechar LAB-06 | Registrar resultado dos gates, exceções e estado de runtime; todos os gates aprovados ou formalmente bloqueados | LAB-04 e checklist |
| 8 | Validar app Android em aparelho | Login, rota, GPS, tela bloqueada, offline/reconexão e conclusão verificados | APK e dispositivo de teste |
| 9 | Homologar fluxo da Marcos Gás com dados sintéticos | Pedido→estoque→entrega→financeiro reconciliados; perfis e limites de acesso aprovados | Host de homologação e P0 concluídos |

## P2 — operação e produto

- Provar alertas, logs e recuperação do host em runtime.
- Corrigir fila offline volátil, GPS apenas em primeiro plano e idempotência mobile/backend antes de operação de campo.
- Completar testes E2E e validação de desktop/mobile no hardware alvo.
- Avaliar domínio fixo, TLS, retenção e notificações conforme decisão de negócio.

## P3 — SaaS

- Provisionamento/convite, planos/cobrança e migração por tenant.
- Teste de isolamento multitenant em runtime, incluindo jobs, cache, arquivos, logs, backup e restore por empresa.
- Governança e observabilidade de plataforma após os gates da Marcos Gás.

## Sequência recomendada

1. Implementar e testar backup pré-migration fail-closed, sem tocar em banco operacional.
2. Definir host e backup off-host; registrar política de dados/PII.
3. Incorporar R-1 em imagem versionada e validá-la em ambiente descartável.
4. Concluir LAB-04 e LAB-06; manter o atual estado runtime como desconhecido até operador autorizar uma nova consulta/execução.
5. Ensaiar migração e fluxo comercial da Marcos Gás em cópia segura antes de qualquer decisão de corte.

## Conclusão

O próximo passo não é repetir LAB-01/03/05, já comprovados historicamente, nem expandir SaaS. É fechar a proteção de dados antes de migration/deploy, resolver a proveniência da imagem e completar os gates ainda abertos. Produção segue bloqueada.
