# GasFlow — Deploy do Aplicativo do Entregador

> **Worktree:** `GasFlow-integration` | **Data:** 20/10/2026 | **Status:** Release candidate Android + Windows assinados

O APK (`v1.1.0` - versionCode 1) e o Desktop (`v1.1.0` - build 1) estão **assinados, testados e prontos** para instalação. Este documento é o guia operacional.

> **Nota de recuperação (30/10/2026):** os `.md` desta pasta (não versionados
> no Git) foram apagados por um processo externo durante a execução de 30/10.
> Este arquivo foi **restaurado a partir da leitura feita nesta mesma
> execução**, preservando o conteúdo lido. Seções que não foram lidas na
> íntegra podem ter se perdido — ver o relatório
> [`RELATORIO-EXECUCAO-2026-10-30.md`](./RELATORIO-EXECUCAO-2026-10-30.md).

---

## APK Android — Instalação

### Build da release (para o build server)

```bash
cd GasFlow-integration/mobile/android
./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a
```

> O `build.gradle` só aponta pra keystore de release quando existe `android/keystore.properties` **e** o arquivo `.keystore` indicado — fora disso o build cai no fallback debug.

### Instalação (celular conectado via USB)

```bash
cd GasFlow-integration/mobile/android
adb devices                      # confirme que o aparelho aparece
adb install -r app/build/outputs/apk/release/app-release.apk
```

### Atualização sem perder dados (sideload)

- `adb install -r` é seguro: **preserva dados, sessão e configurações**.
- A instalação falha se a assinatura for diferente → nesse caso, instale por cima.
- O app detecta a nova versão e mostra o fluxo de atualização automático.

## Desktop Windows — Instalação

### Build da release

```powershell
cd GasFlow-integration/desktop
npm run build:win
# Saída: release/GasFlow-Setup-1.1.0.exe
```

### Instalação / Atualização

1. Feche o app antigo se estiver rodando.
2. Execute `GasFlow-Setup-1.1.0.exe`.
3. A atualização preserva configurações e sessão.

## Validación

- `npx tsc --noEmit` mobile: sem erros
- `npm test` mobile: `86 pass, 0 fail` (fila offline, sessão, rastreamento, lógica)
- Suíte de regressão do backend: `4839 passed, 0 failed`
- Android: APK release `v1.1.0` (versionCode 1), `minSdk 24`, `targetSdk 34`, `arm64-v8a`

**Execução de 30/10/2026 (MOBILE USB LAB 01):**

- Mobile: `npm test` → **101 pass, 0 fail**; `npx tsc --noEmit` → sem erros
  (fila offline com dono/identidade de sessão, durabilidade de gravação e
  consentimento LGPD)
- Desktop: `npm ci` (lockfile) + `npm run typecheck` + `npm test` → **153 pass, 0 fail**
- Backend (foco financeiro/estoque/pagamento/tenant/isolamento):
  **202 pass, 0 fail**
- Android: APK `v1.2.1` (versionCode 4) buildado e **instalado num aparelho físico**
  (Galaxy S10, Android 12, arm64-v8a) com dados preservados — ver
  [`ROTEIRO-DE-CAMPO-MOBILE.md`](./ROTEIRO-DE-CAMPO-MOBILE.md)

## Fluxo de atualização (in-app)

O `UpdateScreen` foi refatorado:
- URL configurável via `updates.json` (`github-release` / `direct-apk` / `disabled`)
- `?force=1` força download sem diálogo
- Check em background, sem travar a tela
- Erros são silenciosos em produção
- Botão "Atualizar" no canto inferior da Home

---

## Avisos conhecidos

### 1. Assinatura do APK é obrigatória para atualizar (bloqueia instalação)

O `build.gradle` só aponta pra keystore de release quando existe
`android/keystore.properties` **e** o arquivo `.keystore` indicado — fora
disso o build cai no fallback debug. Consequência real, aparelho físico:
um APK buildado sem a keystore **não atualiza** uma instalação release
(`INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match`) e a única
saída seria desinstalar, perdendo sessão, consentimento e fila offline do
usuário.

- Antes de buildar para instalar em aparelho: ter `keystore.properties` +
  keystore de release no lugar (ambos gitignorados, nunca commitados).
- Confira quem assinou com:
  `apksigner verify --print-certs app-release.apk`
- `keystore.properties` e `gasflow-release.keystore` são ignorados pelo
  `.gitignore` (`mobile/android/.gitignore:8-11`): quem tem a keystore no
  builda, quem não tem **não** pode empacotar release.

### 2. Splash quebrava o lançamento do app (CORRIGIDO em 30/10/2026)

`res/drawable{,-v24}/splash_screen.xml` usava
`<bitmap android:src="@mipmap/ic_launcher">`. Em API 26+ `ic_launcher` é
**adaptive-icon** (XML de vetores), que o `<bitmap>` não infla. Resultado no
aparelho real (Android 12):

```
FATAL EXCEPTION: main — Process: com.gasflowdriver
android.content.res.Resources$NotFoundException:
  Drawable com.gasflowdriver:drawable/splash_screen with resource ID #0x7f0800bc
Caused by: Binary XML file line #8: <bitmap> requires a valid 'src' attribute
```

Correção: `<item android:drawable="@mipmap/ic_launcher" android:gravity="center" />`
(resolve em qualquer API). **O defeito já existia na v1.2.0 instalada**
(mesmo `res/ck.xml` nos dois APKs) — ou seja, o app que o usuário tinha
instalado já não abria. Corrigido, rebuildado e revalidado (app abre,
processo estável, buffer de crash vazio).

### 3. Build Android exige JDK 17 por sessão

O `JAVA_HOME` global desta máquina aponta para o JDK 8, e o AGP falha com
`Dependency requires at least JVM runtime version 11`. Antes de cada build:

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot"
```

### 4. Teste de campo completo ainda não foi executado

Instalação e abertura foram validadas no aparelho físico, mas **login, fila
offline, GPS, permissões e logout continuam PENDENTES** — ver
[`ROTEIRO-DE-CAMPO-MOBILE.md`](./ROTEIRO-DE-CAMPO-MOBILE.md).

### 5. Empacotamento Docker/Windows não foi tentado em 30/10/2026

O daemon Docker estava parado e os artifacts do Home Server
(`docker compose ls`, listagem de containers, imagem, `.env.lab`, rede/portas)
exigem subir o Docker Desktop — o que pode **auto-iniciar containers
existentes** (políticas de restart). Por isso ficou **pendente de autorização
explícita**: nada foi iniciado, parado ou removido. Os artefatos de deploy
(`docker-compose.prod.yml`, `docker-compose.homeserver.lab.yml`,
`deploy/home-server/`) já estão no repositório; validar o empacotamento real é
o próximo passo quando houver autorização.

### 6. Como o celular enxerga o backend local

O app Android não alcança o `localhost` do PC por USB sozinho. A ponte
comprovada em 30/10 é o túnel reverso do ADB:

```powershell
adb reverse tcp:8010 tcp:8010    # celular usa http://127.0.0.1:8010
adb reverse --list               # UsbFfs tcp:8010 tcp:8010
```

Para o laboratório completo (backend descartável na porta 8010, dados
fictícios, seed e smoke test), use
[`scripts/mobile-lab/`](../../scripts/mobile-lab/README.md).

### 7. Pastas de docs não versionadas podem ser apagadas por processos externos

`docs/mobile/` **não está no Git** (arquivos novos, `git status` → `??`).
Em 30/10/2026 os arquivos `MOBILE-DEPLOY.md`, `MOBILE-QA-22.md` e
`MOBILE-RELEASE-CHECKLIST.md` desapareceram do disco sem nenhuma operação de
remoção nossa — e não há cópia em outro worktree nem no OneDrive. **Proteja
esses arquivos**: versione-os ou faça backup regular, senão qualquer limpeza
externa (sync, outro agente, `git clean`) os perde.

## Laboratório USB (sem tocar em produção)

`scripts/mobile-lab/` sobe um backend **descartável** em `127.0.0.1:8010` com
banco SQLite próprio, WhatsApp desabilitado, sem Redis e com segredos gerados
fora do repositório — além de seed e smoke test do app. É o ambiente para
testes de campo sem risco operacional. Instruções em
[`scripts/mobile-lab/README.md`](../../scripts/mobile-lab/README.md).
