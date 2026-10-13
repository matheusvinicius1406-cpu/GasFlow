# Plano Master — Pendências & Limpeza (GasFlow)

**Criado:** 2026-10-13
**Baseline:** `main` @ `33b7de0` ("fix(multiempresa): P0 de isolamento …", 2026-10-12)
**Última release:** tag `v1.2.0` (desktop/frontend/mobile em `1.2.0`)
**Working tree:** limpo
**Método:** últimos 40 commits + `CHANGELOG.md` + docs de status/auditoria/segurança/CI/roadmap
cruzados **contra o código** (vários docs estavam desatualizados — ver §2).

> Este documento é a fonte única das pendências. A ordem de execução é §5 (ondas).
> Nada é apagado/commitado sem confirmação (§7).

---

## 0. Progresso da execução (atualizado 2026-10-13)

| Onda | Item | Status | Evidência |
|---|---|---|---|
| 0 | Baseline do gate | ✅ | backend baseline **2277 passed / 30 skipped / 2 failed** (as 2 eram bug pré-existente, corrigido); frontend 452; whatsapp 106; ruff/mypy/alembic-head verdes |
| final | Suíte após as mudanças | ✅ | backend **2291 passed / 30 skipped / 0 failed**; integridade **9 findings / 0 pendentes**; allowlist 9/9 |
| 1 | A1 — 10 rotas `SOMENTE_DB` | ✅ auditadas | Todas públicas por design (token de integração / refresh rotativo / convite assinado + rate limit). Registrado em `docs/seguranca/RELATORIO-2026-10-09.md` |
| 1 | A2 — `/webhooks/alerts` | ✅ | `ALERTS_WEBHOOK_SECRET` + gate 401/503; 11 testes; Alertmanager/compose/env documentados |
| 2 | A3 — `init_db` × Alembic | ✅ | Banco vazio bootstrapa por `alembic upgrade head`; testes em `test_init_db_alembic_boot.py` |
| 2 | Bug extra — backup A.3 no Windows | ✅ | `str(engine.url)` percent-encodava o caminho; trocado por `engine.url.database`. `test_schema_migration` 6/6 (era 2 falhas) |
| 3 | F1/F3/F4 — docs | ✅ | `desktop/README.md`, `FINAL_SYSTEM_STATUS.md`, `GASFLOW_CURRENT_STATE_REPORT.md` atualizados |
| 3 | B1 — E2E no CI | ⚠️ config ok | `e2e.yml` já tem cache do Chromium + steps com timeout; falta confirmar o tempo numa run real |
| 3 | B3 — `gh` CLI | ⏳ manual | Ferramenta da máquina, não do repo |
| 4 | C1 — rotas WhatsApp sem consumidor | ✅ | 10 rotas expostas pelo proxy (`whatsapp/accounts.py`); gate **9 findings / 0 pendentes** (era 19); allowlist limpa |
| 4 | C3 — camada de IA do renomeador | ✅ piloto | Dry-run com `qwen3:1.7b`: 5840 contatos, **0 alterações pendentes** no determinístico, 744 elegíveis à IA. Aplicação em massa é batch operacional |
| 5 | Limpeza | ⏳ aguardando revisão item a item (§6.1) | |

**Ainda aberto:** B2/B4 (CI/dependabot), C2 (escopo do renomeador), D (externos/legal), E (dívida diferível) — ver §3.

---

---

## 1. Sumário executivo

O produto está funcionalmente pronto para produção (suíte backend na casa dos
**2.2k testes**, 4 pacotes cobertos por CI, releases `v1.x` publicadas, RBAC +
multiempresa isolados por tenant). O que resta **não** é "terminar o produto":
é (a) um resíduo de segurança/consistência de authz, (b) a dívida de
`create_all` × Alembic, (c) decisões de produto/externas que já estavam
registradas como bloqueios, e (d) **higiene do workspace** (protótipo antigo e
lixo de teste ocupando disco fora do git).

Não existe, no estado atual, nenhum P0 de código aberto conhecido.

---

## 2. O que os docs davam como aberto e **já caiu** (não repetir)

| Item de doc antigo | Fonte | Realidade verificada |
|---|---|---|
| Auth in-memory, `admin123`, PaymentService in-memory | `GASFLOW_CURRENT_STATE_REPORT.md` (29/08) | Fechados em Fases 15.3/P0 (auth→DB, `ADMIN_PASSWORD` obrigatório). |
| 528 erros mypy / sem CI / sem docker-compose.prod | `AUDITORIA.md` (10/09) | mypy **0 erros** (299+ arquivos), CI e `docker-compose.prod.yml` existem. |
| Fontes do desktop inexistentes (só `dist/`) | `AUDITORIA.md` A11 | Onda 4 migrou `dist/main/*.js`→`src/main/*.ts`; **mergeada** na `main`. |
| Escopo por tenant em conversas/workflows (P0) | `RELATORIO-2026-10-09.md` | **Resolvido** no commit `33b7de0` (migração `c1a2b3d4e5f6`, 37 testes cross-tenant). |
| `test_routing_optimizer::test_reordena_com_ganho_real` falhando | `RELATORIO-2026-10-09.md` | **Passa** hoje (8/8) — OR-Tools presente no ambiente. |
| PIX estático, Ollama, Whisper, Piper "não implementados" | `GASFLOW_CURRENT_STATE_REPORT.md` | Implementados: `app/domain/payment/pix_service.py`, `infrastructure/ai/ollama_provider.py`, `infrastructure/audio/{whisper,piper}_provider.py`. |
| mypy 4 erros no renomeador | `RELATORIO-2026-10-09.md` | Corrigido (`215238d`). |

**Lição:** tratar qualquer doc com data < 2026-10-09 como histórico; a verdade é
o código + `CHANGELOG.md` + relatórios de 09/10.

---

## 3. Inventário de pendências reais

### A. Segurança / consistência de authz (ação de código)

| # | Pendência | Evidência | Esforço | Aceite |
|---|---|---|---|---|
| A1 | **10 rotas `SOMENTE_DB`** sem credencial no router (`POST /auth/mobile/*`, `POST /integrations/import`, `POST /public/referral/*`, …) | `docs/seguranca/RELATORIO-2026-10-09.md` §"Pendências" #2 | S | Cada rota classificada (pública-por-design com justificativa **ou** gate adicionado) e refletida na matriz de rotas; testes negativos. |
| A2 | **`POST /webhooks/alerts` sem validação de origem** — só loga; exposto = spam/DoS de log | `backend/app/presentation/api/alerts_webhook.py` (docstring admite a dívida) | S | Header secreto (`X-Alert-Secret`, `hmac.compare_digest`, fail-closed sem env) **ou** restrição por IP documentada no reverse proxy + teste 401/200. |
| A3 | **`init_db` ainda usa `create_all()` sem gravar `alembic_version`** — banco de dev/testes nasce por `create_all` + `_ensure_sqlite_columns`, em paralelo ao Alembic → risco de drift "funciona no dev, quebra no Postgres" | `init_db.py:597` (`create_all`); `SCHEMA_VERSION` é um contador separado | M | `create_all` deixa de ser o caminho primário em dev (ou passa a `stamp head` no fim), com o drift guard do `docs/migrations.md` cobrindo o caso; teste de boot verde. |
| A4 | **`routes` (planos de rota) só em memória** | `FINAL_SYSTEM_STATUS.md` (Category A) / Fase 21 | M | Persistir em `route_plans` **se** a Fase 21 (multi-stop com restart) entrar. Bloqueado por produto — não fazer antes. |

### B. CI / Release

| # | Pendência | Evidência | Esforço | Aceite |
|---|---|---|---|---|
| B1 | **E2E no CI >45 min** (instalação de deps travando o job) | `docs/ci/RELATORIO-CI-2026-10-09.md` | S | Já mitigado (`e2e.yml` com cache do Chromium, steps separados, `timeout-minutes`). Confirmar tempo real < 15 min numa run verde. |
| B2 | **PRs do Dependabot vermelhos** (TS 7 no `whatsapp`, ESLint 10, etc.) | 25+ branches `dependabot/*` | S–M | Depende de upstream (D2 abaixo). Enquanto isso: fechar/ignorar as PRs inviáveis **explicitamente** para limpar a lista. |
| B3 | **`gh` CLI ausente** impede ler logs de job (diagnóstico às cegas) | `RELATORIO-CI-2026-10-09.md` (próximos passos) | S | `gh` instalado+autenticado na máquina de dev. |
| B4 | **Testes do desktop** cobrem só fumaça (updater/config/preload) | `FALHAS.md` / `EXECUCAO_FINAL.md` | M | Ampliar quando o Electron evoluir. Diferível. |

### C. Decisões de produto

| # | Pendência | Evidência | Aceite |
|---|---|---|---|
| C1 | **D3 — 10 rotas do serviço WhatsApp sem consumidor** (`/lists/*/contacts`, `/customers/sync`, `/campaigns/*/preview`, …) | `integrity_allowlist.json` (`whatsapp-sem-consumidor`) | Decisão: expor (criar tela) **ou** remover. Hoje ficam na allowlist com motivo (gate `19/0`). |
| C2 | **Renomeador Fase 3/4 — pendências abertas**: cidades além de Belém (só `default_city` Belém), CNEFE é de 2022 (endereço novo pós-censo não entra), Faces "versão preliminar" (re-ingerir quando sair a definitiva), alvo 10k×20k, PontoFato (3º elo CEP) desligável | `docs/prompts/renomeador-contatos-fase3.md` §12 | Definir qual dessas entra; o resto fica registrado. |
| C3 | **Lote pendente de renomeação de contatos** — `_pendentes_ia.json` (8.601 contatos) + `_pend_part1..4.txt` (artefatos no diretório-pai) | raiz do workspace | Decidir: rodar a camada de IA sobre o lote, arquivar ou descartar. |

### D. Bloqueios externos (não se resolvem com código)

| # | Pendência | Evidência | O que destrava |
|---|---|---|---|
| D1 | **B7 — Fiscal NFC-e** | só menções "sem SEFAZ" no código | Certificado A1 + credenciamento SEFAZ + decisão contábil. MVP: deep link NFF + dados locais. |
| D2 | **B8 — LGPD/CLT do app do entregador** | backend de localização já existe | Documento jurídico antes de soltar o app. |
| D3 | **Assinatura do instalador Windows** (`NotSigned`, SmartScreen) | `FALHAS.md`; `release.yml` exige os secrets | Certificado de code-signing emitido por CA confiável. |
| D4 | **5 HIGH de `extract-zip`** (whatsapp → wwebjs → puppeteer) | `ROADMAP_BLOCKERS.md` D1; cadeia ainda presente | Sem versão corrigida publicada; some ao aposentar o rollback `wwebjs`. |
| D5 | **TS 7 bloqueado no whatsapp** | `ROADMAP_BLOCKERS.md` D2 | `typescript-eslint` que aceite TS 7. |
| D6 | **Shim `jest-dom-vitest.d.ts`** | `ROADMAP_BLOCKERS.md` D4 | Suporte a Vitest 5 no upstream. |
| D7 | **Validações manuais V.1/V.2/V.3** (auto-update em VM limpa, pareamento WhatsApp em celular real, release remota) | `FALHAS.md` | Execução manual com ambiente/credenciais. |
| D8 | **LGPD export/delete de dados** | `GASFLOW_CURRENT_STATE_REPORT.md` §24 | Implementação de código (M) + política. |

### E. Dívida técnica diferível (mapeada na auditoria)

| # | Item | Evidência |
|---|---|---|
| E1 | `except Exception:` silenciosos (triagem + log contextual) | `AUDITORIA.md` A5 |
| E2 | `console.log` → `pino` no serviço WhatsApp | `AUDITORIA.md` A6 |
| E3 | 19 funções com complexidade > 10 | `AUDITORIA.md` A8 |
| E4 | F841/ARG/vulture (parâmetros de interface) | `AUDITORIA.md` §3 |

> Todas **diferíveis**. Nenhuma bloqueia release. Só mexer com escopo explícito.

### F. Documentação desatualizada

| # | Item | Evidência |
|---|---|---|
| F1 | `desktop/README.md:126-134` descreve só o caminho `create_all` | `ROADMAP_BLOCKERS.md` §1.5 (aparece como corrigido em `9458730`, **re-verificar**) |
| F2 | Docs históricos com `whatsapp-web.js` marcados com banner `[histórico]`, mas `ROADMAP.md`/`AUDITORIA.md`/`GASFLOW_CURRENT_STATE_REPORT.md` ainda confundem | `docs/*` |
| F3 | `GASFLOW_CURRENT_STATE_REPORT.md` (29/08) e `AUDITORIA.md` (10/09) descrevem estado pré-correção | docs |
| F4 | `FINAL_SYSTEM_STATUS.md` cita 889 testes (hoje ~2.2k) | docs |

---

## 4. Estado de verificação (baseline a reconfirmar)

| Suíte | Documentado | Última verificação |
|---|---|---|
| Backend pytest | 2.239 passed / 30 skipped | `0089`/09-10 (25 min — caro) |
| Backend ruff / mypy | limpo / 0 erros | 09/10 |
| Frontend vitest | 441 passed | 09/10 |
| WhatsApp `node --test` | 106 pass | 09/10 |
| Desktop typecheck + testes | 11/11 | Onda 4 |
| E2E Playwright | 20 testes (19 passed/1 skip) | 08/10 |
| `integrity_audit` | `findings=19 pendentes=0` | 08/10 |
| `alembic heads` | head único `9f4b7e2a6c31` | 09/10 |
| Routing optimizer (isolado) | 8/8 | **13/10 (este plano)** |

---

## 5. Ondas de execução

Regra mantida: **uma onda por vez, cada uma termina com suíte verde + commit**.

### Onda 0 — Baseline (~30 min)
- Rodar o gate completo do projeto **uma vez** nesta máquina e registrar os números reais (§9).
- Corrigir o que estiver vermelho **antes** de qualquer feature.
- `git status` limpo ao fim.

### Onda 1 — Authz residual (A1, A2) (~2–3 h)
1. A1: classificar as 10 rotas `SOMENTE_DB`; gatear as que precisam; atualizar a matriz.
2. A2: fechar `/webhooks/alerts` (segredo ou IP) + testes.
- Aceite: `test_auth_negative_matrix` estendido, `route_matrix` regerado, ruff/mypy limpos.

### Onda 2 — Alembic/`init_db` (A3) (~3–4 h)
- Alinhar `create_all` ↔ Alembic (stamp no dev, `_ensure_sqlite_columns` como rede de compat **documentada**); atualizar `docs/migrations.md`.
- Aceite: boot de dev/teste e do exe convergem para o mesmo `alembic_version`; drift guard verde.

### Onda 3 — CI/Docs (B1, B3, F1–F4) (~2 h)
- Confirmar E2E < 15 min; instalar `gh`; atualizar `desktop/README.md` e marcar os docs históricos (F2–F4).
- Aceite: `main` verde no GitHub Actions; docs coerentes com 13/10.

### Onda 4 — Decisões de produto (C1–C3) (~ a definir)
- C1 (rotas WhatsApp), C2 (escopo do renomeador), C3 (lote pendente).
- Requer sua decisão antes de codar (ver §7).

### Onda 5 — Limpeza do workspace (§6) (~30 min)
- Apagar o protótipo antigo do diretório-pai e o lixo de teste ignorado.
- **Fora do git** — irreversível. Só após confirmação (§7).

### Onda 6 — Dívida diferível (E1–E4) — **sem prazo**
- Só com escopo explícito; nunca junto de correção.

### Bloqueios externos (D1–D8) — **fora do código**
- Acompanhar quando certificado/jurídico/upstream destravarem.

---

## 6. Inventário de limpeza (candidatos a exclusão)

### 6.1 Diretório-pai (`automação zap/`) — **protótipo antigo, fora do git**
O git real é `GasFlow/`. O pai contém o protótipo antigo do serviço WhatsApp
(descrito em `AUDITORIA.md` §2) + artefatos do renomeador. **Não rastreado** —
apagar é definitivo.

| Caminho | O que é | Ação proposta |
|---|---|---|
| `src/`, `tests/`, `node_modules/` | protótipo antigo (whatsapp-web.js single-service) | apagar |
| `wwebjs_auth/`, `.wwebjs_cache/` | **dados de sessão WhatsApp** (sensíveis!) | apagar |
| `data/`, `gasflow.db*` | DB do protótipo | apagar |
| `export/` | lotes exportados + `renomear-agenda-*.json` (~40 MB, artefatos do renomeador) | **confirmar** (pode ser histórico útil) |
| `_e2e_out.log`, `_e2e_err.log`, `server.log` | logs | apagar |
| `_pend_part1..4.txt`, `_pendentes_ia.json` | lote pendente de renomeação (C3) | **confirmar** antes de apagar |
| `package.json`, `package-lock.json`, `tsconfig.json`, `THIRD_PARTY_NOTICES.md`, `CHANGELOG-seguranca.md` | do protótipo | apagar com o resto |
| `.pytest_cache/`, `.ruff_cache/` | caches | apagar |

### 6.2 Dentro de `GasFlow/` — ignorados (não rastreados)
| Caminho | O que é | Ação |
|---|---|---|
| `backend/$(mktemp -u).db*` + `.backups/` | **bug de shell** virou arquivo literal | apagar |
| `backend/_import_test.db` (**178 MB**), `_integrity_recon.db*`, `_login_test*.db*`, `ci-boot-test.db*`, `gate_fresh.db*`, `gate_legacy.db*`, `test_matrix.db*`, `test_migration.db`, `test-desktop.db*` | resíduos de teste | apagar |
| `backend/gasflow.db.legacy` | banco legado (ver `docs/migrations.md`) | apagar |
| `backend/*.log` (`b1-pytest*`, `dev.log`, `full_run.log`, `pair_run.log`, `pip-ci-install.log`, `pytest-*.log`, `trio.log`, `uvicorn-boot.log`) | logs | apagar |
| `backend/__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` | caches | apagar (regeneráveis) |
| `backend/gasflow.db` | **banco de dev** | **manter** |
| `backend/.venv-ci/` | venv do CI | **manter** |

> `backend/gasflow.db.backups/` (5 cópias) — manter se quiser histórico; senão apagar.

### 6.3 Rastreado no git (decisão de conteúdo)
| Caminho | O que é | Ação |
|---|---|---|
| `docs/` com 119 arquivos + dirs de fase (`phase5..16`, `wave1`, `spike`, `prompts`) | histórico denso | **não apagar em massa**: consolidar/arquivar em `docs/archive/` depois (proposta separada). |

---

## 7. Decisões que preciso de você

1. **Executar o plano agora?** Em qual ordem — começar pela Onda 0+1 (código) ou pela Onda 5 (limpeza) primeiro?
2. **Deleção do diretório-pai** (protótipo antigo + `wwebjs_auth` + `data/`): confirma? E o `export/` e `_pendentes_ia.json` entram na deleção ou ficam?
3. **C1** (rotas WhatsApp sem consumidor): expor ou remover?
4. **C3** (lote de 8.601 contatos do renomeador): rodar, arquivar ou descartar?

---

## 8. Arquivos-chave de referência

- Pendências de authz: `docs/seguranca/RELATORIO-2026-10-09.md`
- CI: `docs/ci/RELATORIO-CI-2026-10-09.md`
- Bloqueios/decisões: `docs/ROADMAP_BLOCKERS.md`
- Migrações: `docs/migrations.md`, `docs/migrations/2026-09-sqlite-batch-audit.md`
- Renomeador Fase 3: `docs/prompts/renomeador-contatos-fase3.md`, `docs/adr/ADR-0008-*.md`
- Changelog: `CHANGELOG.md`

## 9. Comandos de verificação (gate completo)

```bash
cd backend
.venv-ci/Scripts/python.exe -m ruff check app tests scripts
.venv-ci/Scripts/python.exe -m mypy app
.venv-ci/Scripts/python.exe -m pytest -q -p no:randomly        # ~25 min
.venv-ci/Scripts/python.exe -m alembic heads                   # head único
ADMIN_PASSWORD='<sua>' .venv-ci/Scripts/python.exe -m tests.integrity_audit   # espera 19/0
cd ../frontend && npm test
cd ../whatsapp && npm test
cd ../desktop && npm run typecheck && npm test
cd .. && npm run evidencias   # e2e/ (opcional)
```
