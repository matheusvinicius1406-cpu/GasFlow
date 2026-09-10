# Auto-Update — GasFlow Desktop

Fluxo completo: **VS Code → commit → push (tag) → GitHub Actions builda → GitHub Releases publica → app instalado atualiza sozinho.**

```
git push --tags ──► GitHub Actions (release.yml)
                      │  npm ci → npm run build:win -- --publish always
                      ▼
                GitHub Releases (exe + latest.yml)
                      │  electron-updater checa (15s após abrir + a cada 6h)
                      ▼
                App baixa → badge no canto → "Reiniciar e instalar"
```

## Configuração (já aplicada no repo)

| Item | Onde |
|---|---|
| `electron-updater` em `dependencies` | `desktop/package.json` |
| `publish: github (matheusvinicius1406-cpu/GasFlow, releaseType: release)` | `desktop/electron-builder.yml` (fonte única — um campo `build` no package.json **sobrescreveria** este arquivo e quebraria o empacotamento) |
| `updater.js` (setupAutoUpdate + IPC `update:check/install/state`) | `desktop/dist/main/updater.js` |
| Preload expõe `window.gasflowUpdater` | `desktop/dist/preload/index.js` |
| UI: badge + progresso + botão instalar | `frontend/src/components/UpdateNotifier.tsx` |
| Workflow de release | `.github/workflows/release.yml` |
| `build:win` script | `desktop/package.json` |

**Uma vez no GitHub (manual):** Settings → Actions → General → Workflow permissions → **Read and write permissions** (sem isso o Actions não publica a release).

## Fluxo do desenvolvedor

```bash
# 1. Mudanças + testes
cd backend && python -m pytest -q        # (ou o pacote que mexeu)

# 2. Commit
git add . && git commit -m "feat: X"

# 3. Bump de versão (escolha UM — cria o commit + tag sozinho)
cd desktop
npm version patch    # 1.1.1 — bugfix
# npm version minor  # 1.2.0 — feature
# npm version major  # 2.0.0 — breaking

# 4. Push (commit + tag)
cd ..
git push && git push --tags

# 5. Aguardar ~10 min (Actions) → release publicada
# 6. Apps instalados detectam em até 6h (ou 15s após abrir)
```

**Nunca crie a tag manualmente** — `npm version` garante tag = `package.json` = `latest.yml`. Tag dessincronizada faz o updater ignorar a release.

## Rollback (downgrade)

- `allowDowngrade = false`: apps já atualizados **não voltam sozinhos**.
- Para corrigir uma release quebrada: revert do commit → `npm version patch` (ex.: 1.1.2 com código da 1.1.0) → push. **Sempre suba o número.**
- Urgência: editar/deletar a release no GitHub impede *novos* downloads, mas não desfaz o que já atualizou.

## Canal beta (opcional)

`settings.json` do app: `"updateChannel": "beta"` → updater usa `channel: beta` + `allowPrerelease: true` e passa a aceitar releases marcadas como **pre-release** no GitHub (ex.: `v1.2.0-beta.1`). Default (`latest`) ignora prereleases.

## Assinatura de código (futuro)

Sem certificado, o auto-update funciona; só a **primeira instalação** aciona o SmartScreen. Com certificado (EV ~$200/ano ou SignPath): adicionar `CSC_LINK` + `CSC_KEY_PASSWORD` como secrets — o electron-builder assina sozinho no CI.

## Troubleshooting

| Sintoma | Onde olhar | Causa comum |
|---|---|---|
| Badge nunca aparece | `%APPDATA%\gasflow-desktop\logs\main.log` → `updater.*` | Sem release publicada; offline; `releaseType: draft` |
| `updater.check.fail` 404 | GitHub Releases | Nenhuma release `latest` publicada ainda |
| `latest.yml` ausente no release | Actions log | Build falhou antes do publish; `publish always` sem `GH_TOKEN` |
| Baixa mas não instala | UI | Instalar é manual (botão) por design; `autoInstallOnAppQuit` cobre quem só fecha |
| Versão da release ≠ app | `desktop/package.json` | Tag criada manualmente sem `npm version` |

## Validação (checklist)

- [ ] Push da tag → Actions verde → Release com `.exe` + `latest.yml`
- [ ] App v1.1.0 numa máquina limpa → abre → 15s → badge "v1.1.1 disponível"
- [ ] Progresso chega a 100% → botão "Reiniciar e instalar" → app reabre em v1.1.1
- [ ] `main.log` mostra `updater.available` → `updater.ready`
