# Achados por área — Desktop/Electron (main compilado, sem fontes)

## D-1 · 🔴 Fontes do main process não existem — só `dist/` compilado

**Severidade:** 🔴 P0 (risco de sustentação) · **Arquivo:** `desktop/src/` (apenas `placeholder.ts`)

**Evidência:** `ls desktop/src/` → placeholder.ts; `desktop/dist/main/` tem 12 módulos reais (backend-bridge, wa-bridge, updater…); os `.map` não têm `sourcesContent`.

**Impacto:** cada mudança no app (como o auto-update desta semana) é feita **editando JS compilado à mão** — sem typecheck real, sem revisão diffs legível. Um `npm run build` mal configurado pode apagar o main real (quase aconteceu — daí o placeholder).

**Ação:** reescrever `desktop/src/main/*.ts` a partir do comportamento do `dist/` (o arquivo está pequeno: 269 linhas + módulos pequenos). É o caminho para restaurar `tsc` de verdade e eliminar o placeholder.

## D-2 · 🔴 Ponte IPC dormente — preload nunca foi carregado

**Severidade:** 🔴 P0 (para o auto-update)/🟠 P1 (resto) · **Arquivo:** `dist/main/index.js:211`

**Evidência:**
```
webPreferences: { contextIsolation: true, nodeIntegration: false }   // sem preload!
grep ipcMain dist/main/*.js → 0 ocorrências (nenhum handler registrado)
dist/preload/index.js expõe window.gasflow (settings, wa, agent, convs…) que NUNCA responde
```

**Impacto:** o frontend React dentro do Electron nunca teve acesso à ponte (`window.gasflow` é undefined no renderer). Toda a camada de settings/QR/conversas via IPC **nunca funcionou** — o app funcionava porque o frontend fala HTTP direto com o backend. O `UpdateNotifier` desta semana dependeria dessa ponte.

**Ação (aplicada no dist durante a sessão de auto-update, pendente de validação):** `preload:` no webPreferences + `setRendererSender` + `registerUpdateIpc()`/`setupAutoUpdate()` no `did-finish-load`. Correção definitiva exige D-1.

## D-3 · 🟠 Auto-update: integração feita no dist, não validada em release

**Severidade:** 🟠 P1 · **Evidência:** `dist/main/updater.js` (novo, sintaxe OK), `electron-updater 6.8.9` em dependencies, `publish:` no builder.yml + package.json; `desktop/release/` **sem `latest.yml`** — o build local atual não gera o manifesto que o updater consome.

**Ação:** rodar um build completo pós-config de publish e conferir `latest.yml` no output; o primeiro E2E real só acontece com a primeira release publicada via CI (workflow abaixo).

## D-4 · 🟡 `desktop/tests/` vazio

**Evidência:** `npm test` → 0 testes, exit 0 (verde falso).

**Ação:** mover lógica pura (loadSettings/generateKey) para módulos testáveis e cobrir; ou remover o script até existir teste.

## D-5 · 🟡 `waEnabled: false` ignorado no boot

**Evidência:** settings.json do app instalado tem `waEnabled: false`, mas `ensureWaBridge().start()` roda incondicionalmente (`index.js`, bloco whenReady).

**Ação:** respeitar o flag no main process (ou removê-lo da UI) — usuário acha que desligou o WhatsApp e o serviço continua rodando.
