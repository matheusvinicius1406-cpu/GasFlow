# GasFlow — Status & Plano (documento único)

**Este é o único documento de estado, pendências e decisões do projeto.**
Substitui os 119 arquivos que existiam em `docs/` até 2026-10-14 (todos apagados; conteúdo recuperável — ver §7).

| | |
|---|---|
| **Data** | 2026-10-14 |
| **Baseline** | `main` @ `96c5941`, pushado em `origin/main` |
| **Última release** | tag `v1.2.0` (desktop/frontend/mobile `1.2.0`) |
| **Suítes** | backend **2.291** passed / 30 skipped / 0 failed · frontend **452** · whatsapp **106** · desktop 11/11 · ruff/mypy/alembic-head verdes |
| **Gate de integridade** | 9 findings / 0 pendentes · allowlist 9/9 |
| **Recuperar doc apagado** | `git show fdd2129:docs/<caminho>` |
| **Gate completo** | §9 |

> **Regra de leitura:** qualquer informação de estado com data anterior a 2026-10-09 é
> histórico. A verdade é o código + `CHANGELOG.md` + os relatórios de 09/10 citados aqui.

---

## 0. Como usar

- **§1** onde o sistema está hoje.
- **§2** decisões técnicas que continuam valendo (resumo do que foi apagado).
- **§3** o inventário completo de pendências — é o trabalho por fazer.
- **§4** decisões que só você pode tomar.
- **§5** como resolver, em ondas — **nada foi executado ainda**.
- **§6** o que foi limpo em 2026-10-14 e o que ainda falta limpar.
- **§7** como recuperar qualquer arquivo apagado.
- **§8** achados novos desta auditoria (não constavam em lugar nenhum).
- **§9** comandos do gate.

---

## 1. Estado atual

### 1.1 O que está pronto

- **Produto funcional**: CRM, estoque, financeiro (cadeia Order→Payment→Receivable→Ledger), entregas/rota, automações, IA de texto/áudio, multiempresa com isolamento por tenant (RBAC + migração `c1a2b3d4e5f6`).
- **WhatsApp**: motor **Baileys** em modo dual (`WA_ENGINE`, rollback = trocar env), anti-ban com separação conversacional × campanhas, resilience (heartbeat, backoff, pacing), proxy expondo as 10 rotas do serviço.
- **Entrega inteligente (Fases 8/9/10)**: otimizador OR-Tools, `DispatchScorer`, `OsrmRoutingProvider` com circuit breaker — tudo atrás de flags `default=false`.
- **Infra**: `docker-compose.prod.yml`, CI (4 jobs de teste + Trivy + E2E separado), imagens GHCR, schema 100% via Alembic no boot, auto-update do desktop.
- **Segurança**: 69 operações deixaram de ser anônimas (Fase 1), webhook de alerts com segredo, `init_db` por `alembic upgrade head`, matriz de rotas com 18 `SEM_AUTH?` todas justificadas.

### 1.2 O que é promessa quebrada

- `docs/routing/osrm.md` é citado como existente no `CHANGELOG.md:344` e em `config.py:229` — **nunca foi criado** (ver §8.1).
- Release `v1.2.0` publicada com instalador **sem assinatura** (D3).
- `gh` CLI não instalado na máquina de dev → diagnóstico de CI às cegas (B3).

---

## 2. Decisões vivas (resumo do que foi apagado)

Cada linha substitui um arquivo que foi removido. Detalhe: `git show fdd2129:docs/<caminho>`.

### 2.1 Renomeador de contatos (ADRs 0001–0008)

| ADR | Decisão travada |
|---|---|
| 0001 | Parser de `.vcf` como entrada; pipeline em lote |
| 0002 | `preview` e `apply` desacoplados — nunca aplicar sem preview |
| 0003 | Importação em lote por `sync_batch` (4.800 → 1.066 statements) |
| 0004 | Cache de geocoding **por rua + interseções**, não por número |
| 0005 | Formatter: `{codigo}= {rua} Nº {numero} entre {rua_a} e {rua_b}` |
| 0006 | Jobs `bounded-batch` na tabela `contact_jobs` |
| 0007 | Fallback de CEP: ViaCEP → BrasilAPI → PontoFato; E2E 10k |
| 0008 | "Entre ruas" via CNEFE/Faces do IBGE **sem PostGIS** |

### 2.2 WhatsApp

- **Baileys dual-mode** por env `WA_ENGINE` — rollback = trocar env; invariante de superfície do `provider-manager` (`docs/phase16/BAILEYS_MIGRATION.md`).
- **Anti-ban**: separação de tráfego conversacional × campanhas, caps/warmup/quiet-hours, **sem evasion** (`WHATSAPP_ANTI_BAN_CLOUD_API.md`).
- **Cloud API Meta**: runbook de ativação ainda em execução (`CLOUD_API_ACTIVATION_RUNBOOK.md`).
- **Pareamento/recovery**: runbook de QR (`whatsapp-recovery-runbook.md`), painel de partições (`whatsapp-web-panel.md`), spec de correção (`whatsapp-fix-spec.md`).

### 2.3 Arquitetura / plataforma

| Decisão | Fonte apagada |
|---|---|
| **WebSocket por tenant** com polling como fallback; SSE rejeitado | `phase15/RT01_DECISION.md` |
| **Não mesclar** a branch `gas-flow-scalability-plan`; rate limit em Redis com fail-open em 2 níveis; `/ready` | `phase15/SC01_SCALABILITY.md` |
| **PIX BR Code/QR local** — `qrcode`+`Pillow`, **sem `pypix`** | `phase15/PIX01_PIX_STATIC.md` |
| Docker prod, Alembic no boot, GHCR, smoke | `phase15/DP01_CICD_DEPLOY.md` |
| Como rodar/estender o E2E (stack `docker-compose.e2e.yml` em `:8080`) | `phase15/E2E.md` |
| Contrato da **Driver API v1** (auth + escopo motorista) | `phase14/PHASE14_DRIVER_API.md` |
| bcrypt + rehash transparente, token 256 bits, mensagens genéricas de login | `phase13.1/PHASE13_1_HARDENING.md` |
| **Proibido API com chave comercial/trial**; Nominatim/OSRM/ViaCEP mantidos | `auditoria/catalogo-apis-externas.md` |
| Estoque debitado **só em `DELIVERED`** (B3(a)) | `migrations/2026-09-delivery-debit.md` |
| Migrations Alembic devem usar `batch_alter_table` no SQLite | `migrations/2026-09-sqlite-batch-audit.md` |
| Baseline de autorização: 18 `SEM_AUTH?` justificadas (regressão) | `seguranca/matriz-de-rotas-depois.{md,json}` |
| `sqlalchemy==2.1.4` pinado deliberadamente; `e2e.yml` é a única definição de E2E | `ci/RELATORIO-CI-2026-10-09.md` |
| 69 operações deixaram de ser anônimas; p0 de tenant resolvido | `seguranca/RELATORIO-2026-10-09.md` |

### 2.4 Espécifes de produto ainda de pé

- **Rastreio/entrega inteligente** (`rastreio-entrega-inteligente-spec.md`, na raiz — **não apagado**): 20 decisões travadas, Fases 8/9/10 já pousaram no código.
- **Renomeador Fase 3** (`prompts/renomeador-contatos-fase3.md` → resumido em §3-C2).
- **Entregas & cupons** (`entregas-cupons-spec.md`, 9 features F1–F9 já implementadas).
- **Visão de produto** (`VISION.md`): regra do código permanente do cliente segue válida.

---

## 3. Pendências consolidadas

**Total: 47 itens** — 8 resolvidos, 5 parciais, 26 abertos, 8 externos.
Código dos grupos: `A`–`F` herdados do PLANO_MASTER · `G`–`I` novos desta auditoria.

### A. Segurança / authz

| # | Pendência | Status | Esforço | Fonte |
|---|---|---|---|---|
| A1 | 10 rotas `SOMENTE_DB` sem credencial | ✅ **resolvida** — públicas por design, registradas | S | `seguranca/RELATORIO-2026-10-09` |
| A2 | `POST /webhooks/alerts` sem validação de origem | ✅ **resolvida** — `ALERTS_WEBHOOK_SECRET` + gate 401/503, 11 testes | S | idem |
| A3 | `init_db` usava `create_all()` sem `alembic_version` | ✅ **resolvida** — bootstrap por `alembic upgrade head` | M | `test_init_db_alembic_boot.py` |
| A4 | `routes` (planos de rota) só em memória | ⏳ aberta — **bloqueada por produto** (Fase 21) | M | `FINAL_SYSTEM_STATUS` |

### B. CI / Release

| # | Pendência | Status | Esforço | Fonte |
|---|---|---|---|---|
| B1 | E2E no CI >45 min | ✅ **resolvida** — run `bb4f26d` em 2026-10-14: job **`playwright` = 2 min 12 s**, não >45 min. CI inteira (6 jobs) fechou em **8 min 36 s**, verde. A premissa ">45 min" está **falsificada** | ~~S~~ ✅ | run 38595001184 / 38595001354 |
| B2 | PRs do Dependabot vermelhas (TS7 no whatsapp, ESLint10; 25+ branches) | ✅ **resolvida** — 13 PRs: **11 mergeados**, **#50/#25 fechados** com `ignore this major version` para TypeScript 7.x. 0 PRs abertos, 0 branches órfãs, CI do `main` combinado verde 6/6 em 14:46. Sobra uma **pendência deliberada** nova: migrar TS 6→7 à parte (ver TS7) | ~~S–M~~ ✅ | 2026-10-14, §8.17 |
| B5 | Migração TypeScript 6→7 (quebra `/frontend` e `/whatsapp`) — reprovada pelo Dependabot, precisa de trabalho deliberado | ⏳ aberta — **não automatizável**; `@dependabot ignore this major version` ativo nos dois pacotes até decidir migrar | M | §8.13 / §8.17 |
| B3 | `gh` CLI ausente na máquina de dev | ✅ **resolvida** — `gh` 2.102.0 instalado (winget) e **autenticado** como `matheusvinicius1406-cpu` com escopos `repo` + `workflow`. Dois atritos registrados no caminho: o instalador registra no *Machine* PATH, mas sessões abertas antes da instalação não enxergam (basta repor o PATH ou abrir shell novo); e o `gh.exe` não roda com duplo clique — exige `cmd.exe`/terminal | ~~S~~ ✅ | 2026-10-14 |
| B4 | Testes do desktop cobrem só fumaça (updater/config/preload) | ⏳ aberta (diferível) | M | `auditoria/FALHAS` |

### C. Decisões de produto

| # | Pendência | Status | Fonte |
|---|---|---|---|
| C1 | 12 rotas do serviço WhatsApp sem consumidor — expor tela ou remover? | ✅ **fechada 2026-10-14: EXPOR** e **implementada** — as 12 têm tela. `ListsPage` (listas + membros + sync + seed) e `WhatsAppCustomersPage` (base + consentimento LGPD + promote) em `/whatsapp/lists` e `/whatsapp/customers`; preview no `CampaignWizardPage`; mídia no `WhatsAppAccountsPage`; dedupe no `ContactsCrmPage`. Gate 9/0 preservado — ver §8.18 | §8.18 |
| C2 | Escopo do renomeador Fase 3/4: cidades além de Belém · CNEFE 2022 sem endereço pós-censo · Faces "versão preliminar" · alvo 10k→20k · PontoFato desligável | ⏳ aberta | `prompts/renomeador-contatos-fase3` §12 |
| C3 | Lote de **744 contatos** com nome "antes" pendente de renomeação | ⚠️ dry-run `qwen3:1.7b` OK; **aplicação/arquivar/descartar não decidido** | §4 |

> **Correção de C3**: o PLANO_MASTER dizia "8.601 contatos". 8.601 é o **maior ID**,
> não a contagem. O lote tem **744 entradas**, reconciliadas 744/744 contra
> `data/prototype-contacts/app.db`. Ver §6.2.

### D. Bloqueios externos (não se resolvem com código)

| # | Bloqueio | O que destrava |
|---|---|---|
| D1 | Fiscal NFC-e | Certificado A1 + credenciamento SEFAZ + decisão contábil. MVP: deep link NFF |
| D2 | LGPD/CLT do app do entregador | Documento jurídico antes de soltar o app de localização |
| D3 | Instalador Windows `NotSigned` / SmartScreen | Certificado de code-signing |
| D4 | 5 HIGH de `extract-zip` (whatsapp→wwebjs→puppeteer) | Sem versão upstream; some ao aposentar o rollback `wwebjs` |
| D5 | TypeScript 7 bloqueado no `whatsapp` | `typescript-eslint` compatível com TS7 |
| D6 | Shim `jest-dom-vitest.d.ts` | Vitest 5 upstream |
| D7 | Validações manuais V.1/V.2/V.3 | Execução em ambiente/credenciais — **checklist em 0/3** |
| D8 | LGPD export/delete de dados | Implementação (M) + política |

### E. Dívida técnica diferível (sem prazo, não bloqueia release)

| # | Item |
|---|---|
| E1 | `except Exception:` silenciosos — triagem + log contextual (25 blocos) |
| E2 | `console.log` → `pino` no serviço WhatsApp (24 ocorrências) |
| E3 | 19 funções com complexidade ciclomática > 10 (16 ainda restantes) |
| E4 | F841/ARG/vulture — parâmetros de interface |

### F. Documentação

| # | Item | Status |
|---|---|---|
| F1 | `desktop/README.md` descrevia só o caminho `create_all` | ✅ **confirmada resolvida em 2026-10-14** — linhas 126–143 descrevem `alembic upgrade head` como primário, `stamp head` para banco legado e `create_all` só como plano B; bate com `backend/desktop_entry.py::run_migrations()` |
| F2 | Docs históricos com `whatsapp-web.js` ainda confundindo | ⏳ **superado por esta sessão** — todos os docs apagados |
| F3 | `GASFLOW_CURRENT_STATE_REPORT` / `AUDITORIA` descreviam estado pré-correção | ✅ resolvida |
| F4 | `FINAL_SYSTEM_STATUS` citava 889 testes | ✅ resolvida |

### G. Validações live nunca executadas (novo)

| # | Item | Fonte apagada |
|---|---|---|
| G1 | Suíte live do WhatsApp (`test_provider_live_harness.py`, 13 testes) — **bloqueada por QR/celular real** | `phase15/PENDING_RESOLUTION` |
| G2 | PSP PIX real — gateway + webhook HMAC prontos, **aguarda credenciais de homologação** | `phase15/PENDING_RESOLUTION` |
| G3 | Ativação do **Cloud API Meta** (token permanente, templates, verificação do número) + rotear campanhas para `send_template` | `phase16/CLOUD_API_ACTIVATION_RUNBOOK` |
| G4 | `sendMedia` live + E2E full-stack pedido→entrega→notificação | `phase16/PHASE16_...INTEGRATION` |
| G5 | Roteiro manual da **Central Financeira** (15 seções) + impressão seção a seção | `auditoria/central-financeira-fase5` §4 |
| G6 | Testes de carga do rate limit (ab/vegeta) não executados; janela ZSET não atômica sob concorrência extrema | `phase15/SC01` |
| G7 | `NOT VERIFIED`: Docker/device/provider real (phase10) · STT/TTS reais (phase11) · **provider de IA de texto ainda mock** (FE01 IA-01) | phase10/11, `FE01` |
| G8 | `release.yml` permissão de escrita (P-3) + `UpdateNotifier`/`latest.yml` E2E em release real (D-2/D-3) | `auditoria/01_MATRIZ_DE_RISCOS` |
| G9 | Auto-recovery `logged_out` sem prova em campo (W-1) | `01_MATRIZ_DE_RISCOS`, `PENDING_RESOLUTION` WA-02 |

### H. Segurança residual (novo)

| # | Item | Fonte apagada |
|---|---|---|
| H1 | `/metrics` fora do compose exige `METRICS_PUBLIC=1` ou chave de serviço | `seguranca/RELATORIO-2026-10-09` |
| H2 | Riscos declarados da Fase 13: token demo (não JWT assinado) · SHA-256 → Argon2id · isolamento lógico de tenant **sem PostgreSQL RLS** · **sem MFA** | `phase13/PHASE13_FINAL_VALIDATION` |
| H3 | Guard de permissão nos **GETs** de `/finance/*` e `/reports/*` (V7) — fora do escopo do P3 | `central-financeira-fase2/fase5` |
| H4 | MyPy strict completo pendente (só baseline) | `01_MATRIZ_DE_RISCOS` |
| H5 | Ponte IPC/`UpdateNotifier` precisa de E2E em release real | `01_MATRIZ_DE_RISCOS` D-2 |

### I. Frontend / qualidade (novo)

| # | Item | Fonte apagada |
|---|---|---|
| I1 | ~12 telas sem teste dedicado; estados de permissão/offline não unificados (P2) | `phase15/FE01_SCREEN_INVENTORY` |
| I2 | ~~ESLint sem config no repo~~ **facto errado** — configs existem (`frontend/eslint.config.js`, `whatsapp/eslint.config.js`), `npm run lint` verde nos dois, e o CI **já roda lint no frontend** (`ci.yml:64`) | ⚠️ **corrigido 2026-10-14**: o gap real era o job do whatsapp não rodar lint apesar do script existir — step adicionado. `desktop`/`e2e`/`agent` seguem sem ESLint (desktop cobre com `tsc`; escopo de adicionar é decisão, não bug) |
| I3 | `favorite_product` do Customer360 = `NOT_IMPLEMENTED` (LOW) | `phase6/PHASE6_FINAL_VALIDATION` |
| I4 | `order.created`/`payment.*` fora do Event Bus; consumidor `driver:*` no frontend (P2+) | `phase15/RT01_DECISION` |
| I5 | `docs/routing/osrm.md` inexistente (ver §8.1) — e a feature está entregue | esta auditoria |

---

## 4. Decisões que precisam de você

| # | Decisão | Opções |
|---|---|---|
| **1** | ~~**C1** — 10 rotas WhatsApp sem consumidor~~ | ✅ **DECIDIDO 2026-10-14: EXPOR** (12 rotas, não 10). Manter a arquitetura de 3 camadas |
| **2** | **C3** — lote de 744 contatos | rodar a camada de IA **ou** arquivar **ou** descartar |
| **3** | **C2** — escopo do renomeador Fase 3/4 | o que entra da lista de §3-C2 |
| **4** | **A4** — persistir `routes` | fazer só quando a Fase 21 for aprovada? |
| **5** | **D7** — validações V.1/V.2/V.3 | quando/executar em que máquina (VM + celular real) |
| **6** | **E1–E4** — dívida diferível | escopo e janela (nunca junto de correção) |
| **7** | `_legado_raiz/wwebjs_auth.legado.zip` (351,9 MB) | manter ou apagar (sessão regenerável por QR) |
| **8** | `backend/gasflow.db.backups/` (5 cópias) | manter ou apagar |

---

## 5. Plano de resolução (nada executado)

Regra: **uma onda por vez, cada uma termina com suíte verde + commit.**

| Onda | Escopo | Esforço | Pré-requisito |
|---|---|---|---|
| **A** | **Dívida E1–E4** (except silenciosos, pino, complexidade, F841) | ~1 dia | nenhum |
| **B** | **CI**: ✅ **concluída 2026-10-14** — B1 ✅ (E2E medido 2:12, não >45 min) · B3 ✅ (`gh` instalado e autenticado) · B2 ✅ (11 mergeados / 2 fechados) · I2 ✅ (lint no job do whatsapp) · B5 ⏳ nova (migração TS7, deliberada) | ~~2–3 h~~ ✅ | `gh` |
| **C** | **Decisões de produto**: C1, C3, C2 | a definir | **§4 nº 1–3** |
| **D** | **Segurança residual**: H1 metrics, H2 token→JWT/Argon2id, H3 guard GETs, H4 mypy strict | ~1 dia | — |
| **E** | **Qualidade FE**: I1 telas sem teste, I3 favorite_product, I4 Event Bus | ~1 dia | — |
| **F** | **Validações live**: G1–G9 + D7 | imprevisível | **credenciais/VM/celular (§4 nº 5)** |
| **G** | **Limpeza restante** (§6.3) | ~30 min | **§4 nº 7–8** |
| **—** | **Bloqueios externos D1–D8** | fora do código | certificado/jurídico/upstream |

**Não fazer junto:** onda de dívida (A) sempre isolada de correção de bug.

---

## 6. Limpeza do workspace

### 6.1 Feito em 2026-10-14 (commit `96c5941`, pushado)

A raiz `automação zap/` **não é um repo git** — tudo foi movido para dentro do
`GasFlow/` **antes** de sumir do disco, para que a exclusão seja recuperável.

**Preservado (rastreado):**

| Caminho novo | Conteúdo |
|---|---|
| `data/pendentes-renomeacao-744.json` | lote C3 — 744 contatos `{id, antes}` |
| `data/prototype-contacts/app.db` | protótipo com **8.601 contatos**, 13 listas, 9.412 vínculos (fonte real do lote) |
| `data/export-broadcast/` | 42 lotes de broadcast (9.575 contatos) + 26 `renomear-agenda-*.json` |
| `_legado_raiz/` | protótipo TS órfão (`src/`, `tests/`, `scripts/`), `package.json`, `package-lock`, `tsconfig`, `THIRD_PARTY_NOTICES`, `CHANGELOG-seguranca`, `.gitignore` da raiz, `gasflow.db` |

**Excluído (recuperável via git, §7):** `wwebjs_auth/` da raiz → zipado em
`_legado_raiz/wwebjs_auth.legado.zip` (351,9 MB, **fora do git**, ignorado pelo
`.gitignore`). Sessão Puppeteer órfã — o GasFlow usa
`GasFlow/whatsapp/wwebjs_auth/` (paths relativos) e volume nomeado no compose.

**Docs:** 119 arquivos de `docs/` removidos via `git rm`; sobrou apenas este.

### 6.2 Pendência C3 — como está agora

| | |
|---|---|
| Lote | **744 contatos** (não 8.601), todos reconciliados 744/744 contra o DB |
| Status dos nomes | **744/744 ainda com o nome original** — nada foi renomeado |
| Ruído no lote | ~15–20 entradas de teste ("Inválido", "Fluxo Teste", "Idem", "Grupo Teste", "Fulano", "Beltrano"…) → descartar antes de rodar |
| Duplicatas | **19 nomes repetidos em 52 IDs** (ex.: "Surper Gas ( Wagner )" ×4, "= Gas Amigo" ×3) → investigar duplicidade real **antes** de renomear |
| Dry-run | OK com `qwen3:1.7b`: 0 alterações pendentes no determinístico, 744 elegíveis à IA |

### 6.3 Ainda falta limpar (fora do git, ignorado — exige confirmação)

| Caminho | O que é | Ação |
|---|---|---|
| `backend/$(mktemp -u).db*` | bug de shell virou arquivo literal | apagar |
| `backend/_import_test.db` (**178 MB**), `_integrity_recon.db*`, `_login_test*.db*`, `ci-boot-test.db*`, `gate_fresh.db*`, `gate_legacy.db*`, `test_matrix.db*`, `test_migration.db`, `test-desktop.db*` | resíduos de teste | apagar |
| `backend/gasflow.db.legacy` | banco legado | apagar |
| `backend/*.log` (`b1-pytest*`, `dev.log`, `full_run.log`, `pair_run.log`, `pip-ci-install.log`, `pytest-*.log`, `trio.log`, `uvicorn-boot.log`) | logs | apagar |
| `backend/__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` | caches | apagar |
| `compose-e2e-run.log`, `compose-e2e.log` | logs na raiz | apagar |
| **manter** | `backend/gasflow.db` (dev), `backend/.venv-ci/`, `backend/gasflow.db.backups/` (§4 nº 8) | — |

---

## 7. Recuperação de arquivos apagados

**Docs (119 arquivos)** — todos presentes no commit `fdd2129`:

```bash
git show fdd2129:docs/PLANO_MASTER.md            # exemplo
git show fdd2129:docs/adr/ADR-0008-entre-ruas-por-dados-ibge.md
git checkout fdd2129 -- docs/                     # restaurar a pasta inteira
```

**Conteúdo por grupo** (todos sob `docs/` em `fdd2129`):

| Grupo | Arquivos |
|---|---|
| `adr/` | 8 ADRs do renomeador |
| `auditoria/` | 13 md + `areas/` (4) + `integridade/` (2) + `d20-concordancia.json` + `fase3-metricas-locais.json` + `central-financeira-fase5-evidencias/` (8 PNG + 1 PDF) |
| `phase5`…`phase14` | 22 validações/auditorias de fase (+ `PHASE14_DRIVER_API.md`) |
| `phase15/` | 9 (DP01, E2E, FE01, FE02, GOLDEN, PENDING_RESOLUTION, PIX01, RT01, SC01) |
| `phase16/` | 4 (BAILEYS_MIGRATION, ANTI_BAN, CLOUD_API_RUNBOOK, RESILIENCE) |
| `seguranca/` | RELATORIO-2026-10-09 + matriz antes/depois (.md+.json) |
| `ci/` | RELATORIO-CI-2026-10-09 |
| `prompts/` | renomeador fase2 e fase3 |
| `migrations/` | delivery-debit, sqlite-batch-audit |
| `wave1/`, `wave2.5/`, `spike/fase3/` | REPOSITORY_AUDIT, PROVIDER_COMPARISON, README + 2 `.py` |
| raiz de `docs/` | 35 md: PLANO_MASTER, ROADMAP(_BLOCKERS), VISION, AUDITORIA, ARCHITECTURE_AUDIT, BASELINE_14_9, GASFLOW_CURRENT_STATE_REPORT, FINAL_SYSTEM_STATUS, EXECUCAO_FINAL, reorg-plan, FLOWS, API, DATABASE, BUSINESS_RULES, FLOWS, specs de WhatsApp, AUTO_UPDATE, ollama/ai-setup, migrations.md, release-notes-v1.2.0, etc. |

**Raiz (protótipo)** — commit `96c5941`:

```bash
git show 96c5941:_legado_raiz/package.json
git checkout 96c5941 -- _legado_raiz/            # restaurar o protótipo inteiro
```

---

## 8. Achados desta auditoria (não constavam)

1. **`docs/routing/osrm.md` não existe.** `CHANGELOG.md:344` e `backend/app/core/config.py:229` descrevem um arquivo que nunca foi criado. A Fase 10 (OSRM) está **entregue no código** (`osrm_provider.py`, `circuit_breaker.py`, `factory.py`, `docker-compose.osrm.yml`, flags todas no `config.py`), mas o doc prometido sumiu com a limpeza. → **Recriar ou remover as duas referências** (I5).
2. **C3 com contagem errada** no PLANO_MASTER: "8.601 contatos" na verdade é o maior ID; o lote tem 744.
3. **`main` estava 5 commits à frente do remoto** — sem backup externo durante toda a auditoria. Pushado antes de qualquer exclusão.
4. **`data/app.db` da raiz era o dado real** (8.601 contatos), não lixo — identificado e preservado antes da limpeza; todos os 744 IDs do lote batem 100%.
5. **`export/` tinha 26 `renomear-agenda-*.json`** além dos lotes de broadcast — agendas e backups do renomeador de 06–13/10, preservados em `data/export-broadcast/`.
6. **Duas specs Playwright gravavam dentro de `docs/`** (`fase5-evidencias.spec.ts` e `fase5-pdf-electron.spec.ts` → `OUT = docs/auditoria/.../evidencias/`) — corrigido para `e2e/evidencias/` nesta sessão, senão quebraria.
7. **Referências a `docs/` em código/CI são só docstrings** (`ci_gate.py`, `test_schema_migration.py`, `test_finance_v7_read_guard.py`, `test_delivery_stock_reversal.py`) — a exclusão não quebra build/teste. As ~30 referências do `CHANGELOG.md` viraram ponteiro histórico.
8. **A suíte de frontend NÃO roda estável no default desta máquina.** O pool de forks do Vitest morre com `Timeout waiting for worker to respond` — em 3 runs seguidos ela reportou 370, 452 e 394 testes, com 6–9 arquivos que **nunca subiram worker** e eram contados como "passed" no resumo. Causa: 4 cores lógicos / 11,8 GB e jsdom criado por arquivo. **Correção: `vitest run --maxWorkers=2`** → 74 arquivos / 452 testes / 0 erros, determinístico. Vale para CI local e para o gate manual.
9. **O backend leva ~61 min, não ~25 min** como estimava o PLANO_MASTER (medido: 3648 s). Planejar o gate em cima disso — é o motivo de dois runs terem estourado timeout de shell.
10. **`alembic heads` hoje é `c1a2b3d4e5f6`** (migração do P0 multiempresa, `33b7de0`), não mais `9f4b7e2a6c31` como registrava o PLANO_MASTER §4. Head único, sem divergência.
11. **`docs/routing/osrm.md` foi recriado em 2026-10-14** (Onda 2.1) a partir do código real (`osrm_provider.py`, `factory.py`, `circuit_breaker.py`, `docker-compose.osrm.yml`, flags de `config.py`), não da spec prometida — a feature já estava entregue, só o doc faltava.
12. **`desktop/README.md:147` estava corrompido** com o texto literal `<arg_value><b88a6f17>` no meio de uma frase — resíduo de alguma ferramenta. Removido. Era o único arquivo do repo com esse padrão.
13. **B2 do Dependabot: fonte original errada, e duas leituras intermediárias também — o erro foi julgar PR por CI velha.** A fonte `DEPENDABOT_v1.1.7` dizia "25+ branches vermelhas, TS7 no whatsapp". A primeira medição (2026-10-14) achou **13 PRs, 12/13 verdes** e concluiu que o doc estava errado. Essa conclusão era falsa: os checks tinham **4 a 23 dias** e estavam em bases antigas (`c04e87b`, `1acd033`, `54abd34`), nenhuma em `main` atual. Ao **rebasear os 13 para o `main` novo e deixar a CI rodar de verdade**, o quadro se inverteu: **11 verdes**, e **exatamente os dois major bumps de TypeScript 6→7 falharam** — **#50** em `/frontend` (jobs `Frontend` e `playwright`) e **#25** em `/whatsapp` (job `WhatsApp service`). **A afirmação original do doc ("TS7 no whatsapp vermelho") estava correta o tempo todo**; quem a refutou fui eu, com evidência de 23 dias. Lição operacional: um PR só é julgável depois de rebaseado para o `main` vigente, e o Dependabot **não rebasea sozinho** quando o bump não gera conflito — a CI velha fica parada e parece conclusiva. Ver §8.17 para o desfecho.
14. **O gap real de lint era o job do WhatsApp no CI.** O `frontend` já rodava `npm run lint` desde antes (`ci.yml:64`), e existiam `eslint.config.js` válidos em `frontend/` e `whatsapp/` — o §3-I2 original ("ESLint sem config no repo") estava errado. O job `whatsapp` tinha `Typecheck` e `Build (tsc)` mas nenhum step de lint, apesar de o script existir e passar localmente. Step adicionado em 2026-10-14 (Onda 2.2). `desktop`, `e2e` e `agent` seguem sem ESLint por decisão de escopo — `desktop` é coberto por `tsc`.
15. **Os tempos do PLANO_MASTER confundiam máquina local com CI.** O backend leva **~61 min localmente** (§8.9, 3648 s) mas **5 min 51 s no CI** — runners do GitHub são bem mais rápidos que a máquina de dev (4 cores lógicos / 11,8 GB). Ambos os números são verdadeiros para o seu ambiente; o planejamento deve usar o valor do ambiente alvo. Pela mesma razão o ">45 min de E2E" (B1) nunca se confirmou: medido **2 min 12 s** no CI.
16. **Run de CI de referência (commit `bb4f26d`, 2026-10-14) — 6/6 jobs verdes em 8 min 36 s:** `Agent` 0:17 · `WhatsApp` 0:37 (já com o step de lint novo) · `Migrations` 0:54 · `Frontend` 1:14 · `Trivy` 2:39 · `Backend` 5:51. Workflow `Build & Push Images` separado, 4/4 verdes (até 1:15). É a baseline de regressão daqui pra frente.
17. **B2 fechada em 2026-10-14 — 13 PRs do Dependabot: 11 mergeados, 2 fechados.** Fluxo executado: `@dependabot rebase` nos 13 → CI nova no `main` → **11 verdes mergeados** (squash, branch deletada) e **#50 + #25 fechados** com `@dependabot ignore this major version` (o bot confirmou: "won't notify you about version 7.x.x again"). Detalhe de execução relevante: os 13 estavam em 4 grupos por arquivo (`backend/requirements-dev.txt`, `e2e/`, `whatsapp/`, `frontend/`), então o merge precisou ser **sequencial por grupo** — mergear um invalidava o lockfile dos irmãos, que eram rebaseados e revalidados antes do próximo merge. Estado final: **0 PRs abertos, 0 branches `dependabot/*` sobrando**, e CI do `main` combinado (**`991db31`**) verde **6/6 em 14 min 46 s** (`Frontend` 1:17 · `Agent` 0:15 · `Migrations` 0:50 · `Backend` 7:15 · `WhatsApp` 0:29 · `Trivy` 2:25). A migração para TypeScript 7 fica **pendência deliberada** — não é automação, quebra `/frontend` e `/whatsapp`.
18. **C1: são 12 rotas sem consumidor, não 10 — e a decisão é expor.** O doc dizia 10; a checagem exata (cada rota do bloco *Proxy completo* em `accounts.py:418-529` comparada às URLs que o frontend realmente chama, normalizando `${...}` dos template literals) devolve **12 de 12 sem nenhuma chamada**. As 12: `POST /accounts/{id}/media` · `POST /contacts/dedupe` · `POST /customers/sync` · `PUT /customers/{id}/status` · `GET /lists/{id}/contacts` · `POST/DELETE /lists/{id}/contacts/{cid}` · `GET /lists/{id}/customers` · `POST/DELETE /lists/{id}/customers/{cid}` · `POST /lists/{id}/sync` · `POST /campaigns/{id}/preview` · `POST /customers/{cid}/promote` · `POST /customers/{id}/opt-in|opt-out` · `POST /lists/seed`. **Decisão do usuário (2026-10-14): expor**, preservando a arquitetura de 3 camadas. Achado colateral: `api.whatsapp` em `frontend/src/lib/api/client.ts` **não é invocado por nenhuma tela** — o padrão vigente é chamar `apiClient` com URL literal dentro da página; as telas novas seguem o padrão existente, não o objeto morto.
19. **O gate de integridade não resolve variáveis no último segmento de URL — e isso quebrou o gate no meio da implementação.** O extrator `frontend_api_calls()` pega o template literal inteiro e normaliza `${...}` para `*`, depois compara com as rotas do OpenAPI (onde `{param}` também vira `*`. `apiClient.post(\`/whatsapp/customers/${id}/${action}\`)` virava `*/*` e não casava com `/whatsapp/customers/*/opt-in`, gerando `tela-sem-endpoint` e **findings 9→10 / pendentes 0→1**. O sintoma é assimétrico e fácil de diagnosticar errado: `/whatsapp/lists/${a}/contacts/${b}` passou sem problema, porque ali os dois params são variáveis e o backend tem `{list_id}/{contact_id}` — dois `*` de ambos os lados. O truque é que só o **último** segmento precisa ser literal: bastou separar em dois `if` com `apiClient.post(\`/whatsapp/customers/${customerId}/opt-in\`)` e `.../opt-out\`)` para voltar a 9/0. Lição operacional: em qualquer chamada com segmento de rota dinâmico, **prefira literais ramificados** a interpolar o segmento — o audit é estático e não enxerga `if/else` fora do parêntese do `apiClient`.

---

## 9. Gate de verificação

**Rodado e verde em 2026-10-14** (Fase 1 desta sessão — ver §8.8/§8.9 para as duas correções de comando):

| Check | Resultado |
|---|---|
| `ruff check app tests scripts` | All checks passed |
| `mypy app` | Success: 0 issues in 337 files |
| `alembic heads` | head único `c1a2b3d4e5f6` |
| `pytest -q -p no:randomly` | **2291 passed / 30 skipped / 0 failed** (3648 s) |
| `frontend: vitest run --maxWorkers=2` | **452 passed / 74 files / 0 errors** |
| `whatsapp: npm test` | **106 passed / 0 failed** |
| `desktop: npm run typecheck` | exit 0 |
| `desktop: npm test` | **71 passed / 0 failed** |
| `tests.integrity_audit` | findings=9 / **pendentes=0** |
| CI no `main` (run `bb4f26d`, 2026-10-14) | **6/6 jobs verdes em 8 min 36 s** (E2E 2:12, Backend 5:51) — ver §8.16 |
| CI no `main` combinado (run `991db31`, 2026-10-14, após 11 merges de deps) | **6/6 jobs verdes em 14 min 46 s** — baseline vigente; ver §8.17 |

```bash
cd backend
.venv-ci/Scripts/python.exe -m ruff check app tests scripts
.venv-ci/Scripts/python.exe -m mypy app
.venv-ci/Scripts/python.exe -m alembic heads                   # head único c1a2b3d4e5f6
.venv-ci/Scripts/python.exe -m pytest -q -p no:randomly        # ~61 min
ADMIN_PASSWORD='<sua>' .venv-ci/Scripts/python.exe -m tests.integrity_audit   # espera 9/0
cd ../frontend && npx vitest run --maxWorkers=2                # OBRIGATÓRIO nesta máquina
cd ../whatsapp && npm test
cd ../desktop && npm run typecheck && npm test
cd .. && npm run evidencias                                     # e2e/ (opcional)
```
