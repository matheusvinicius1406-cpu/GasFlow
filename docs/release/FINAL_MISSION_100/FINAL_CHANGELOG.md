# Final Changelog — 2026-10-30

## Fase 1 (checkpoint da missão)

- Alterado boot PostgreSQL para exigir schema no Alembic head e recusar migration/create_all implícitos.
- Removido `alembic upgrade head` do comando de boot do backend no Compose de produção; mantida migration explícita no overlay do banco descartável do lab.
- Adicionado `pg_deploy_gate.py`: dump custom para destino confirmado off-host, magic/hash/manifesto, `pg_restore --list`, migration somente depois, estado de falha/partial, validação do head posterior. Não inicia serviços.
- Adicionados testes fake para ordem/abort/preservação do backup.
- WhatsApp outbound fail-closed: modo `live` explícito; default e laboratório `dry-run`; worker de campanhas bloqueado em dry-run.
- Adicionados testes negativos com engine fake; atualizado Compose e templates; sem QR, sessão ou envio real.
- Atualizadas notas de Home Server e pendência P1-8.
- Criados 13 relatórios `FINAL_*` em `docs/release/FINAL_MISSION_100/`.
- Corrigida a divergência de contrato `client_action_id` → `idempotency_key` em `mobile/src/logic/api.ts`.

## Fase 2 (continuação em 30/10/2026)

- **Fila offline persistente (fecha P1-1):** novo
  `mobile/src/logic/queuePersistence.ts` — `PersistentQueueStorage` mantém a
  leitura síncrona para a UI e espelha o snapshot no AsyncStorage a cada mutação,
  com escritas serializadas, `remove()` real, merge no boot que nunca ressuscita
  ação `synced` e relatório de erro de hidratação/escrita. `wired.tsx` expõe
  `hydrateOfflineQueue`/`clearOfflineQueue`/`offlineQueuePersistenceState`;
  `App.tsx` reidrata **antes** do replay e o logout explícito descarta a fila.
- **Consentimento LGPD persistente:** `createAsyncStorageConsentStorage` em
  `session.ts` (payload corrompido ⇒ null ⇒ gate repede o pedido, fail-closed);
  `App.tsx` deixa de usar storage em memória.
- **Dependência:** `@react-native-async-storage/async-storage@2.1.0` (MIT,
  orçamento zero) em `mobile/package.json`.
- **CI (fecha P1-3):** job `mobile` em `.github/workflows/ci.yml` (Node 24,
  `npm ci`, `npm run typecheck`, `npm test`).
- **Fail-closed de campanha:** `docker-compose.prod.yml` passa a defaultar
  `WA_BROADCAST_ENABLED=false`; campanha em massa exige duas chaves explícitas
  (`WA_SEND_MODE=live` **e** `WA_BROADCAST_ENABLED=true`). Nenhuma mensagem foi
  enviada; nenhuma sessão WhatsApp foi aberta.
- **Evidência de suíte:** backend completo executado pela primeira vez nesta
  missão (`2552 passed, 15 skipped, 17 deselected, 0 failed`).
- **APK:** primeiro build release do app do entregador
  (`app-release.apk`, arm64-v8a, 52.692.772 bytes) com o código de persistência
  verificado dentro do bundle e da `classes.dex`.
- Relatórios `FINAL_*` atualizados com a nova evidência e novos percentuais.

## Não executado nesta missão

Sem `commit`, `push`, `merge`, `deploy`, migration, `docker compose down -v`,
remoção de volume, pareamento/envio WhatsApp ou alteração de dados da Marcos
Gás. Nenhuma liberação de campanha ou envio real foi realizada.

Sem reescrita de histórico Git, sem remoção de PII e sem publicação de artefato.
