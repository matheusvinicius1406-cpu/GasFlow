# MOBILE USB LAB 01 — Relatório de instalação e homologação física

**Data:** 31/10/2026
**Status:** **BLOQUEADO — nenhum aparelho conectado.** Nenhum resultado físico foi simulado.

---

## 1. Estado do host

| Item | Resultado |
|---|---|
| `adb` | Android Debug Bridge 1.0.41 (platform-tools 37.0.0) — instalado |
| `adb devices -l` | lista **vazia** (nenhum dispositivo em `device`/`unauthorized`) |
| Java | OpenJDK 17.0.19 (Temurin) |
| Gradle wrapper | presente em `mobile/android/gradlew` |
| Backend de laboratório | não iniciado nesta etapa (depende do aparelho para o teste) |

Conclusão: a instalação via USB **não foi executada** porque não há dispositivo anexado ao host.
Não há como produzir evidência de `Success`, package ID, versão instalada ou inicialização sem o
aparelho. Os itens abaixo ficam prontos para execução imediata quando o celular for conectado.

## 2. APK — divergência com o histórico (importante)

O relatório anterior citava `app-release.apk` com **52.692.772 bytes** e
SHA-256 `f2c33ba4818b1eb78eb6e2246fa8bf124e141dc6034b5b8003f37e1b6df557ef`.
Os arquivos presentes no disco **não correspondem** a esse hash:

| Arquivo | Bytes | SHA-256 |
|---|---|---|
| `GasFlow/mobile/android/app/build/outputs/apk/release/app-release.apk` | 52.836.098 | `eb0cdb9739bfb8bd0f6b0f6e6769e245e97ab5ef60dd401822fe2fab366c3673` |
| `GasFlow-integration/mobile/android/app/build/outputs/apk/release/app-release.apk` | 52.695.120 | `fe21486d1518bcc63aec0737b2aadba7d0ce0329ea3b1aee16a46de5a8aa0838` |

Consequência: o artefato histórico foi substituído/regenerado e **não pode ser citado como evidência**.
Para homologar, gere um APK novo a partir da branch que será integrada e registre o hash resultante.

## 3. Procedimento exato (executar com o celular conectado)

```powershell
# 1. Detectar e caracterizar o aparelho
adb devices -l
adb shell getprop ro.product.manufacturer
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.product.cpu.abi
adb shell df /data

# 2. Conferir o artefato
Get-FileHash .\mobile\android\app\build\outputs\apk\release\app-release.apk -Algorithm SHA256
# package ID esperado: br.com.gasflow.driver (conferir no AndroidManifest)

# 3. Instalar preservando dados (sem uninstall/pm clear)
adb -s <SERIAL> install -r "CAMINHO\app-release.apk"

# 4. Comprovar
adb -s <SERIAL> shell dumpsys package <PACKAGE_ID> | Select-String versionName
adb -s <SERIAL> shell monkey -p <PACKAGE_ID> -c android.intent.category.LAUNCHER 1
```

## 4. Backend de laboratório (isolado, nunca o operacional)

- Porta exclusiva `8010` (não `127.0.0.1:8000`, que pode pertencer ao backend operacional).
- Banco sintético + tenant fictício `gasflow_lab`; WhatsApp `WA_SEND_MODE=dry-run`.
- Scripts prontos em `scripts/mobile-lab/` (`start_lab_backend.ps1`, `seed_lab_data.py`,
  `verify_lab_api.py`, `stop_lab_backend.ps1`).
- Ponte USB: `adb -s <SERIAL> reverse tcp:8010 tcp:8010`.

## 5. Perfil fictício e entregas sintéticas

Perfil: **Entregador Teste** / `MOTORISTA-LAB-001` / tenant `GasFlow Laboratório` / papel DRIVER.
Credencial criada pelo mecanismo oficial (`seed_lab_data.py`), entregue **apenas localmente**, nunca
em documento ou commit. Entregas sintéticas: 2 de P13, 2 de água 20 L, 1 em andamento.

## 6. Checklist de homologação (pendente de execução)

- [ ] Inicialização sem crash (splash/`Resources$NotFoundException` resolvido no PR #79)
- [ ] Login e identificação do motorista (`/driver/me`)
- [ ] Lista e detalhe de entregas
- [ ] Aceite → início → navegação → atualização de status → conclusão
- [ ] Confirmação no backend (status e idempotência)
- [ ] Permissões de localização e GPS em primeiro plano
- [ ] GPS em segundo plano / tela bloqueada (P1-2 — não aprovar só com tela aberta)
- [ ] Câmera e comprovante com foto sintética
- [ ] Offline: ação → API indisponível → persistência → fechar app → reabrir → sync único
- [ ] Replay sem duplicidade (uma única baixa por `idempotency_key`)

## 7. Riscos

| Risco | Observação |
|---|---|
| APK não assinado com a keystore correta | `android/keystore.properties` é ignorado pelo Git; sem ele o release não assina |
| `adb reverse` mascarar indisponibilidade de rede | o teste offline deve derrubar **a API**, não o Wi-Fi |
| Dados operacionais | usar somente `gasflow_lab` sintético; nunca o banco real da Marcos Gás |
