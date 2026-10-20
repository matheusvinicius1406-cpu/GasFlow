# Checkpoint — 20/10/2026 (fim do expediente)

Estado do projeto ao fim de 20/10/2026. Retomar daqui em 21/10.

## Pronto e commitado

- **LGPD D8 (backend)**: `POST /clients/{codigo}/export` + `DELETE /clients/{codigo}/data`
  (`app/application/lgpd/use_cases.py`), anonimização idempotente em 13 tabelas
  preservando fiscal, auditoria `LGPD_*`, 10 testes novos (`backend/tests/test_lgpd.py`).
  Gates: ruff 0, mypy 0 (339 arquivos), vulture 0, **suíte completa 2323 passed / 30 skipped**.
  (Bug corrigido no caminho: o seed usava código `PED…` e quebrava o
  `proximo_codigo()` sequencial dos pedidos → contador numérico 990000+.)
- **v1.3.0 consolidada** no `CHANGELOG.md` (inclui bateria verde dos subsistemas).
- **Fase D da v1.2.0 fechada** (`release-v1.2.0-spec.md`, 20/20 checkboxes) com log real
  do updater; **G8 fechada** no `STATUS_E_PLANO.md` → 29 resolvidos / 17 externos.
- **Limpeza**: `_legado_raiz/`, `logs/`, caches e `node_modules` raiz removidos.
- **App do entregador — login destravado** (campo "Servidor" na tela de login):
  - `mobile/src/logic/serverConfig.ts` (novo): URL persistida no Keystore;
  - `App.tsx`: carrega a URL salva no boot + monta o `UpdateScreen` (antes nunca
    montado — o auto-update do APK nunca tinha checado versão em produção);
  - `wired.tsx`/`LoginScreen.tsx`: resolve a conexão com a URL digitada antes do login;
  - `gradle.properties`: `-Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8` — sem isso o
    AGP lia os artefatos UTF-8 do CMake com CP850 e o ninja morria com
    `chdir ... No such file` (repo em "automação zap"). **Build release verde em 9m36s.**
  - Gates mobile: typecheck limpo, **64/64 testes**.

## Amanhã (21/10) — falta fechar o teste no celular

1. Reconectar o celular via USB (saiu do adb ao fim do build) e `adb devices`
   (aceitar o diálogo de depuração USB no aparelho se pedir).
2. Instalar o APK novo: `adb install -r mobile\android\app\build\outputs\apk\release\app-release.apk`
   (assinado com a mesma keystore → instala por cima).
3. Garantir o túnel: `adb reverse tcp:8000 tcp:8000` (o desktop precisa estar aberto —
   backend embutido em `127.0.0.1:8000`, que é o que o celular alcança pelo túnel).
4. No app: **Servidor** `http://127.0.0.1:8000`, **Usuário** `edson`,
   **Senha** `MPEU-K4PY-CG84` (senha temporária criada hoje em `auth_users`,
   `driver_id=000001`, `must_change_password=true` → a tela de troca de senha
   deve aparecer; escolher senha nova e seguir para "Rota do Dia").
5. **Localização**: GPS já ligado (`location_mode=3`) e permissões concedidas via
   `adb shell pm grant`. Aguardar envios e conferir linhas novas em
   `driver_locations` no banco do desktop (`%APPDATA%\gasflow-desktop\gasflow.db`,
   driver 000001) e o ponto no mapa de rastreio ao vivo do desktop.
6. Registrar resultado no `release-v1.2.0-spec.md` (D4/D5) e no CHANGELOG se o fluxo fechar.

## Pendências/décisões levantadas hoje (não bloqueiam o teste)

- **Produção do app fora do USB**: o desktop embute o backend com `--host 127.0.0.1`
  (`desktop/src/main/index.ts:142`) — um celular fora do USB/túnel não alcança.
  Decidir: `0.0.0.0` + LAN, ou relay/URL pública (configuração por QR continua sendo
  a solução de produto; o campo de servidor é o fallback manual).
- `UpdateScreen` agora está montada — confirmar em produção que a checagem
  `GET /api/v1/mobile/version` aparece no log (valida D4 de verdade).
- `driver_sessions`/`driver_locations` do banco de produção estavam **zerados** até
  hoje: nenhum celular jamais conectou antes deste teste.
- D7 (validações V.1/V.2/V.3) segue 0/3 — precisa VM + celular real com credenciais.
