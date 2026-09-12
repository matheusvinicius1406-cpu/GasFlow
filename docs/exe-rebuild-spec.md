# Spec — Rebuild do Instalador GasFlow v1.1.2 + Abertura do App

**Data:** 11/09/2026
**Pedido original:** "o arquivo .exe já foi corrigido com todas essas atualizações? se ainda não vamos atualizar e abrir..."
**Status:** ✅ Spec fechada via entrevista (4 rodadas de ask_user). **Nenhuma linha de código alterada ainda** — este documento é o plano aprovado.

---

## 1. Resposta à pergunta original

**Não — o .exe NÃO está atualizado.** Estado verificado em 11/09/2026:

| Artefato | Caminho | Estado |
|---|---|---|
| Backend empacotado (PyInstaller, 56 MB) | `backend/dist/gasflow-backend.exe` | ⚠️ **Desatualizado** — compilado em **10/09 19:42**, ANTES de todas as correções de 11/09 (falhas críticas de IA/WhatsApp `b24fd63`, B904 `cd9f6a4`, backup de migration `d397a97`, puppeteer/CI `d7637eb`/`c99a7a0`, Onda 4 `3224009`) |
| Instalador do desktop (NSIS) | `desktop/release/` | ❌ **Inexistente** — pasta vazia (limpa por `rebuild.ps1` na sessão anterior) |

**Detalhe crítico do pipeline:** o script `build:win` do desktop **não recompila** o exe do backend — ele apenas copia `../backend/dist/gasflow-backend.exe` via `extraResources` do `electron-builder.yml`. Ou seja, rodar só o build do instalador embutiria o backend **velho** no app. O PyInstaller precisa rodar antes, manualmente (no CI isso é o step "Build bundled backend" do `release.yml`).

Também verificado: `desktop/release/win-unpacked/GasFlow Desktop.exe` (o exe do Electron) também não existe — o instalador completo resolve ambos.

---

## 2. Decisões do usuário (entrevista)

| # | Pergunta | Decisão |
|---|---|---|
| 1 | Escopo do artefato | **Instalador completo** (recompila backend PyInstaller + gera Setup NSIS) |
| 2 | Como abrir | **Instalar via Setup** (testa o instalador de verdade: atalhos, desinstalador) |
| 3 | Versão | **Bump para 1.1.2** no `desktop/package.json` |
| 4 | PyInstaller | **Ambos**: pinar no `requirements.txt` do backend **e** instalar agora |
| 5 | Publicação | **Tag `v1.1.2` + release via CI** (`release.yml` publica no GitHub Releases → auto-updater distribui aos clientes) |
| 6 | Processos rodando | **Matar antes de buildar** (node, gasflow-backend, GasFlow Desktop — como o `kill_and_rebuild.ps1` já faz) para evitar EBUSY/EPERM |
| 7 | Alcance do rebuild | **Completo**: backend exe (PyInstaller), desktop TS, agent, whatsapp e frontend dist — nada embutido defasado |
| 8 | Caminho OneDrive | **Builda no lugar** (`C:\Users\mathe\OneDrive\Desktop\automação zap\GasFlow`) + garantir `.gitignore` dos artefatos (build/, dist/ do backend, release/ do desktop) |
| 9 | Bump de versão | **Só desktop** (1.1.1 → 1.1.2). frontend/agent/whatsapp mantêm as versões deles |
| 10 | Assinatura | **Sem certificado Authenticode** — SmartScreen mostrará aviso nativo; usuário clica "Mais informações → Executar assim mesmo" (mesmo comportamento da 1.1.1) |
| 11 | Release notes | **Changelog curado em PT-BR** (não auto-gerado) |
| 12 | Gate pré-tag | **Suíte completa verde** antes de criar a tag (pytest backend, frontend, whatsapp, desktop + smoke do instalador local) |
| 13 | Conflito do gate de assinatura no CI | **Remover o step "Require Authenticode signature"** do `release.yml` (sem cert, ele quebraria a release e nada seria publicado) |
| 14 | Secrets CSC no CI | **Deixar como está** — sem `WINDOWS_CODESIGN_CERTIFICATE_*`, electron-builder 26 publica o exe cru (é o que o `electron-builder.yml` já assume desde `642680e`) |

---

## 3. Descobertas da investigação (insumos da spec)

### 3.1 Arquitetura do app empacotado
- Electron (container) → spawn do `resources/backend/gasflow-backend.exe` (uvicorn/FastAPI) → janela carrega `http://127.0.0.1:<porta>` servido pelo FastAPI com o React embutido (`FRONTEND_DIST`).
- `desktop/src/main/index.ts` (`resolvePython()`): em `app.isPackaged`, usa `resources/backend/gasflow-backend.exe`; em dev, venv local ou `python -m uvicorn`.
- Env injetado pelo Electron (`ensureBackend()`): `DATABASE_URL` (sqlite em `userData/gasflow.db`), `ADMIN_PASSWORD` (= `settings.backendAdminPassword`, gerado na 1ª execução e gravado em `LOGIN.txt`), `FRONTEND_DIST`, `WHATSAPP_SERVICE_URL/KEY`, `AI_PROVIDER=ollama`, `ENVIRONMENT=production`.
- Bridges embutidos como recursos: `agent/dist/index.js`, `whatsapp/dist/server.js`, `frontend/dist/` — todos precisam estar buildados (escolha #7).
- `waEnabled` (`config.ts`, Bloco B): controla se o waBridge sobe no boot (default `true`).

### 3.2 Pipeline de release (`release.yml`, trigger: tag `v*`)
1. Checkout → Node 20 → Python 3.12 (cache pip via `backend/requirements.txt`)
2. `pip install -r requirements.txt pyinstaller` → `pyinstaller --clean --noconfirm gasflow-backend.spec` (backend exe é regenerado no CI)
3. `npm ci` desktop + `npm ci --prefix ../agent|../whatsapp|../frontend`
4. `npm run build:win` (compila TS desktop + dists dos 3 siblings + electron-builder --win)
5. ~~"Require Authenticode signature"~~ → **a remover** (decisão #13)
6. `electron-builder --win --publish always` com `GH_TOKEN` → GitHub Releases (`releaseType: release`, não-draft → visível ao auto-updater)
7. Upload de artefato backup (exe + `latest.yml`, 30 dias)

### 3.3 Contradição resolvida (o achado principal)
`4173ffa` ("valida assinatura antes de publicar") adicionou um step que faz a release **falhar** se `Get-AuthenticodeSignature` não retornar `Valid`. Como não há certificado (decisão #10/#14), a tag `v1.1.2` publicaria **nada**. O `electron-builder.yml` já foi ajustado em `642680e` (remoção do `signAndEditExecutable`), mas o **gate do CI ficou órfão**. Solução escolhida: remover o step inteiro do `release.yml` (sem alternativa condicional — usuário escolheu remoção simples), com comentário no YAML explicando como reativar quando houver certificado.

### 3.4 PyInstaller
- `gasflow-backend.spec`: onefile, entrypoint `desktop_entry.py` (uvicorn + argparse `--host/--port`), `hiddenimports = collect_submodules("app") + collect_submodules("uvicorn")`, `console=True`, UPX on.
- PyInstaller **não instalado** na máquina local (verificado). Entrará no `requirements.txt` (pinado, ex. `pyinstaller==6.10.0`) + `pip install` imediato — isso também deixa o step do CI determinístico (ele hoje instala `pyinstaller` solto; após o pin, ambos usam a mesma versão).

### 3.5 Riscos conhecidos
| Risco | Mitigação na spec |
|---|---|
| OneDrive sync churn durante build (node_modules, build/, dist/) | Decisão #8: builda no lugar; garantir `.gitignore` cobrindo `backend/build/`, `backend/dist/`, `desktop/release/`; artefatos ficam fora do git (OneDrive ainda sincroniza, aceito pelo usuário) |
| Arquivo travado por processo em execução | Decisão #6: matar `node`, `gasflow-backend`, `GasFlow Desktop` antes de buildar |
| `pyinstaller` ausente | Fase 1 instala + pina |
| Backend embutido desatualizado | Fase 2 regenera o exe ANTES do electron-builder (ordem obrigatória) |
| Gate de assinatura quebrando a release | Fase 4 remove o step do `release.yml` |
| SmartScreen no instalador não-assinado | Aceito (decisão #10); documentado nas release notes |
| Suíte backend falhou com ADMIN_PASSWORD≠conftest em sessão anterior | Na validação usar exatamente o default do conftest (`ADMIN_PASSWORD=test_password_123` via `setdefault`) — não sobrescrever o env |

---

## 4. Plano de execução (a implementar após aprovação)

### Fase 0 — Pré-flight
1. `git status` limpo; confirmar branch (`main` ou `refactor/desktop-sources` — ver §6).
2. Encerrar processos: `node`, `gasflow-backend`, `GasFlow Desktop` (estilo `kill_and_rebuild.ps1`).
3. Limpar `desktop/release/` e `backend/build/` + `backend/dist/` (rebuild limpo).
4. Conferir `.gitignore`: `backend/build/`, `backend/dist/`, `desktop/release/`, `*.backups/` (do novo backup de migration) — adicionar o que faltar (decisão #8).

### Fase 1 — Versão + PyInstaller
1. `desktop/package.json`: `"version": "1.1.1"` → `"1.1.2"` (só desktop — decisão #9) + `npm install` para sync da lockfile.
2. Adicionar `pyinstaller==6.10.0` (ou versão vigente) ao `backend/requirements.txt` e `pip install` local.

### Fase 2 — Rebuild completo (ordem importa)
1. **Backend exe:** `cd backend && pyinstaller --clean --noconfirm gasflow-backend.spec` → valida que `dist/gasflow-backend.exe` tem timestamp novo (o teste de saúde é a Fase 3).
2. **Dists dos siblings:** `npm run build --prefix agent`, `--prefix whatsapp`, `--prefix frontend`.
3. **Desktop TS:** `cd desktop && npm run build` (recompila `dist/main|preload` das fontes TS da Onda 4).
4. **Instalador:** `npx electron-builder --win` → gera `desktop/release/GasFlow Desktop Setup 1.1.2.exe` + `win-unpacked/`.
   - Atalho equivalente: `npm run build:win` (mas NÃO recompila o backend exe — por isso o passo 1 é separado e obrigatório).

### Fase 3 — Validação (gate da decisão #12)
1. **Suítes:** backend pytest (com env default do conftest), ruff, mypy; frontend vitest+tsc; whatsapp typecheck+testes; desktop typecheck+testes.
2. **Smoke do pacote:** abrir `win-unpacked/GasFlow Desktop.exe` uma vez (backend sobe, `/health` responde, login admin com senha do `LOGIN.txt`).
3. **Instalação via Setup** (decisão #2): rodar o `Setup 1.1.2.exe` → atalhos criados → app abre → desinstalador funcional.
4. **Smoke do backend novo:** executar `backend/dist/gasflow-backend.exe --port 8001` isolado e conferir `/health` (prova que o exe regenerado funciona sem o wrapper do Electron).

### Fase 4 — Preparação da release (commits em `main`)
1. **`release.yml`: remover o step "Require Authenticode signature"** + comentário: reativar quando `WINDOWS_CODESIGN_CERTIFICATE_*` existir (decisão #13).
2. `.gitignore` das pastas de artefato (se faltou na Fase 0).
3. Commit único coeso: `chore(release): v1.1.2 — bump, pyinstaller pinado, gate de assinatura removido`.
4. Push `main` (usuário já autorizou push neste fluxo).

### Fase 5 — Tag + release via CI
1. Criar release notes **curadas em PT-BR** (decisão #11) — seções:
   - 🔒 **Segurança** (relatório 11/09): webhook Cloud API agora responde (IA ativa); `permission_level` server-side em `/ai/chat`; permissão por tool enforcement; handlers das 15 tools; typo `order_coordinates`; binding de `arguments_hash`; fila de aprovações em Redis; B904/except silenciosos.
   - 💾 **Banco:** `_schema_version` + migração genérica + **backup automático** antes de migrar (Bloco A).
   - 🖥️ **Desktop (Onda 4):** main process reescrito em TypeScript; electron 44 + electron-builder 26 (**0 vulnerabilidades npm**); bridge paths em packaged; boot resiliente; `waEnabled`.
   - 📦 **Release:** PyInstaller pinado; gate de assinatura removido (sem cert); aviso de SmartScreen esperado.
2. `git tag -a v1.1.2 -m "..."` + `git push origin v1.1.2` → dispara `release.yml`.
3. Monitorar o run no GitHub Actions (fail possível conhecido: cache/npm — corrigir e re-taggar `v1.1.2` se necessário).

### Fase 6 — Verificação final
1. Release `v1.1.2` visível em GitHub Releases com `GasFlow Desktop Setup 1.1.2.exe` + `latest.yml` (bloco não-draft).
2. **Auto-updater:** uma instalação 1.1.1 existente, ao abrir, deve oferecer "Reiniciar e instalar" (15s após boot). Validar se houver máquina com 1.1.1 instalada.
3. App instalado aberto e funcional (decisão #2 atendida).
4. Atualizar `docs/EXECUCAO_FINAL.md` com a execução desta spec.

---

## 5. Critérios de aceite

- [ ] `backend/dist/gasflow-backend.exe` com timestamp pós-correções e `/health` respondendo isoladamente
- [ ] `GasFlow Desktop Setup 1.1.2.exe` gerado, instalação via Setup concluída, app abrindo com login admin funcional
- [ ] Todas as suítes verdes ANTES do tag (decisão #12)
- [ ] Step de assinatura removido do `release.yml`; CI de release conclui e publica a release não-draft
- [ ] `pyinstaller` pinado no `requirements.txt` e instalado localmente
- [ ] Versão `1.1.2` apenas no `desktop/package.json` (lockfile sincronizada)
- [ ] Release notes curadas em PT-BR publicadas
- [ ] `.gitignore` cobre artefatos de build (nada de binário gigante entra no git)

## 6. Pergunta em aberto (menor)

- **Branch de origem da tag:** `main` e `refactor/desktop-sources` estão atualmente no mesmo commit (`2f86542`). Recomendo taggar a partir de `main` após os commits da Fase 4. Se o PR da Onda 4 ainda não tiver sido mergeado quando a tag for criada, o conteúdo da Onda 4 (fontes TS do desktop) precisa estar em `main` de outra forma — **hoje já está** (foram para `main` via merge `d64f53c`), então não há bloqueio; só NÃO mergear o PR separadamente depois sem rever (duplicaria nada, mas o histórico fica redundante).

## 7. Fora de escopo desta spec

- Compra/instalação de certificado Authenticode (decisão #14 — seguir sem cert)
- Bump de versão de frontend/agent/whatsapp (decisão #9 — só desktop)
- Merge do PR `refactor/desktop-sources` (continua pendente de validação do usuário; hoje `main` já contém o conteúdo)
- CI de outros SOs (macOS/Linux) — só Windows
