# Final Rollback Plan

## Limite

Nenhum rollback ou restore foi executado nesta missão. O plano abaixo é para staging descartável e requer revisão antes de qualquer uso operacional.

## Falha antes da migration

- Manter o dump custom e manifesto/hash no destino externo.
- Não iniciar Alembic se qualquer validação do backup falhar.
- Diagnosticar em staging; não apagar o artefato de evidência.

## Falha durante migration

- O gate registra `migration-failed-or-partial`, preserva o dump e aborta.
- Não executar downgrade automaticamente nem tentar reparar banco de produção.
- Em staging, restaurar para um banco novo e isolado; verificar head, schema, constraints e contagens sintéticas.

## Restore de versão anterior

1. Isolar o ambiente e impedir writers.
2. Confirmar origem/hash/manifesto/versão de PostgreSQL e compatibilidade da imagem anterior.
3. Restaurar em database/volume novo; nunca sobrescrever a única cópia.
4. Verificar integrity, tabelas, índices, constraints, contagens e fluxos sintéticos.
5. Comparar a aplicação anterior contra o schema restaurado.
6. Só trocar tráfego depois de aceite humano; preservar a instância original até aceite.

## Requisitos para completar o plano

RPO/RTO formal, cópia off-host, retenção, teste periódico, comunicação ao operador e runbook de recuperação de host ainda precisam ser definidos. Este plano não foi ensaiado.
