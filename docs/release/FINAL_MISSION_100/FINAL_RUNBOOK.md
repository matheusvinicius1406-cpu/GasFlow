# Final Runbook — preparação segura

Este é um runbook de staging; **não executar em produção ou no banco da Marcos Gás** sem autorização específica.

## Antes de qualquer runtime

1. Confirmar worktree `GasFlow-integration`, branch e HEAD; preservar modificações existentes.
2. Obter autorização para iniciar Docker manualmente; verificar somente leitura containers, volumes, redes e portas antes de comandos mutáveis.
3. Usar projeto e volumes descartáveis exclusivos; `.env.lab` com segredos fictícios fortes, sem credenciais da operação.
4. Confirmar WhatsApp `WA_SEND_MODE=dry-run`, `WA_BROADCAST_ENABLED=false`, webhook vazio e nenhum número real pareado.
5. Confirmar que imagem tem digest/build documentado e contém as correções revisadas.

## Inspecionar o gate sem executar

```powershell
python scripts/home-server/data/pg_deploy_gate.py `
  --project gasflow-hs-lab `
  --compose-file docker-compose.prod.yml `
  --compose-file docker-compose.homeserver.yml `
  --compose-file docker-compose.homeserver.lab.yml `
  --env-file deploy/home-server/.env.lab `
  --backup-dir E:\GasFlow-Backups `
  --database-name gasflow_lab
```

Sem `--execute`, o gate é dry-run e não chama Docker. O destino deve existir e estar num filesystem diferente do checkout; para provar off-host, o operador precisa confirmar o dispositivo/share e usar `--confirm-off-host`.

## Execução em staging descartável

Só após aprovação humana, ambiente descartável pronto e destino externo confirmado, adicionar `--execute --confirm-off-host`. O gate não inicia serviços: exige PostgreSQL/Redis já disponíveis; faz `pg_dump`, verifica formato/hash/manifesto e `pg_restore --list`; então migra e verifica Alembic head. Qualquer falha interrompe ou marca resultado parcial e preserva o backup.

Depois, verificar healthcheck, smoke e dados sintéticos. Não usar este procedimento para cutover real sem plano separado e assinatura do proprietário. O gate não inicia nem para serviços.

## Compilar o app do entregador (APK)

No worktree de integração, com JDK 17 em `JAVA_HOME` (o `JAVA_HOME` do
sistema pode apontar para JDK 8):

```bash
cd mobile/android
JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-17.0.19.10-hotspot" \
  ./gradlew assembleRelease --no-daemon -PreactNativeArchitectures=arm64-v8a
```

Resultado verificado em 30/10/2026: `app-release.apk` em
`mobile/android/app/build/outputs/apk/release/` (52.692.772 bytes,
SHA-256 `f2c33ba4818b1eb78eb6e2246fa8bf124e141dc6034b5b8003f37e1b6df557ef`).

**Limite conhecido (P1-7):** a build **só** funciona para `arm64-v8a`. Para
`armeabi-v7a` (e para qualquer ABI que compile `react-native-screens`) o CMake
entra em loop de `Re-running CMake` porque o caminho do repositório
(`automação zap`) é corrompido para `automa??o` na cadeia de build do Windows.
Correções reais, na ordem de preferência: (a) mover o repositório para um
caminho 100% ASCII; (b) fixar `reactNativeArchitectures` no `gradle.properties`.
Não é defeito do código do GasFlow.

O APK gerado não é assinado com keystore próprio (o `android/keystore.properties`
não existe): cai na assinatura de debug — suficiente para instalar em aparelho
de teste, não para distribuição. Instalar com
`adb install -r mobile/android/app/build/outputs/apk/release/app-release.apk`.

## Rodar os testes locais

```bash
cd backend && python -m pytest -q -m "not live and not slow"   # ~36 min
cd mobile   && npm test && npm run typecheck                     # ~2 s
cd frontend && npm test && npm run build && npm run lint
```
