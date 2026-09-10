# GasFlow Desktop

App desktop **Electron** que é um **container do GasFlow original**: a mesma
interface React do navegador, servida pelo próprio backend FastAPI, com todos
os serviços rodando localmente na máquina.

```
┌──────────────────────────── Electron ─────────────────────────────┐
│  Janela = frontend React original    │  Main process              │
│  (mesmo design do navegador)         │  ─ BackendBridge → uvicorn │
│  carregado de                        │    (FastAPI + SQLite local)│
│  http://127.0.0.1:8000               │  ─ WhatsAppBridge → Baileys│
│                                      │  ─ AgentBridge → agente    │
│                                      │  ─ AssistantEngine (IA)    │
│                                      │  ─ AiService  → Ollama     │
└───────────────────────────────────────────────────────────────────┘
         │                      │                        │
         ▼                      ▼                        ▼
   Backend FastAPI        WhatsApp (Baileys)      Agente de integração
   + frontend + APIs      porta 3101 (local)      sync site → GasFlow
         │
         ▼
   Ollama (11434) — IA local
```

## Como funciona

- O main process sobe **3 subprocessos** na ordem: backend → WhatsApp → agente
  (falha de um não derruba a janela).
- O **backend FastAPI** serve o frontend React original na raiz e as APIs sob
  `/api` (env `FRONTEND_DIST` — o mesmo contrato do proxy do vite). Banco
  **SQLite** local em `%APPDATA%/gasflow-desktop/gasflow.db` — sem PostgreSQL.
- A janela carrega `http://127.0.0.1:8000`: login `admin`, senha em
  `settings.json → backendAdminPassword` (gerada na primeira execução).
- O **assistente IA** (auto-resposta de WhatsApp via Ollama) roda no main
  process, controlado por `settings.json → waAutoReply`.
- Notificações nativas do Windows para sync e status do WhatsApp quando a
  janela está em segundo plano.

## Requisitos

- **Node.js 20+** (para desenvolver) — o usuário final não precisa (Electron
  embute o Node 22 para os subprocessos).
- **Python 3.11+** com as deps do backend (o backend roda via `python -m
  uvicorn`; se existir `backend/.venv`, ele é usado automaticamente).
  Empacotar o backend com PyInstaller é o próximo passo para um instalador
  100% autônomo.
- **Ollama** com modelo de texto (`ollama pull llama3.2`) — usado pelo
  assistente e pelo pipeline de IA do backend (`AI_PROVIDER=ollama`).

## Desenvolvimento

```bash
# 1. builds prévios (uma vez, e a cada mudança)
cd agent && npm install && npm run build && cd ..
cd whatsapp && npm install && npm run build && cd ..
cd frontend && npm install && npm run build && cd ..
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cd ..
cd desktop && npm install

# 2. rodar
npm start
```

Scripts:

| Script | O que faz |
| --- | --- |
| `npm run typecheck` | tsc do main process |
| `npm test` | testes unitários (ai-service, agent-bridge, wa, assistant) |
| `npm run build` | typecheck + tsc |
| `npm start` | sobe tudo e abre a janela |
| `npm run dist` | build de tudo (agent, whatsapp, frontend, desktop) + NSIS |

## Configuração (`%APPDATA%/gasflow-desktop/settings.json`)

| Chave | Default | Descrição |
| --- | --- | --- |
| `gasflowApiUrl` | `http://localhost:8000` | Porta do backend local (a janela usa essa) |
| `gasflowToken` | — | Token de serviço (agente → backend, permissão `integration.write`) |
| `backendAdminPassword` | gerada | Login admin do frontend (`admin` / senha) |
| `ollamaBaseUrl` | `http://localhost:11434` | Ollama |
| `ollamaTextModel` / `ollamaVisionModel` | `llama3.2` / `llama3.2-vision` | Modelos |
| `waPort` | `3101` | Porta do serviço WhatsApp local |
| `waApiKey` | gerada | Chave local que protege a API do WhatsApp |
| `waEnabled` | `true` | Se `false`, o serviço WhatsApp **não sobe** no boot (log `wa.bridge.skipped`) |
| `waAutoReply` | `false` | Assistente IA responde novas mensagens sozinho |

### Segurança e anti-ban do serviço WhatsApp (efeitos recentes)

- **Auth timing-safe + produção travada**: com `ENVIRONMENT=production` e
  `MARCOS_GAS_API_KEY` vazia, o serviço WhatsApp **não sobe** (fail no boot).
  No desktop a chave é gerada automaticamente (`waApiKey`), então o cenário
  afeta apenas deployments manuais/docker.
- **`mediaPath` restrito a allowlist**: envios de mídia por caminho só
  funcionam dentro de `WA_UPLOADS_DIR` (default `<cwd do serviço>/uploads`).
  Fora disso → `400 MEDIA_PATH_INVALID`.
- **Anti-ban em toda a API de envio**: `/messages`, `/send` e automações
  respeitam caps por minuto/hora e cooldown por destinatário — bloqueio
  retorna `429` com `Retry-After`. O assistente IA do desktop não duplica
  resposta: só fala quando o backend ainda não respondeu àquela mensagem.

## Auto-update (electron-updater + GitHub Releases)

Fluxo completo de atualização do app instalado:

1. **Bump de versão** (`desktop/package.json` e `package-lock.json`) + commit.
2. **Push de tag** `v<versão>` → o workflow `release.yml` builda o instalador
   no GitHub Actions e publica na Release correspondente (com `latest.yml` e
   `*.blockmap`).
3. **Apps instalados detectam**: 15s após abrir (e a cada 6h) o
   `electron-updater` consulta o canal (default `latest`) no GitHub Releases.
4. **Download automático** (`autoDownload=true`); o usuário vê o progresso e
   clica em **"Reiniciar e instalar"** — ou instala ao fechar o app
   (`autoInstallOnAppQuit=true`).

Logs para diagnosticar: `updater.checking` / `updater.available` /
`updater.ready` / `updater.error` (arquivo de log em `%APPDATA%/gasflow-desktop/logs/`).

- `allowDowngrade=false`: versão anterior nunca é instalada por cima.
- **Rollback**: publique uma release nova com versão maior — o updater não
  rebaixa versão sozinho.
- Dev (app não empacotado): auto-update desligado de propósito (log
  `app não empacotado — auto-update desligado (dev)`).

## Migration de schema (SQLite local)

O banco do usuário (`%APPDATA%/gasflow-desktop/gasflow.db`) é criado por
`Base.metadata.create_all()` — que **não altera tabelas existentes**. Para
evolutivas de schema, `init_db._ensure_sqlite_columns()` compara o schema real
(`PRAGMA table_info`) com os models e adiciona colunas faltantes via
`ALTER TABLE ... ADD COLUMN` (idempotente, não perde dados). A versão aplicada
fica registrada em `_schema_version` (tabela de 1 linha, upsert idempotente).

## Sobre `desktop/dist/` versionado
<arg_value><b88a6f17>> [histórico] Os fontes do main process (`src/main/*.ts`) não estão nesta
> árvore — apenas o `dist/` compilado é versionado. A restauração dos fontes
> está em andamento na branch `refactor/desktop-sources` (Onda 4 da auditoria).

O Electron carrega `dist/main/index.js` direto — alterações no main process
são feitas hoje no próprio `dist/` (com os testes de fumaça em `desktop/tests/`
cobrindo updater, config e preload). `npm run typecheck` usa um placeholder em
`src/` até os fontes serem restaurados.

## Arquitetura / decisões

- **Sem interface própria**: o Electron só orquestra processos e exibe o
  frontend original — qualquer melhoria no `frontend/` aparece no desktop.
- **Backend como subprocesso**: `BackendBridge` espera `/health` (até 90s) e
  injeta o ambiente (`DATABASE_URL` sqlite, `FRONTEND_DIST`,
  `WHATSAPP_SERVICE_URL`, `ADMIN_PASSWORD`, `AI_PROVIDER=ollama`).
- **WhatsApp como subprocesso HTTP** (Baileys, sem Chromium): o desktop fala
  REST com ele e conecta o loop de mensagens recebidas → backend → IA.
- **Agente como subprocesso IPC** (`agent/dist/index.js --ipc`, JSON-lines).
- **Modo embutido do backend é aditivo**: sem `FRONTEND_DIST`, docker/nginx
  funcionam exatamente como antes.

## Empacotamento (Windows)

`npm run dist` gera `release/GasFlow Desktop Setup <versão>.exe` (NSIS).
Embutidos: `resources/frontend` (React), `resources/agent`, `resources/whatsapp`.

> ⚠️ **Windows sem privilégio de symlink**: se o build falhar em
> `winCodeSign` (`Cannot create symbolic link`), habilite o **Modo
> Desenvolvedor** ou popule o cache manualmente:
>
> ```bash
> CACHE="$LOCALAPPDATA/electron-builder/Cache/winCodeSign"
> # use qualquer pasta temp <n> já extraída (fica no cache após uma tentativa)
> cp -r "$CACHE"/<n> "$CACHE/winCodeSign-2.6.0"
> cd "$CACHE/winCodeSign-2.6.0/darwin/10.12/lib"
> cp -f libcrypto.1.0.0.dylib libcrypto.dylib   # symlinks viram cópias —
> cp -f libssl.1.0.0.dylib libssl.dylib         # só são usados no macOS
> ```

## Limitações conhecidas

- **Backend precisa de Python na máquina** nesta versão (PyInstaller na
  roadmap para instalador totalmente autônomo).
- WhatsApp: use um número dedicado — automação não-oficial tem risco de
  banimento; use com moderação.
- WhatsApp Web audio: depende do whisper instalado na máquina (usado pelo
  backend para transcrição).
