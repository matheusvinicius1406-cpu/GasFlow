# GasFlow Driver — app Android do entregador

App React Native 0.76 (bare, sem Expo) do entregador. Ele autentica pela auth
**principal** do backend (`/auth/login`), é forçado a trocar a senha no primeiro
acesso e opera só nas rotas do namespace `/driver/*`.

- **Login / sessão:** `/auth/login` (access JWT + refresh) — token em
  `react-native-keychain` (Keystore/Keychain), nunca em `AsyncStorage` puro.
- **Gate de senha pendente:** HTTP `403` + header
  `X-GasFlow-Password-Change-Required: 1`, e WebSocket fechando `4003`. Ambos
  levam à tela de troca de senha como **estado de app**, não erro genérico.
- **Realtime:** WebSocket `/ws` no canal `driver:{driver_id}` com backoff.
- **Rastreio:** gate por rota (B2) + cadência do `/driver/me` + fila offline
  (kind `location`, dedupe por `recorded_at`, retenção de 7 dias).

> Detalhes da receita de build (caminho ASCII, JDK 17, `react-native-screens`
> 4.4.0, `newArchEnabled=false`): **`android/BUILD.md`**.

## ⚠️ Bloqueio conhecido — GPS em segundo plano (Fase 5)

A lib indicada, **`@ikolvi/tracelet@0.1.0-alpha.1`**, **não compila** no projeto
Android:

- `:ikolvi_tracelet:compileReleaseKotlin` → `Unresolved reference: core`
  (o pacote publicado não inclui o submódulo `core` que o módulo Android importa);
- o manifest da lib traz um `<service>` **fora** do `<application>` → AAPT
  rejeita (`unexpected element <service> found in <manifest>`);
- exige `minSdk 26` (o app usa 24).

Por isso a dependência **não** está instalada: o rastreio hoje é o de primeiro
plano (`@react-native-community/geolocation`), **atrás da costura**
`src/logic/backgroundTracking.ts`. O adaptador já implementa config
(`distanceFilter` ~20 m, precisão HIGH, foreground service, lote 50, retenção
7 dias), geofencing (~150 m) e **fallback** quando a lib não está disponível —
coberto por testes com um fake.

Para ligar o background quando houver uma versão utilizável:

1. reinstalar a lib (`npm i @ikolvi/tracelet@<versão>`);
2. subir `minSdkVersion` para 26 em `android/build.gradle` (API 26 = Android 8);
3. em `src/containers/wired.tsx`, trocar `tracelet: null` por
   `tracelet: Tracelet` (import de `@ikolvi/tracelet`).

Candidatas alternativas (open source, sem conta/API key) devem ser avaliadas
antes de trocar a costura.

## Build

Pré-requisitos: **JDK 17** e caminho do projeto **ASCII** (sem acentos/espaços).
O repo vive em `…\OneDrive\Desktop\automação zap\…`, o que quebra o NDK/CMake —
por isso o build roda numa cópia em `C:\gflow`. Passo a passo completo em
`android/BUILD.md`.

```bash
# cópia ASCII (exclui node_modules e artefatos)
robocopy "C:\Users\mathe\OneDrive\Desktop\AUTOMA~1\GasFlow\mobile" ^
         "C:\gflow\mobile" /E /MT:16 /XD node_modules .cxx build .gradle
cd /c/gflow/mobile && npm ci --no-audit --no-fund
cd android
JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-17.0.19.10-hotspot" \
  ./gradlew assembleRelease --no-daemon
```

Artefato: `android/app/build/outputs/apk/release/app-release.apk` (~53 MB).
O APK fica **fora do git** (`mobile/.gitignore` → `android/app/build/`).

## Assinatura e custódia da keystore

O `release` lê `android/keystore.properties` (gitignored). Sem o arquivo, o
build cai na chave de debug — nunca falha por falta de assinatura local.

```properties
storeFile=gasflow-release.keystore
storePassword=<SEGREDO>
keyAlias=gasflow
keyPassword=<SEGREDO>
```

| Item | Valor |
|---|---|
| Alias | `gasflow` |
| Arquivo | `android/app/gasflow-release.keystore` (gitignored) |
| SHA-256 | `47:10:07:3C:B7:B4:ED:72:22:9D:07:05:A4:92:72:CA:78:C3:F9:0A:98:4A:D7:61:E5:E8:01:BF:0B:6B:D7:0C` |
| SHA-1 | `CA:C6:91:BA:15:B7:85:52:2E:25:E0:9D:C8:C5:04:09:80:E1:78:69` |

Regenerar (só se a keystore for perdida — **exige novo app id para publicar**):

```bash
keytool -genkeypair -v -keystore android/app/gasflow-release.keystore \
  -alias gasflow -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=GasFlow Driver, O=GasFlow, C=BR"
```

**Custódia:** guarde a keystore **e** a senha num cofre (1Password/Bitwarden/
cofre corporativo). Perder a keystore = não conseguir atualizar um app já
publicado. **Rotação:** gerar keystore nova e republicar só é possível com
novo `applicationId`; para trocar a senha sem trocar a chave, use
`keytool -storepasswd` e atualize `keystore.properties`. **Nunca** commitar
`.keystore` nem `keystore.properties` (ambos já estão no `.gitignore`).

## Ambientes

A base URL **nunca** é hardcoded em produção: é resolvida em runtime pela tela
de conexão (`src/logic/connection.ts`), com modos `lan` / `cloud` / `offline`.
Em `dev`/`staging`/`prod` muda apenas o endereço informado pelo operador —
o mesmo binário serve os três.

## Distribuição

1. **Sideload / link direto** (recomendado para frota pequena): publicar o
   `app-release.apk` num link interno e instalar com
   `adb install -r app-release.apk` (o aparelho precisa permitir "fontes
   desconhecidas").
2. **Google Play — trilha de teste interno**: enviar o mesmo APK (ou um AAB)
   pela trilha interna; exige a keystore acima e o `applicationId` definitivo.
3. **MDM** (frota gerenciada): distribuir via Intune/Microsoft Endpoint etc.

## Teste manual end-to-end

1. Admin cria o entregador → anota a **senha temporária** (aparece uma vez).
2. Instalar o `app-release.apk` num **aparelho real**.
3. Login com a temporária → o app **deve** cair na tela de troca de senha.
4. Trocar a senha → entra nas telas do entregador.
5. Verificar no backend que o WebSocket conectou em `driver:{driver_id}`.
6. Fechar e reabrir o app → a sessão persiste (keychain).
7. Logout → volta ao login.
8. Desativar o entregador no admin → a próxima request retorna 401/403 e o app
   limpa a sessão.

## Testes e typecheck

```bash
npm test          # node --test (lógica pura — sem device)
npm run typecheck # tsc --noEmit
```
