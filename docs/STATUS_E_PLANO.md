# GasFlow — Status & Plano (documento único)

**Este é o único documento de estado, pendências e decisões do projeto.**
Substitui os 119 arquivos que existiam em `docs/` até 2026-10-14 (todos apagados; conteúdo recuperável — ver §7).

| | |
|---|---|
| **Data** | 2026-10-20 (última revisão; ondas concluídas até 2026-10-16) |
| **Baseline** | `main` @ `48037b2` (A4/B4/C2; árvore de trabalho com o refactor do desktop de 20/10) |
| **Última release** | tag `v1.2.0` (desktop/frontend/mobile `1.2.0`) |
| **Suítes** | backend **2.310** passed / 30 skipped / 0 failed (20/10) + 11 testes novos verdes (sync-all e LGPD) · frontend **528** / 90 arquivos (20/10) · whatsapp **106** (19/10) · desktop **152** (20/10) · ruff / mypy strict 0 em 337 / vulture 0 / alembic head único `a4b5c6d7e8f9` (20/10) |
| **Gate de integridade** | 11 findings / 0 pendentes · allowlist 14/14 |
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
- **§5** como resolver, em ondas — **A, B, D e E executadas e fechadas**; C, F, G pendentes.
- **§6** o que foi limpo (14/10 e 19/10) e o que ainda depende de decisão.
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

- Release `v1.2.0` publicada com instalador **sem assinatura** (D3) — **única que segue de pé**.

> **Corrigido em 2026-10-19:** este bloco listava duas promessas que já estavam
> resolvidas e contradiziam o resto do documento — `docs/routing/osrm.md`
> **foi recriado** em 14/10 (§8.11) e o `gh` CLI **está instalado e autenticado**
> (§3-B3). Sobra só o D3.

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

**Total: 47 itens** — recontagem de **2026-10-16**, atualizada em **2026-10-20** (o I1 fechou com o transversal de permissão/offline, §8.26, **C3 fechou com a renomeação do lote**, §6.2, **A4 fechou com a persistência do plano de rota**, §8.28, **B4 fechou com a cobertura desktop**, §8.29, e **C2 fechou mantendo o estado atual**, §8.30, e **G8 fechou com a Fase D do auto-update**, `release-v1.2.0-spec.md`): **29 resolvidos · 0 parciais · 1 aberto** (B5 — agora bloqueio externo com data-alvo de reavaliação, D5) **· 17 dependentes de fator externo** (D1–D8, G1–G7, G9, H5 — certificado, jurídico, credenciais, VM/celular, upstream). Critério: “resolvido” = o gate que cobre o item está verde e a evidência está citada na própria linha; “parcial” = só um subitem resta.
Código dos grupos: `A`–`F` herdados do PLANO_MASTER · `G`–`I` novos desta auditoria.

### A. Segurança / authz

| # | Pendência | Status | Esforço | Fonte |
|---|---|---|---|---|
| A1 | 10 rotas `SOMENTE_DB` sem credencial | ✅ **resolvida** — públicas por design, registradas | S | `seguranca/RELATORIO-2026-10-09` |
| A2 | `POST /webhooks/alerts` sem validação de origem | ✅ **resolvida** — `ALERTS_WEBHOOK_SECRET` + gate 401/503, 11 testes | S | idem |
| A3 | `init_db` usava `create_all()` sem `alembic_version` | ✅ **resolvida** — bootstrap por `alembic upgrade head` | M | `test_init_db_alembic_boot.py` |
| A4 | `routes` (planos de rota) só em memória | ✅ **resolvida 2026-10-19** — tabela `route_plan_records` (upsert por tenant+driver), migração `a4b5c6d7e8f9`, repositório `SQLAlchemyRoutePlanRepository`, save best-effort nos dois caminhos (`POST /route/optimize` e pós-atribuição), `GET /delivery/route/plan/{driver_id}`, 13 testes de persistência + 176 de regressão. Flag `DELIVERY_SMART_ROUTING_ENABLED` continua default false | M | §8.27 |

### B. CI / Release

| # | Pendência | Status | Esforço | Fonte |
|---|---|---|---|---|
| B1 | E2E no CI >45 min | ✅ **resolvida** — run `bb4f26d` em 2026-10-14: job **`playwright` = 2 min 12 s**, não >45 min. CI inteira (6 jobs) fechou em **8 min 36 s**, verde. A premissa ">45 min" está **falsificada** | ~~S~~ ✅ | run 38595001184 / 38595001354 |
| B2 | PRs do Dependabot vermelhas (TS7 no whatsapp, ESLint10; 25+ branches) | ✅ **resolvida** — 13 PRs: **11 mergeados**, **#50/#25 fechados** com `ignore this major version` para TypeScript 7.x. 0 PRs abertos, 0 branches órfãs, CI do `main` combinado verde 6/6 em 14:46. Sobra uma **pendência deliberada** nova: migrar TS 6→7 à parte (ver TS7) | ~~S–M~~ ✅ | 2026-10-14, §8.17 |
| B5 | Migração TypeScript 6→7 (quebra `/frontend` e `/whatsapp`) — reprovada pelo Dependabot, precisa de trabalho deliberado | ⏳ **bloqueio externo** (D5) — `typescript-eslint` sem suporte a TS7; TS 7.1 stable 24/11/2026; lint ~Q1/2027. `ignoreDeprecations: "6.0"` no tsconfig do whatsapp perde efeito em TS7. `@dependabot ignore this major version` ativo. **Reavaliação: 2027-01** (após stable + typescript-eslint) | M | §8.13 / §8.17 / D5 |
| B3 | `gh` CLI ausente na máquina de dev | ✅ **resolvida** — `gh` 2.102.0 instalado (winget) e **autenticado** como `matheusvinicius1406-cpu` com escopos `repo` + `workflow`. Dois atritos registrados no caminho: o instalador registra no *Machine* PATH, mas sessões abertas antes da instalação não enxergam (basta repor o PATH ou abrir shell novo); e o `gh.exe` não roda com duplo clique — exige `cmd.exe`/terminal | ~~S~~ ✅ | 2026-10-14 |
| B4 | Testes do desktop cobrem só fumaça (updater/config/preload) | ✅ **resolvida 2026-10-19, ampliada em 2026-10-20** — 71→**101→152 testes**: parsers do ai-service (extractJsonBlock/parseMoney/coerceOrder/parseOrdersJson), idempotência do `registerUpdateIpc`, guard do `setupAutoUpdate` (dev), settings.json corrompido, canais do updater no preload; em 20/10, helpers puros extraídos de `index.ts` (`app-helpers`: porta/URLs, paths de boot, nome de PDF, cupom ESC/POS, plano de serviços), contrato completo do IPC do updater e protocolo JSON-lines do `AgentBridge` (incluindo spawn que falha). Job `desktop` no CI (typecheck+build+test) | M | §8.28 / §8.30 |

### C. Decisões de produto

| # | Pendência | Status | Fonte |
|---|---|---|---|
| C1 | 12 rotas do serviço WhatsApp sem consumidor — expor tela ou remover? | ✅ **fechada 2026-10-14: EXPOR** e **implementada** — as 12 têm tela. `ListsPage` (listas + membros + sync + seed) e `WhatsAppCustomersPage` (base + consentimento LGPD + promote) em `/whatsapp/lists` e `/whatsapp/customers`; preview no `CampaignWizardPage`; mídia no `WhatsAppAccountsPage`; dedupe no `ContactsCrmPage`. Gate 9/0 preservado — ver §8.18 | §8.18 |
| C2 | Escopo do renomeador Fase 3/4: cidades além de Belém · CNEFE 2022 sem endereço pós-censo · Faces "versão preliminar" · alvo 10k→20k · PontoFato desligável | ✅ **fechada 2026-10-19: MANTER ESTADO ATUAL** — as 5 recomendações do §12 aprovadas: cidades Belém-only; aceitar lacuna CNEFE 2022; faces preliminar com re-ingestão idempotente; gate 10k; PontoFato ligado com toggle break-glass. Fase 3 (IBGE/CNEFE) já em produção (migração `9f4b7e2a6c31`, `IbgeEntreRuasProvider`, `jobs.py:318-320`, gate D20 aprovado); PontoFato ligado (`pontofato_enabled: true` em `config.py:300`, usado em `cep.py:192`) | §8.29 |
| C3 | Lote de **744 contatos** com nome "antes" pendente de renomeação | ✅ **fechada 2026-10-19** — mapping gerado manualmente (sem Ollama), 711 nomes distintos: 20 descartados (teste), 92 reestruturados com endereço, 174 só limpeza, 425 já limpos (sem mudança). Aplicado via `--from-file`: **275 contatos renomeados**, 0 falhas, backup em `export/renomear-agenda-backup-*.json` | §6.2 |

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
| D5 | TypeScript 7 bloqueado no `whatsapp` | `typescript-eslint` compatível com TS7 (reavaliar 2027-01 — TS 7.1 stable 24/11/2026, lint ~Q1/2027) |
| D6 | Shim `jest-dom-vitest.d.ts` | Vitest 5 upstream |
| D7 | Validações manuais V.1/V.2/V.3 | Execução em ambiente/credenciais — **checklist em 0/3** |
| D8 | LGPD export/delete de dados | ✅ **implementado 2026-10-20** — backend `POST /clients/{codigo}/export` + `DELETE /clients/{codigo}/data` (anonimização preserva pedidos/fiscal, auditoria, **10 testes**) e tela **Privacidade e LGPD** na ficha do cliente (exportar JSON; anonimizar exige digitar o código; permissões `customer.write`/`customer.*`). Falta só a política/revisão jurídica |

### E. Dívida técnica diferível — **Onda A concluída em 2026-10-15 (E1–E4 fechadas)**

| # | Item | Status |
|---|---|---|
| E1 | `except Exception:` silenciosos | ✅ **fechada 2026-10-15** — os **46** blocos do `backend/app` ganharam log contextual (`logger.error/warning(..., exc_info=True)` para problema real, `debug` para fallback benigno); detector de `except` silencioso em `app/` = **0**. O único restante do repo é `scripts/renomear_agenda_local.py:236` (`reconfigure` best-effort de CLI), mantido de propósito |
| E2 | `console.log` → `pino` no serviço WhatsApp | ✅ fechada 2026-10-14 (`e3c8f48`) — 0 `console.*` em `whatsapp/src`, regra `no-console` no lint, `pino@^10.3.1` no `whatsapp/package.json`. Restam `console.*` fora do serviço: `agent/debug2.ts`(2), `agent/src/index.ts`(3), `e2e/scripts/fase5-pdf-electron.spec.ts`(1), `mobile/src/containers/wired.tsx`(5) |
| E3 | Funções com complexidade ciclomática > 10 | ✅ **fechada 2026-10-15** — **44 → 0** (36 em `app/`, 6 em `scripts/`, 2 em `tests/`), sempre por extração de helpers privados (sem mudança de comportamento). Maiores: `db_integrity_check.check_integrity` 23→1, `integrity_audit.collect_findings` 22→2, `main.lifespan` 22→1, `renamer.renomear` 20→8, `workflow_engine.resume_after_approval` 19→6, `whatsapp/gateway.process_incoming` 17→5, `overpass._conta` 19→≤10. Travada no gate: `C901` + `max-complexity = 10` no `ruff.toml` da raiz |
| E4 | F841/ARG/vulture — parâmetros de interface | ✅ **fechada 2026-10-15** — **F841 36 → 0** (saiu do `ignore` do ruff; 1 em `app/`, 35 em `tests/`, sempre mantendo a chamada com efeito). **ARG 119 → 0** em `app/`: 70 guardas FastAPI `ctx`→`_ctx` (padrão já usado em `whatsapp/accounts.py`; `Depends` mantido, só o nome vira `_ctx`), 17 renomes de helpers privados, 29 `# noqa` documentado em contratos (provedores LLM/STT/TTS/WhatsApp, PSP, repo), Query `community_member` morta removida e `_get_order_data_for_date` passou a filtrar por data (bug: relatório diário listava todas as entregas). **vulture 1 → 0** (`raise` duplicado após `raise ... from` em `client_repository.py`). `ARG` entrou no `select` com `per-file-ignores` só para `backend/tests/**` (336 — o pytest exige o nome exato do parâmetro para injetar fixture) e vulture entrou no CI (`--min-confidence 80`) |

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
| G8 | `release.yml` permissão de escrita (P-3) + `UpdateNotifier`/`latest.yml` E2E em release real (D-2/D-3) | ✅ **fechada 2026-10-20** — `permissions: contents: write` no `release.yml` (comprovado pela release v1.2.0 completa de 23/09) e **Fase D da `release-v1.2.0-spec.md` validada com log real do updater** (upgrade 1.1.6→1.2.0, `sem atualizações (v1.2.0 é a mais recente)`, `download_url` do APK 200/50.3MB, boot do empacotado com `/health` 200) | `auditoria/01_MATRIZ_DE_RISCOS` · `release-v1.2.0-spec.md` §Fase D |
| G9 | Auto-recovery `logged_out` sem prova em campo (W-1) | `01_MATRIZ_DE_RISCOS`, `PENDING_RESOLUTION` WA-02 |

### H. Segurança residual (novo) — **Onda D executada em 2026-10-15**

| # | Item | Status | Fonte apagada |
|---|---|---|---|
| H1 | `/metrics` fora do compose exige `METRICS_PUBLIC=1` ou chave de serviço | ✅ **já estava resolvido** — `main.py:265-289` (`METRICS_PUBLIC` default `False` + aceita `X-GasFlow-Key`/`Bearer` com a chave de serviço) e 11 casos em `tests/test_auth_negative_matrix.py` (401 sem chave com chave configurada, 200 com chave certa, 200 se `METRICS_PUBLIC=1`). O risco do relatório era anterior a essa implementação | `seguranca/RELATORIO-2026-10-09` |
| H2 | Riscos declarados da Fase 13: token demo (não JWT assinado) · SHA-256 → Argon2id · isolamento lógico de tenant **sem PostgreSQL RLS** · **sem MFA** | ✅ **token e senha já resolvidos; RLS/MFA são decisões, não código pendente** — o access token é **JWT HS256 assinado** (`application/security/jwt_crypto.py`) com refresh opaco gravado só como sha256 (`operator_token.py`), ou seja não há "token demo" em uso. Senha é **bcrypt** (`domain/security/models.py:362-383`) com fallback de verificação SHA-256 legado + `needs_rehash` que promove para bcrypt no próximo login (Argon2id seria troca de algoritmo, não correção). Tenant é isolado por repositório (`tenant_id` em toda query; `tests/test_tenant_isolation.py` + `test_cross_tenant_isolation.py`) — **RLS do PostgreSQL e MFA seguem fora do escopo**: são features/decisão (§4), não dívida escondida | `phase13/PHASE13_FINAL_VALIDATION` |
| H3 | Guard de permissão nos **GETs** de `/finance/*` e `/reports/*` (V7) — fora do escopo do P3 | ✅ **já estava resolvido** — `require_permission("finance.read")` nos GETs de `presentation/api/finance/finance.py` e nas rotas de `/reports`, travado por `tests/test_finance_v7_read_guard.py` (VIEWER 200, DRIVER/CUSTOMER 403) | `central-financeira-fase2/fase5` |
| H4 | MyPy strict completo | ✅ **fechado em 2026-10-16** — o bloco `ignore_errors` foi apagado por inteiro: `mypy app` roda strict, **0 erros em 335 arquivos, sem nenhuma seção**. Histórico (strict real medido com o baseline removido): **610 erros em 53 módulos → 566 erros em 31 módulos**. 22 módulos saíram do baseline (5 já em 0 e 17 corrigidos nesta onda, incluindo bugs de runtime — §8.22). Os 566 restantes têm **uma causa raiz medida**: model SQLAlchemy legado (`x = Column(...)`) faz o mypy tipar o atributo como `Column[str]`; são **572 declarações em 21 modelos**, e os 5 modelos novos já usam `Mapped[...]`. **Migração executada em 2026-10-16**: os 22 arquivos de modelo foram para `Mapped[...]` (preservando a nullability — §8.24) e o strict caiu para **165 erros em 21 módulos**; 7 seções saíram do baseline e, na sequência (mesma data), os consumidores finais foram corrigidos — **vários eram bugs latentes de runtime (§8.25)** — e o bloco `ignore_errors` foi **apagado por inteiro**. O `mypy app` agora roda strict total: **0 erros em 335 arquivos, sem nenhuma seção** | `01_MATRIZ_DE_RISCOS` |
| H5 | Ponte IPC/`UpdateNotifier` precisa de E2E em release real | `01_MATRIZ_DE_RISCOS` D-2 |

### I. Frontend / qualidade (novo)

| # | Item | Fonte apagada |
|---|---|---|
| I1 | ~12 telas sem teste dedicado; estados de permissão/offline não unificados (P2) | ✅ **fechada 2026-10-19** — as duas metades: **telas** em 16/10 (das ~12 originais restavam 8 — `WorkflowsPage`, `CustomerDetailPage`, `DriverLoginPage`, `InventoryDetailPage`, `OrderDetailPage`, `ProductDetailPage`, `IntegrationsPage`, `ContactsCrmPage` — todas ganharam teste dedicado, FE **463 → 499**) e o **transversal** em 19/10 (classificador único + `<ErrorState error>` + tela `PermissionDenied` no guard; 41 sites convertidos, FE **499 → 520** — §8.26) | `phase15/FE01_SCREEN_INVENTORY` |
| I2 | ~~ESLint sem config no repo~~ **facto errado** — configs existem (`frontend/eslint.config.js`, `whatsapp/eslint.config.js`), `npm run lint` verde nos dois, e o CI **já roda lint no frontend** (`ci.yml:64`) | ⚠️ **corrigido 2026-10-14**: o gap real era o job do whatsapp não rodar lint apesar do script existir — step adicionado. `desktop`/`e2e`/`agent` seguem sem ESLint (desktop cobre com `tsc`; escopo de adicionar é decisão, não bug) |
| I3 | `favorite_product` do Customer360 = `NOT_IMPLEMENTED` (LOW) | ✅ **já estava implementado** (FASE 6 FIX) — `order_repository.get_customer_metrics` calcula o produto favorito de `order_items` (soma de `quantity`, agrupada por `product_nome`, top-1) e o `Customer360UseCase` recebe o repositório de pedidos de verdade (`presentation/api/clients.py:105`), com `result.update(metrics)` no use case. Travado por `tests/test_phase6_validation.py:443` (`test_favorite_product_implemented`) e `tests/test_crm.py:218`. O `"favorite_product": None` que resta em `client/use_cases.py:198` é só o default do dict antes do update | `phase6/PHASE6_FINAL_VALIDATION` |
| I4 | `order.created`/`payment.*` fora do Event Bus; consumidor `driver:*` no frontend (P2+) | ✅ **fechado 2026-10-16 (backend + consumidor frontend)** — `order.created`/`order.updated` **já eram publicados** (`presentation/api/orders.py` na criação e na troca de status) e a ponte realtime já assinava `order`. O buraco real era só o **pagamento**: `payment.confirmed`/`payment.pending` existiam no `EventType` **sem nenhum publisher** e o prefixo `payment` **não estava na assinatura** de `setup_realtime_bridge` (o próprio `test_realtime.py` afirmava `PAYMENT_CONFIRMED not in subscribed` — o teste documentava a lacuna como se fosse intenção). Fechado: helper `publish_payment_event`, publicação em `finance.py` (registro de pagamento) e `finance/payments.py` (criação → PENDING, confirmação → CONFIRMED), prefixo `payment` assinado na ponte, e testes trocados para afirmar a assinatura + roteamento do evento no canal do tenant. **Consumidor no frontend fechado** na mesma onda: `realtimeQueryKeys` ganhou o branch `payment.*` (invalida `orders`, `dashboard` e os caches `finance-payments`/`finance-receivables`/`finance-cash`/`finance-balance`), e o teste que antes afirmava `payment.confirmed → []` foi invertido | `phase15/RT01_DECISION` |
| I5 | `docs/routing/osrm.md` inexistente (ver §8.1) | ✅ **resolvida 2026-10-14** — arquivo recriado a partir do código realmente entregue (`osrm_provider.py`, `factory.py`, `circuit_breaker.py`, `docker-compose.osrm.yml`, flags do `config.py`), não da spec prometida; presente em `docs/routing/osrm.md` (§8.11) |

---

## 4. Decisões que precisam de você

| # | Decisão | Opções |
|---|---|---|
| **1** | ~~**C1** — 10 rotas WhatsApp sem consumidor~~ | ✅ **DECIDIDO 2026-10-14: EXPOR** (12 rotas, não 10). Manter a arquitetura de 3 camadas |
| **2** | ~~**C3** — lote de 744 contatos~~ | ✅ **DECIDIDO/EXECUTADO 2026-10-19: RENOMEAR** (mapeamento manual, sem Ollama) — 275 aplicados, §6.2 |
| **3** | ~~**C2** — escopo do renomeador Fase 3/4~~ | ✅ **DECIDIDO 2026-10-19: MANTER ESTADO ATUAL** — 5 recomendações aprovadas, §8.30 |
| **4** | ~~**A4** — persistir `routes`~~ | ✅ **DECIDIDO/EXECUTADO 2026-10-19: PERSISTIR AGORA** — `route_plan_records` em SQLite, §8.28 |
| **5** | **D7** — validações V.1/V.2/V.3 | quando/executar em que máquina (VM + celular real) |
| **6** | ~~**E1–E4** — dívida diferível~~ | ✅ **executada 2026-10-15** (Onda A, gate verde §9) — escopo fechado, nada junto de correção |
| **7** | ~~`_legado_raiz/wwebjs_auth.legado.zip` (351,9 MB)~~ | ✅ **APAGADO 2026-10-19** — fora do git, sessão regenerável por QR |
| **8** | ~~`backend/gasflow.db.backups/` (5 cópias)~~ | ✅ **APAGADO 2026-10-19** — dev DB, cópias dispensáveis |

---

## 5. Plano de resolução — ondas A, B, D, E executadas; C, F, G pendentes

Regra: **uma onda por vez, cada uma termina com suíte verde + commit.**

| Onda | Escopo | Esforço | Pré-requisito |
|---|---|---|---|
| **A** | **Dívida E1–E4** (except silenciosos, pino, complexidade, F841) — ✅ **concluída 2026-10-15**, gate completo verde (§9) | ~~~1 dia~~ ✅ | nenhum |
| **B** | **CI**: ✅ **concluída 2026-10-14** — B1 ✅ (E2E medido 2:12, não >45 min) · B3 ✅ (`gh` instalado e autenticado) · B2 ✅ (11 mergeados / 2 fechados) · I2 ✅ (lint no job do whatsapp) · **B4 ✅ (cobertura desktop, 152 testes + job CI, §8.28/§8.30)** · B5 → bloqueio externo D5 (reavaliar 2027-01) | ~~2–3 h~~ ✅ | `gh` |
| **C** | **Decisões de produto**: C1 ✅, C3 ✅, **C2 ✅** | ✅ **concluída 2026-10-19** | — |
| **D** | **Segurança residual** (H1–H4) — ✅ **executada 2026-10-15**: H1/H2/H3 **já estavam no código** (verificação com evidência em §3-H); H4 apertado de **53 → 31 módulos** no baseline mypy (610 → 566 erros strict, 17 módulos corrigidos de fato + 5 que já estavam em 0). **Modelos migrados em 2026-10-16** (Onda D/H4 — §8.24): strict 566 → 165; **consumidores fechados na sequência (§8.25): 165 → 0 e o baseline apagado** — `mypy app` strict total, 0 seções | ~~~1 dia~~ ✅ | — |
| **E** | **Qualidade FE**: I1 telas sem teste, I3 favorite_product, I4 Event Bus — ✅ **concluída 2026-10-19**: I3 **já estava implementado** (medido, §3-I); I4 **fechado** no backend **e** no consumidor frontend (§3-I); **I1 telas fechado** (8 testes dedicados, 463→499); **I1 transversal permissão/offline fechado** (§8.26, 499→520) | ~~~1 dia~~ ✅ | — |
| **F** | **Validações live**: G1–G9 + D7 | imprevisível | **credenciais/VM/celular (§4 nº 5)** |
| **G** | **Limpeza restante** (§6.3) — ✅ **concluída 2026-10-19**: logs, `__pycache__` (86 pastas) e caches `.mypy/.pytest/.ruff` apagados (~75 MB); zip 351 MB e `gasflow.db.backups/` apagados (§4 nº 7–8) | ~~30 min~~ ✅ | — |
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

### 6.2 Pendência C3 — **fechada em 2026-10-19**

| | |
|---|---|
| Lote | **744 contatos** (não 8.601), todos reconciliados 744/744 contra o DB |
| Decisão | **Renomear** — sem Ollama: mapeamento antes→depois gerado manualmente (regras conservadoras: só reestrutura com logradouro do lexicon + número real; sem endereço → mantém o nome limpo) |
| Artefato | `data/renomeador-ia-c3.json` — 711 nomes distintos `{excluir, nome, nome_final_contato, …}` |
| Resultado | 20 descartados (sujeira de teste) · 92 com endereço reestruturado · 174 só limpeza (prefixo legado/emoji/espaço) · 425 já limpos (sem mudança) — 275 alterados + 469 já com nome final igual ao atual |
| Aplicação | `renomear_agenda_local.py --from-file` (modo novo): **275 contatos renomeados**, 0 sem resposta, 32 excluídos pela §4 |
| Verificação | 0 contatos ainda com nome antigo no DB; backup + relatório em `export/renomear-agenda-*-{backup-,}20261019-*.json` |
| Testes | `backend/tests/test_renamer_from_file.py` (5 testes) — verde |

### 6.3 Limpeza restante — situação em 2026-10-19

| Caminho | O que é | Status |
|---|---|---|
| `backend/$(mktemp -u).db*`, `backend/_import_test.db` (**178 MB**), `_integrity_recon.db*`, `_login_test*.db*`, `ci-boot-test.db*`, `gate_fresh.db*`, `gate_legacy.db*`, `test_matrix.db*`, `test_migration.db`, `test-desktop.db*`, `gasflow.db.legacy` | resíduos de teste / banco legado | ✅ **já não existem no disco** (verificado 19/10) |
| `backend/*.log` (`pytest-ondaD-h4.log`, `pytest-ondaD2.log`, `_ia_full.log`, `_onda_e_pytest.log`, `dev.log`, `full_run.log`, …) | logs | ✅ **apagados em 2026-10-19** |
| `compose-e2e-run.log`, `compose-e2e.log` | logs na raiz | ✅ **apagados em 2026-10-19** |
| `backend/__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` | caches regeneráveis | ✅ **apagados em 2026-10-19** (renascem sozinhos no próximo gate) |
| **manter** | `backend/gasflow.db` (dev), `backend/.venv-ci/` | — |
| **decisão pendente (§4 nº 7–8)** | `_legado_raiz/wwebjs_auth.legado.zip` (**351,9 MB**) · `backend/gasflow.db.backups/` (5 cópias, 6,2 MB) | ⏳ **aguardando confirmação** — não toquei |

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

20. **Um teste pode consagrar uma lacuna como se fosse decisão.** `tests/test_realtime.py` tinha, sob o comentário *"Unrelated events are NOT bridged to WS"*, a asserção `assert EventType.PAYMENT_CONFIRMED not in subscribed` — e o doc I4 dizia a mesma coisa ("`payment.*` fora do Event Bus"). Doc e teste concordavam entre si, então nada acusava problema; enquanto isso o `EventType.PAYMENT_CONFIRMED` estava **definido e sem publisher**, com o prefixo `payment` fora da assinatura da ponte: confirmar pagamento não acendia nada no painel e nenhum gate reclamava. Mesma familia dos outros itens desta auditoria — **concordância entre doc e teste não é evidência de que o comportamento é desejado**; quem decidiu foi o `RT01_DECISION` (P2+), e a Onda E/I4 fechou a lacuna (asserção invertida para `in subscribed` + caso negativo movido para `DISPATCH_ASSIGNED`, que segue fora por decisão).
21. **O maior bloco de dívida de tipagem tem UMA causa raiz, e ela é de model, não de consumidor.** Medido em 2026-10-15 (Onda D/H4): removendo o bloco `ignore_errors` do `mypy.ini` e rodando `mypy app`, saem **610 erros em 53 módulos**. A esmagadora maioria é do mesmo formato — `Argument "codigo" to "Product" has incompatible type "Column[str]"; expected "str"`: model declarado no estilo legado (`x = Column(String)`) faz o mypy tipar o **atributo da instância** como `Column[...]`, e aí cada consumidor (repositório, API, use case) vira erro. São **572 declarações `Column(` em 21 modelos**; os **5 modelos novos** (`contact_job`, `coupon`, `driver_stock`, `ibge`, `print_job`) já nasceram em `Mapped[...]` justamente porque a regra "arquivo novo nasce verificado" empurrou todo mundo para o estilo novo. Consequência prática: consertar consumidor por consumidor é trabalho O(nº de consumidores); migrar os 21 modelos para `Mapped[X] = mapped_column(...)` é O(nº de colunas) **uma vez** e resolve a maior parte dos 566 de uma vez. Foi essa medição que definiu o recorte do H4 nesta onda (17 módulos de erro pequeno e de causa **não-model**), em vez de raspar 610 erros à mão.
22. **O mypy estava segurando 6 bugs de runtime, não só ruído de tipo.** Cada um dos achados abaixo foi erro de mypy em módulo que estava no baseline `ignore_errors = True` — o gate verde escondia todos: (a) `application/reorder/service.py:67` ordenava pedidos por `created_at` **sem tratar `None`** → `TypeError` no meio do cálculo de reorder; (b) `application/security/auth_service.py:421` chamava `session.expires_at.isoformat()` direto, e `expires_at` é `Optional` → `AttributeError` no login de sessão sem TTL; (c) `application/financial/use_cases.py:291` estornava passando `payment.id` (que é `int | None`) para `update_status` sem guard → estorno de pagamento não persistido quebrava depois de já ter mexido no estado; (d) `application/segmentation/service.py:63` dividia por `total_orders` sem checar `None` (a comparação `> 0` era com `None`); (e) `application/automation/workflow_engine.py:418` guardava `str` numa variável depois de `float(value)` no `except ValueError` — a condição com valor não numérico ia com o tipo errado; (f) `application/whatsapp/use_cases.py` **não era nem importável** (`ImportError: cannot import name 'WhatsAppRepository'`) e, se fosse, criava pedido sem `order_item_repo` e lia `order.value` (atributo inexistente — é `order.total`), ou seja: o bot de pedidos falharia em toda criação de pedido, engolido pelo `except Exception` do fluxo. Todos corrigidos (o (f) por remoção — ver §8.23).
23. **`application/whatsapp/use_cases.py` era código morto que não importava, e o silêncio era enganoso.** Prova: `python -c "import app.application.whatsapp.use_cases"` → `ImportError` na linha 20 (`WhatsAppRepository` não existe em `app/domain/whatsapp/repository.py`, só `ConversationRepository`/`ConversationMessageRepository`), e **nenhum** arquivo de `app/`, `tests/` ou `scripts/` importa o módulo nem cita `HandleIncomingMessageUseCase`/`SendManualMessageUseCase`/`GetConversationUseCase` — o fluxo vivo é `application/whatsapp/gateway.py`. O `vulture` não denuncia isso: por padrão ele não acusa módulo inteiro não importado, então o item E4 ("vulture 0 findings") ficava verde **sobre um módulo que não podia nem ser importado**. Removido via `git rm` (recuperável: `git show <commit-anterior>:backend/app/application/whatsapp/use_cases.py`). Lição: **gate de dead code por arquivo, não só por símbolo** — um `python -c "import app.<modulo>"` por módulo, ou um teste de fumaça que importe todos os módulos de `app/`, pega o que o vulture não vê.
24. **A migração dos 22 modelos para `Mapped[...]` fez o que a medição previa — e o único cuidado real era o schema.** Executado em 2026-10-16 (Onda D/H4): os 22 arquivos de modelo saíram de `x = Column(...)` para `x: Mapped[X] = mapped_column(...)`. O strict do mypy caiu de **566 erros em 31 módulos para 165 erros em 21 arquivos** — ~400 eram o padrão `Column[str]`, resolvidos de uma vez. Regra que governou a migração: a **nullability da anotação tem de reproduzir a do modelo legado/Alembic** (`test_migrations_schema_alignment:150` compara `model.nullable` com o banco em toda coluna; e `mapped_column` *deriva* `nullable` da anotação) — legado `Column(String)` sem `nullable=` é `Mapped[Optional[str]]`; PK e `nullable=False` são `Mapped[str]`. Numeric virou `Mapped[Any]` (convenção do `coupon_model.py`). Só 2 consumidores quebraram e ambos eram **bugs latentes reais** (família do §8.22): `finance_reports` chamava `due_date.date()` num recebível com `due_date` possivelmente NULL (estouraria no relatório de fluxo de caixa), e o `cash_balance` do dashboard era inferido `int` recebendo `float`. 7 módulos ficaram em 0 e tiveram a seção removida do baseline. Os 165 restantes eram consumidores reais, não ruído de model — fechados em §8.25.
25. **A onda final de consumidores: 165 → 0, e boa parte era bug latente de runtime, não ruído de tipo.** Executada em 2026-10-16, fechando o H4: o bloco `ignore_errors` do `mypy.ini` foi **apagado por inteiro** e `mypy app` roda strict em 335 arquivos com **0 erros**. Os blocos: (a) `application/client/use_cases` 36 — eram **36 erros numa única linha**, porque ao dict `result` faltava a anotação e o mypy inferiu a união dos valores (str/None/int/float/datetime), quebrando a aritmética de `total_spent - outstanding`; `result: Dict[str, Any]` resolve. (b) `whatsapp/gateway` 34 + API 4 — o `id` da entidade `Conversation` é `Optional[int]` e era passado a repositórios que exigem `int`; nova propriedade `Conversation.persisted_id`, que **estoura cedo** em vez de mandar `None` silenciosamente ao SQL. (c) `whatsapp_automation` service/executor 12 — `seg_repo.get_segment` **não existia** (o método é `find_by_id`); `rule.id`/`exec.id` Optional; `strftime` em data possivelmente nula; dict `results` sem anotação. (d) `operations`/`dispatch`/`delivery_ops`/`driver_api` 37 — **a família §8.23 de novo**: o código chamava `driver.status`/`driver.name`/`driver.vehicle_id`/`driver.is_available`/`driver.to_dict`/`driver.update_location` na **entidade de domínio** `DeliveryDriver`, que modela só `codigo/nome/telefone/placa/ativo`. Esses atributos são do **model**, não da entidade — ou seja, `GET /operations/map/drivers`, o dashboard operacional, `list_drivers` e `PATCH /drivers/{id}/location` **davam 500 em runtime** (AttributeError), e o baseline escondia; o mypy strict foi o que os expôs. Correção: ler os campos de model via `SQLAlchemyDeliveryDriverRepository.snapshot(codigo)`/`find_by_id_as_model` (a API que o próprio `delivery_repository` documenta como destinada às respostas de API) e **remover a mutação fantasma** (`driver.update_location` — a posição real vive na tabela de GPS, via `loc_repo.upsert_location`). Também: `delivery_ops` importava `SQLAlchemyDeliveryDriverRepository` do **módulo errado**; um `engine = DispatchEngine(...)` local **sombreava o engine do banco**; e dois `latest = ...` trocavam `DriverLocationRecord` por `DriverLocationHistoryRecord` — extraído para o helper `_latest_driver_position`, que também devolveu o `C901` a ≤10.

26. **Estados de permissão/offline unificados no FE (I1/P2, Onda E) — fechado em 2026-10-19.** Um único classificador `src/lib/api/failure.ts` (`classifyRequestFailure`: `response.status === 403` → "Sem permissão"; outro status HTTP → "Algo deu errado"; sem `response` → "Sem conexão"; nulo/booleano → genérico, de propósito: um `true` legado não carrega informação e não pode mentir "Sem conexão" no meio da migração) + `<ErrorState error?: unknown>` que escolhe o título sozinho (sem a prop, o título genérico antigo — comportamento retrocompatível). O `PermissionRoute` deixou de fazer `<Navigate to="/" />` silencioso e passou a renderizar a tela `PermissionDenied` ("Sem permissão"); a sidebar permanece porque todas as rotas protegidas ficam dentro do `DashboardLayout`. Adoção nos **41 sites de `ErrorState` (37 arquivos)**: `useState(false)` → `useState<unknown>(null)`, `setError(true)` → `catch (err) { setError(err) }`, `<ErrorState error={error}>`; onde o estado guardava só a mensagem (`DriverFormPage`, `ReorderPage`, `AutomationsPage`), um segundo estado `failure` guarda o objeto e a mensagem original fica intacta. A financeira foi a mais profunda: `useVisaoGeralData`/`useAnalyticsData` setam o `.reason` do `Promise.allSettled`, `sectionState()` devolve o próprio objeto e `SectionShell` o repassa. Duas réplicas de guard em teste (`AuditPage.test.tsx`, `PurchaseNotesPage.test.tsx`) foram atualizadas para asserir o estado (não mais o redirecionamento). Gate: `tsc` 0, `eslint` 0, `vitest --maxWorkers=2` **520 passed / 88 files** (499 → 520: +21 testes — classificador, `ErrorState`, `PermissionDenied`, `PermissionRoute`).

27. **A4 — persistência do plano de rota otimizado (2026-10-19).** O resultado da otimização (Fase 8) era efêmero: HTTP response + evento em memória (ring buffer de 1000). Reiniciar o backend perdia a ordem otimizada. Implementado: tabela `route_plan_records` (upsert por `(tenant_id, driver_id)`, `plan_version` incrementa a cada save), migração `a4b5c6d7e8f9` (head único), `SQLAlchemyRoutePlanRepository` (TenantMixin — leituras sempre tenant-scoped), save best-effort nos dois caminhos (`POST /delivery/route/optimize` → `source="ENDPOINT"`, `_try_optimize_after_assign` → `source="ASSIGN"`, ambos em try/except que degrada para debug log, nunca 500), `GET /delivery/route/plan/{driver_id}` (404 quando não há plano). Allowlist de integridade: `route_plan_records` em `tests/integrity_allowlist.json`. 13 testes de persistência (upsert, tenant isolation, restart survival, geometry JSON round-trip) + 176 de regressão (delivery, persistence, cross-tenant). Flag `DELIVERY_SMART_ROUTING_ENABLED` continua default false — tabela fica vazia até a flag ligar.

28. **B4 — cobertura desktop: 71 → 101 testes + job no CI (2026-10-19).** A premissa "só fumaça" estava desatualizada (11 arquivos, 71 testes, `node:test` via `tsx --test`, miram `dist/`). Os gaps reais fechados: parsers puros do `ai-service` (`extractJsonBlock` com fences/balanceamento, `parseMoney` pt-BR, `coerceOrder` com aliases e hash determinístico, `parseOrdersJson` com pedidos mistos), idempotência do `registerUpdateIpc` (segunda chamada não duplica handlers), guard do `setupAutoUpdate` (dev não empacotado não configura nada), settings.json corrompido (JSON inválido e não-objeto caem nos defaults e regeneram chaves), canais do updater no preload (`update:check`/`install`/`state`). Job `desktop` adicionado ao `ci.yml` (typecheck + build + test). Ainda sem teste: `index.ts` (743 linhas — single-instance/second-instance/activate), dedupe do assistant, backend-bridge — diferíveis. O IPC do updater e o agent-bridge foram cobertos na continuação de 20/10 (§8.30).

29. **C2 — escopo do renomeador Fase 3/4: mantido o estado atual (2026-10-19).** As 5 recomendações do §12 da spec (`prompts/renomeador-contatos-fase3.md`) foram aprovadas: (1) cidades Belém-only; (2) aceitar lacuna CNEFE 2022 sem endereço pós-censo; (3) Faces em versão preliminar com re-ingestão idempotente; (4) gate 10k; (5) PontoFato ligado com toggle break-glass. Verificado no código: Fase 3 (IBGE/CNEFE) já em produção (migração `9f4b7e2a6c31`, `IbgeEntreRuasProvider`, wire-up em `jobs.py:318-320`, gate D20 aprovado); PontoFato ligado (`pontofato_enabled: true` em `config.py:300`, usado em `cep.py:192`).

30. **B4 (continuação) — helpers puros do main process e protocolo do agente (2026-10-20).** `desktop/src/main/index.ts` inicia o Electron no require, então nada nele é importável num teste. As decisões de configuração/formatação foram extraídas para `desktop/src/main/app-helpers.ts` (sem dependência de Electron, `fs`/`path` injetados): `backendPort`/`backendUrl`/`waBaseUrl`, `sqliteDatabaseUrl`, `resolveFrontendDist`, `resolvePython` (empacotado → venv → PATH), `sanitizePdfFilename` (fallback para vazio, não só não-string), `isSessionToken`, `TEST_RECEIPT_ESCPOS` e `planServices` (whatsapp/assistant/printer/painel/relay). O boot passou a usar `plan.*` também no relay, eliminando a última checagem de flags duplicada. Testes novos: `app-helpers.test.ts` (24), `agent-bridge.test.ts` (18 — correlação de id, buffering de JSON-lines, eventos, stderr, exit e **spawn que falha**, que antes deixava `running=true` fantasma e `pending` sem resposta), `updater-ipc.test.ts` (7 — os 3 canais, idempotência e conversão de erro) e `backend-wa-spawn.test.ts` (2 — mesmo bug de spawn no `BackendBridge`/`WhatsAppBridge`, que esperavam o health check inteiro antes de falhar). **Desktop 101 → 152 testes**, `tsc`/build limpos; CI inalterado (o job `desktop` já roda a suíte inteira).

31. **Telas órfãs e gate de links (2026-10-20).** Duas rotas internas existiam em `App.tsx` e em `features/` e **não tinham nenhuma entrada no menu**: `/automation` (WorkflowsPage) e `/settings/integrations` (IntegrationsPage). O gate de integridade não acusava porque `_nav_link_findings` deixava o link da raiz (`/`) cobrir todas as rotas por prefixo — `"/automation".startswith("/")` é sempre true — e ainda ignorava o alvo exato (`target != route`). Corrigido nos dois pontos, com testes de regressão (`test_nav_link_findings_*`), e as duas telas entraram no grupo **Configurações** do menu. As 4 rotas que restam no allowlist são legítimas e declaradas: `/cadastro` (convite público), `/track/*` (rastreio enviado ao cliente), `/reports` e `/reports/heatmap` (redirects legados para `/finance`). Na mesma onda: **Integrações** ganhou resumo (ativas/desativadas/com erro) e o botão **Sincronizar todas** consumindo o `POST /integrations/sync-all` que existia sem tela (teste de contrato em `test_integrations.py`); **Automações (workflows)** ganhou resumo de execuções ativas, aprovações pendentes e workflows definidos. Na mesma data, a ficha do cliente ganhou o card **Privacidade e LGPD**: exportação em JSON (`POST /clients/{codigo}/export`) e anonimização (`DELETE /clients/{codigo}/data`) com confirmação pelo código do cliente, permissões `customer.write`/`customer.*` e feedback de 403/404. Gate: FE **528/90** (+5 do card LGPD), integridade **11/0** (allowlist 14/14), `tsc`/lint limpos; backend LGPD **10/10**.

---

## 9. Gate de verificação

**Última execução completa: 2026-10-20** (backend + frontend + whatsapp + desktop + ruff/mypy/vulture/alembic/integridade), sobre o baseline verde de 2026-10-16 (§8.8/§8.9).

> **Reconferência de 2026-10-20** (checks rápidos + frontend/whatsapp/desktop):
> `ruff` limpo · `mypy app` strict **0 em 337 arquivos** · `vulture` 0 ·
> `alembic heads` único `a4b5c6d7e8f9` · `vitest --maxWorkers=2` **528/90** ·
> `whatsapp npm test` **106/0** · `desktop typecheck/build/test` **152/0** ·
> `tsc` e `eslint` limpos no FE. A suíte completa de backend também foi reexecutada
> nesta data: **2310 passed / 30 skipped / 0 failed** em 1676 s.

| Check | Resultado |
|---|---|
| `ruff check app tests scripts` (agora com `C901` ≤ 10, `ARG` e `F841` no `select`) | All checks passed — **C901 44→0, ARG 119→0, F841 36→0** |
| `mypy app` (**strict total** — bloco `ignore_errors` apagado em 2026-10-16) | Success: **0 issues in 335 files** |
| `mypy` **sem o baseline** (medida do strict real, Onda D/H4) | **610 → 566 → 165 → 0 erros** (53 → 31 → 21 → **0 módulos**); o bloco `ignore_errors` do `mypy.ini` foi **apagado por inteiro** em 2026-10-16 — o `mypy app` agora É o strict (§8.24/§8.25) |
| `python -m vulture app --min-confidence 80` | **0 findings** (era 1: `raise` duplicado em `client_repository.py`) — re-rodado na Onda D após remover o módulo morto: ainda 0 |
| `pytest -q -p no:randomly` | **2310 passed / 30 skipped / 0 failed** — medido **2026-10-20 em 1676 s** (pós-A4: +18 testes). Histórico: 2292/30 em 964 s no gate de 2026-10-16 (Onda D/H4), 859 s na Onda A e 1627 s na Onda D — mesma suíte; diferença de tempo é variância de carga da máquina, não regressão |
| `alembic heads` | head único **`a4b5c6d7e8f9`** (migração A4; era `c1a2b3d4e5f6` até 19/10) |
| `frontend: vitest run --maxWorkers=2` | **528 passed / 90 files / 0 errors** — medido **2026-10-20** após a onda de navegação/telas (+8: `nav.test.tsx` 2, resumo/sync-all em `IntegrationsPage` 1, card LGPD 5). Antes: 520/88 em 19/10 (Onda E/I1), 499/84 em 16/10 e 463/76 antes dos 8 testes dedicados do I1 |
| `whatsapp: npm test` | **106 passed / 0 failed** — medido 2026-10-15 e **repetido 2026-10-19** (94 s) |
| `desktop: npm run typecheck` (baseline 2026-10-14) | exit 0 |
| `desktop: npm test` (baseline 2026-10-14, atualizado 2026-10-20) | **152 passed / 0 failed** |
| `tests.integrity_audit` | findings=**11** / **pendentes=0** (allowlist 14/14; inclui os 4 links públicos/redirects declarados em §8.31) |
| CI no `main` (run `bb4f26d`, 2026-10-14) | **6/6 jobs verdes em 8 min 36 s** (E2E 2:12, Backend 5:51) — ver §8.16 |
| CI no `main` combinado (run `991db31`, 2026-10-14, após 11 merges de deps) | **6/6 jobs verdes em 14 min 46 s** — ver §8.17 |
| CI no `main` (run `38914204555`, 2026-10-16 — mypy strict + onda de consumidores) | **6/6 jobs verdes em 9 min 48 s** (Backend 7:11, Trivy 2:31, Frontend 1:26, Migrations 0:54, WhatsApp 0:27, Agent 0:12); `E2E` 2:06 e `Build & Push Images` 1:45 verdes |

```bash
cd backend
.venv-ci/Scripts/python.exe -m ruff check app tests scripts   # inclui C901<=10, ARG, F841
.venv-ci/Scripts/python.exe -m mypy app
.venv-ci/Scripts/python.exe -m vulture app --min-confidence 80
.venv-ci/Scripts/python.exe -m alembic heads                   # head único c1a2b3d4e5f6
.venv-ci/Scripts/python.exe -m pytest -q -p no:randomly        # ~28 min nesta máquina
ADMIN_PASSWORD='<sua>' .venv-ci/Scripts/python.exe -m tests.integrity_audit   # espera 11/0
cd ../frontend && npx vitest run --maxWorkers=2                # OBRIGATÓRIO nesta máquina
cd ../whatsapp && npm test
cd ../desktop && npm run typecheck && npm test
cd .. && npm run evidencias                                     # e2e/ (opcional)
```
