# Final Test Report

**Data:** 30/10/2026 · **Worktree:** `GasFlow-integration` ·
**Branch/HEAD:** `release/home-server-candidate` / `e989f70d029385fd974d3d7e5cb0426cbce670a5`

Ambiente dos execuções: Windows, Python 3.14.6, Node 24.17.0, sem Docker daemon,
sem `psql`/`pg_dump`, sem aparelho Android conectado.

## 1. Executado nesta continuação

| Área | Comando / artefato | Resultado | Limite da evidência |
| --- | --- | --- | --- |
| Backend — suíte completa | `python -m pytest -q -m "not live and not slow" -p no:cacheprovider` | **2552 passed, 15 skipped, 17 deselected, 0 failed** em 35m57s (exit 0) | Bancos temporários/fakes; 17 deselect = marcados `live`/`slow` (provider externo e E2E 10k); não tocou o SQLite operacional |
| Backend — Compose após hardening | `pytest tests/test_ops01b_homeserver_profile.py tests/test_prod_stack_config.py -q` | **48 passed** em 16,72s (exit 0) | `docker compose config` estático, sem daemon |
| Mobile — suíte completa | `npm test` (`node --test "tests/**/*.test.ts"`) | **86 passed, 0 failed** em 2,3s (exit 0) | Lógica pura em node; não executa JS em aparelho |
| Mobile — typecheck | `npx tsc -p tsconfig.json --noEmit` | **exit 0**, sem erros | — |
| Frontend — suíte | `npx vitest run --reporter=dot --pool=threads --maxWorkers=50%` | **88 arquivos / 500 testes passed**, exit 1 por **2 workers que não subiram** (`VisaoGeralSection.test.tsx`, `InviteSignupPage.test.tsx`) | Rerun dirigido desses 2 arquivos: **2 passed / 28 passed, exit 0**. Total: **90 arquivos / 528 testes, 0 falhas** |
| Frontend — build | `npm run build` (`tsc -b && vite build`) | **exit 0** — 2827 módulos, `dist/` gerado em 1m19s | Aviso de bundle >500 kB (performance, não erro) |
| Frontend — lint | `npm run lint` (eslint) | **exit 0**, zero problemas | — |
| Android — APK | `./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a` (JDK 17) | **BUILD SUCCESSFUL** em 12m21s (exit 0) — `app-release.apk`, 52.692.772 bytes, SHA-256 `f2c33ba4…557ef` | Somente ABI `arm64-v8a`; sem instalação em aparelho |
| APK — inspeção do artefato | varredura do `assets/index.android.bundle` e das `classes.dex` | `gasflow.driver.queue.v1`, `gasflow.driver.consent.v1`, `PersistentQueueStorage`, `hydrateOfflineQueue` presentes; `AsyncStoragePackage` presente em `classes.dex` | Prova de presença no pacote, não de comportamento em dispositivo |

### Testes novos adicionados nesta continuação

- `mobile/tests/queuePersistence.test.ts` — **9 casos**: restart com mesmo KV
  (replay uma única vez), estabilidade do `client_action_id` entre reinícios,
  ação `synced` nunca ressuscita, itens enfileirados antes do `hydrate()` não se
  perdem, `remove()`/prune persistem, snapshot corrompido não derruba o boot,
  falha de escrita não perde a fila em memória, `attach()` troca de KV,
  `clear()` no logout.
- `mobile/tests/session.test.ts` — **2 casos**: consentimento LGPD persistido
  sobrevive ao restart; payload corrompido não vira aceite (fail-closed).

## 2. Executado no checkpoint (preservado, não repetido)

| Área | Comando | Resultado |
| --- | --- | --- |
| Backend focado (migrações, seed/backfill, Desktop, seleção de dialeto, gate) | 6 arquivos de teste | **34 passed, 0 failed** em 284,04s |
| Gate de backup | `pytest tests/test_ops01d_deploy_gate.py -q` | **6 passed** (dry-run sem comandos; dump falhou ⇒ Alembic não executado; migração falhou ⇒ backup preservado e manifesto `migration-failed-or-partial`) |
| WhatsApp | `npm test` + `tsc --noEmit` | **162 passed, 0 failed, 0 skipped**; typecheck limpo |
| Compose lab | `pytest test_lab_disables_whatsapp_broadcast_and_critical_webhook` | **1 passed** |

Os 7 testes direcionados de sessão/offline/replay do checkpoint **fazem parte
dos 86 do app** e não são somados.

## 3. Não executado (com motivo)

| Item | Motivo |
| --- | --- |
| Suíte Electron do Desktop (`desktop`: `tsx --test tests/*.test.ts`) | `desktop/node_modules` ausente; instalar Electron (~100 MB) sem necessidade imediata foi evitado |
| `npm ci` do job mobile em runner limpo | Sem push/PR; só executado localmente o par `typecheck` + `test` |
| E2E Playwright (`npm run test:e2e`) | Exige backend + frontend subindo; nenhum serviço foi iniciado nesta missão |
| `pg_deploy_gate.py --execute`, `pg_dump`, `pg_restore`, migration real | Sem Docker daemon e sem `pg_dump`/`psql` no host |
| `docker compose up`, healthcheck, restart, volumes | Daemon Docker indisponível; iniciar Docker Desktop arriscaria subir a pilha existente sem autorização |
| Instalação/uso em aparelho Android | Nenhum aparelho conectado (`adb` sem dispositivo) |
| Testes `live` (17 deselect) e marcados `slow` | Exigem provider externo/credencial ou E2E de escala |
| Pareamento, envio ou recebimento WhatsApp real | Dependente de número de teste e autorização explícita — não autorizado |
| Migração SQLite → PostgreSQL com dados reais | Proibido sem cópia verificável e ambiente isolado |

## 4. Falhas observadas e como foram resolvidas

1. **Build Android — 1ª tentativa:** `autolinkLibrariesFromCommand: npx
   @react-native-community/cli config timed out` (11m52s). Causa: contenção de
   CPU (pytest + vitest + gradle simultâneos). `npx @react-native-community/cli
   config` sozinho leva **5,17s**; reexecução sozinho resolveu.
2. **Build Android — 2ª tentativa:** `:react-native-screens:buildCMakeRelWithDebInfo[armeabi-v7a]`
   em loop infinito de `Re-running CMake` (15m19s). Causa: o caminho
   `…/automação zap/` é corrompido para `automa??o` na cadeia de build (o
   próprio erro mostra o caminho quebrado). **Não é defeito do código.**
   Resolvido limitando a `-PreactNativeArchitectures=arm64-v8a` (12m21s, exit 0);
   registrado como pendência P1-7 no relatório de dependências.
3. **Frontend vitest — 1ª execução:** exit 1 por 2 workers que não iniciaram
   (`Timeout waiting for worker to respond`), não por teste reprovado. Rerun
   dirigido dos 2 arquivos: 28 testes, exit 0.
4. **Teste novo em `queuePersistence.test.ts`:** 1 falha — o erro estava no meu
   teste (usei `deliveryId` onde o `enqueue` gera `client_action_id`
   aleatório). Corrigido o teste; comportamento do código nunca foi alterado
   para fazer passar.

## 5. Números de teste desta missão

- **Total executado (todos os escopos, contando cada arquivo uma vez):**
  **3.166 testes** (backend 2552 + frontend 528 + mobile 86 + whatsapp 162).
- **Aprovados:** 3.166 · **Reprovados:** 0.
- **Ignorados/skipped:** 15 (backend).
- **Não executados:** 17 marcados `live`/`slow` (backend), suíte Electron,
  E2E Playwright, runtime Docker, gate real de backup, testes em aparelho.
- Nenhum teste foi desativado, enfraquecido ou removido para alterar números.

Não há teste reprovado escondido: as duas execuções com exit 1 tiveram a causa
investigada e reexecutada, e a falha final (worker de infraestrutura) consta
acima.
