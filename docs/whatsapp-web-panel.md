# WhatsApp Web Panel — Protótipo Híbrido (F0–F5)

**Data:** 2026-09-14
**Status:** implementado, **flag OFF por default** (`waWebPanel.enabled: false`).
**Regra de ouro:** o envio de mensagens continua **100% no Baileys**. Este painel
serve APENAS para pairing (QR), status e visibilidade operacional. Nenhuma
automação de DOM, nenhum envio via UI.

---

## 1. Arquitetura

```
┌─ Electron main ──────────────────────────────────────────────┐
│  wa-web-panel.ts                                             │
│  ├─ WebContentsView por conta (Electron 44)                  │
│  │    partition = persist:wa-web-<accountId>                 │
│  ├─ UA Chrome estável pinado (Chrome/128)                    │
│  ├─ Permissões: câmera/mic/geo/notificações NEGADAS          │
│  ├─ Healthcheck de PRESENÇA (15s, env WA_WEB_HEALTHCHECK_MS) │
│  │    → canvas do QR / header de chat / banner desconexão    │
│  └─ onStatus push → IPC "gasflow:wa-web-status"              │
└──────────────┬───────────────────────────────────────────────┘
               │ IPC (wa-web:statuses/show/bounds/hide/re-pair/close)
┌─ Preload ────▼───────────────────────────────────────────────┐
│  window.gasflow.waWeb* + onWaWebStatus                       │
└──────────────┬───────────────────────────────────────────────┘
┌─ React ──────▼───────────────────────────────────────────────┐
│  /whatsapp/web (guard whatsapp.read)                         │
│  Abas por conta + badges de estado + botões abrir/QR/fechar  │
│  Placeholder medido por ResizeObserver → bounds da view      │
└──────────────────────────────────────────────────────────────┘
```

- **WebContentsView** (não BrowserView deprecado, não `<webview>`, não `<iframe>`).
- **Uma view por conta; partições distintas** = duas contas coexistem em tabs.
  Duas views da **mesma** conta nunca são criadas (brigariam pelo socket).
- **Healthcheck de presença apenas** (`PRESENCE_SCRIPT`): booleans de
  elementos-chave, nunca scraping de conteúdo.
- **Permissões negadas** por default — notificações ficam só no Baileys
  (evita duplicação).

## 2. Feature flag (F5)

`settings.json` (userData do Electron):

```json
{ "waWebPanel": { "enabled": false } }
```

- **Default: `false`.** Com a flag off, `createPanelIfEnabled` retorna `null`:
  **nenhum** WebContentsView é instanciado (validado por teste cobrindo
  `webContents.getAllWebContents()` equivalente no harness).
- Os handlers IPC respondem `{ ok: false, disabled: true }` quando o painel
  não existe; a página React mostra o estado "desativado".

## 3. Como testar manualmente (3 passos por fase)

| Fase | Passos |
|---|---|
| **F0** — WA Web carrega | 1. `settings.json` → `"waWebPanel": { "enabled": true }` 2. Abrir `/whatsapp/web` → "Abrir painel" 3. **Critério:** QR aparece na área do placeholder. Se NÃO aparecer: bloqueio server-side novo — parar e reportar |
| **F1** — Shell | A moldura React (tabs, badges, botões) desenha em volta; view só sobre o placeholder |
| **F2** — Duas contas | 1. Abrir painel na tab "Principal" e parear a conta A 2. Trocar para "Secundária", abrir e parear a conta B 3. **Critério:** ambas ativas simultaneamente, sem interferência |
| **F3** — Status bridge | 1. No celular: WhatsApp → Dispositivos conectados → desconectar a conta da view 2. Observar a página em ≤5s: badge muda para "Desconectado"/"Aguardando QR" 3. **Critério:** a view mantém o estado real; o envio pelo Baileys não é afetado |
| **F4** — Persistência | 1. Fechar o GasFlow completamente 2. Reabrir e entrar em `/whatsapp/web` → "Abrir painel" 3. **Critério:** sessão preservada, sem re-scan de QR |
| **F5** — Flag off | 1. `"waWebPanel": { "enabled": false }` 2. Reabrir o app e navegar para `/whatsapp/web` 3. **Critério:** mensagem "desativado"; nenhuma view criada |

## 4. Backup e persistência (F4)

A sessão de cada conta fica no userData do Electron:

```
%APPDATA%/gasflow/Partitions/persist:wa-web-primary/   (ou <accountId>)
```

- **Incluir `Partitions/` no backup.** Se o restore não o incluir, o usuário
  re-escaneia o QR (uma vez) após restaurar.
- O `logout()` do Baileys NÃO apaga a sessão da view — são dispositivos
  independentes. Para desparear a view: botão "Fechar" + limpar a partição,
  ou deslogar pelo celular.

## 5. Expectativa de comportamento (documentar ao usuário)

Baileys (**device #1**) e a view WA Web (**device #2**) são **duas sessões
independentes** no telefone:

- Ambas aparecem em "Dispositivos conectados".
- Ambas recebem mensagens — **não é bug**.
- Se o Baileys cair: a view continua mostrando o estado real e permite agir
  (re-parear / ver QR). Se a view cair: o Baileys segue enviando — perde-se
  visibilidade, não capacidade.
- Notificações: default só no Baileys (evita duplicação).

## 6. Riscos conhecidos

| Risco | Mitigação |
|---|---|
| WA Web muda o DOM com frequência | Healthcheck lê apenas **presença** de elementos-chave (canvas/header/banner), nunca conteúdo |
| UA spoof quebra quando o Chrome sobe versão | UA **pinado** em Chrome/128 (`CHROME_USER_AGENT` em `wa-web-panel.ts`) — revisar trimestralmente |
| Sessão da view em userData fora do backup | Path documentado na seção 4; incluir `Partitions/` no fluxo de backup |
| Duplicação de notificações | Notificações negadas na view por default |
| Rate limit do WA para UA anômalo | Uma view por conta, sem automação, sem multi-login da mesma conta |

## 7. Testes automatizados

| Suite | Antes | Depois |
|---|---|---|
| Desktop (`npm test`) | 29 | **41** (12 novos: flag off, partições, 1 view por conta, bounds, permissões negadas, healthcheck de presença, timeout de logout de view) |
| Frontend (`vitest run`) | 189 | **194** (5 novos: desktop-only, flag off, tabs + push de status, abrir com bounds, re-parear/fechar) |

O módulo `whatsapp/src/` (Baileys + anti-ban) **não foi tocado** — diff só em
arquivos novos + IPC wiring + tela nova, conforme escopo.
