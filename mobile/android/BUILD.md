# Build Android (APK) — GasFlowDriver

> **Requisito de ambiente:** caminho **ASCII** (sem acentos/espaços) + JDK 17.
> O repo vive em `…\OneDrive\Desktop\automação zap\GasFlow` — o `ç` e o
> OneDrive corrompem o CMake/ninja do NDK (`ninja: fatal: chdir …`).
> `JAVA_HOME` do sistema aponta para o JDK 8; o build exige o 17
> (Temurin instalado em `C:\Program Files\Eclipse Adoptium`).

## Receita validada (2026-09-18)

```bash
# 1. Copiar o mobile/ para um caminho ASCII (robocopy preserva tudo;
#    exclui node_modules e artefatos — reinstalamos/geramos lá dentro)
robocopy "C:\Users\mathe\OneDrive\Desktop\AUTOMA~1\GasFlow\mobile" ^
         "C:\gflow\mobile" /E /MT:16 /XD node_modules .cxx build .gradle

# 2. Dependências
cd /c/gflow/mobile
npm ci --no-audit --no-fund

# 3. Build (JDK 17 no JAVA_HOME do comando)
cd android
JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-17.0.19.10-hotspot" \
  ./gradlew assembleDebug --no-daemon

# 4. Artefato
ls app/build/outputs/apk/debug/app-debug.apk   # ~107MB (universal, 4 ABIs)

# 5. Copiar o APK de volta para o repo (pasta é gitignored)
cp app/build/outputs/apk/debug/app-debug.apk \
   "C:\Users\mathe\OneDrive\Desktop\AUTOMA~1\GasFlow\mobile\android\app\build\outputs\apk\debug\"
```

## Notas

- **`react-native-screens` fixada em 4.4.0** — versões novas (4.28+)
  derrubam o codegen do RN 0.76 com
  `Unknown prop type "accessibilityContainerViewIsModal"`.
- **`newArchEnabled=false`** em `gradle.properties` — pela mesma limitação
  de caminho não-ASCII; reativar (Fabric/TurboModules) quando o repo
  migrar para um caminho ASCII definitivo.
- **Rebuild incremental**: repetir apenas o passo 3 no `C:\gflow`
  (sem recopiar) — Gradle cache em `android/.gradle` é local da cópia.
- Para release assinado: gerar keystore própria (o `debug.keystore` é só
  para debug) — ver https://reactnative.dev/docs/signed-apk-android.
- Instalar no aparelho: `adb install -r app-debug.apk` (depuração USB) ou
  copiar o APK para o telefone e abrir.
