# 🔍 AUDITORIA PROFUNDA — GasFlow

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).


**Data:** 2026-09-10 · **Escopo:** repositório completo (backend, frontend, whatsapp, agent, desktop, e2e)

> **✅ AÇÃO APLICADA (mesma data):** A1, A2, A3, A4, A7, A9 corrigidos; ícone
> + instalador NSIS gerados (`GasFlow Desktop Setup 1.1.0.exe`, 127 MB,
> ícone verificado no exe). Restantes: A5, A6, A8, A10*, A11, A12, A13 —
> diferidos (*A10 reavaliado: `npm test` roda e sai com 0 — só não há testes).
**Método:** vulture 2.16, ruff 0.15.22, mypy 2.3.1, tsc 5.8 (strict flags), depcheck, pip-audit, grep estrutural.

> **Fase 1 — somente diagnóstico.** Nada foi corrigido. Ações propostas aguardam revisão.

---

## 1. Resumo executivo

| # | Problema | Severidade | Categoria |
|---|----------|------------|-----------|
| A1 | `ContactsCrmPage.tsx` (UI de contatos do CRM: sync WhatsApp, import/export VCF) **não tem rota, não é importada, não tem item de menu** — funcionalidade invisível ao usuário | 🔴 ALTA | Tela inacessível |
| A2 | `python-multipart 0.0.12` com **7 advisories** (PYSEC-2026-1851/1852/3036–3040) e **ausente do `requirements.txt`** (dependência implícita do `UploadFile` do FastAPI — VCF import quebra em instalação limpa) | 🔴 ALTA | Segurança + dependência |
| A3 | `@hapi/boom` importado em `baileys-engine.ts` mas **não declarado** no `package.json` do whatsapp (funciona só por transitividade do Baileys) | 🟠 MÉDIA | Dependência |
| A4 | Desktop: **sem ícone** (`build/icon.ico` inexistente, `electron-builder.yml` sem `icon:`), sem atalho do Menu Iniciar, sem `shortcutName`/`publisherName`/`artifactName` | 🟠 MÉDIA | Empacotamento (Fase 2) |
| A5 | 25 blocos `except Exception:` + `pass` no backend — erros engolidos silenciosamente (amostra em §4) | 🟠 MÉDIA | Crash silencioso |
| A6 | 24 `console.log` no serviço WhatsApp (deveria usar `pino logger`) | 🟡 BAIXA | Logs |
| A7 | 12 variáveis locais não usadas (F841) no backend; 3 imports não usados no whatsapp; 1 no agent | 🟡 BAIXA | Código morto |
| A8 | 19 funções acima da complexidade ciclomática 10 (pior: `import_service.test_connection` = 20) | 🟡 BAIXA | Manutenibilidade |
| A9 | 3 `.catch(() => {})` no frontend (erros de promise ignorados) | 🟡 BAIXA | Crash silencioso |
| A10 | `desktop/tests/` vazio — `npm test` falha (glob sem match) | 🟡 BAIXA | Testes |
| A11 | `desktop/src/` contém apenas `placeholder.ts`; código real só existe compilado em `dist/` | 🟡 BAIXA | Fontes (decisão Fase 2) |
| A12 | mypy: 528 erros em 52 arquivos (baseline de tipagem ausente) | ℹ️ INFO | Tipagem |
| A13 | 131 argumentos não usados (ARG001/002) — majoritariamente falsos positivos de DI do FastAPI e overrides | ℹ️ INFO | Código morto (ruído) |

---

## 2. Estrutura do repositório ✅

| Verificação | Resultado |
|---|---|
| Arquivos rastreados | 614 |
| Lixo rastreado (`.db`, `.sqlite`, `.log`, `.exe`, `.asar`, `.pyc`, `.tsbuildinfo`) | **Nenhum** ✅ |
| `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache` rastreados | **Nenhum** ✅ |
| `.env` rastreado | **Não** (apenas `.env.example`) ✅ |
| Arquivos > 1 MB rastreados | **Nenhum** ✅ |
| Pastas obsoletas (`old/`, `backup/`, `tmp/`, `test_*`) | **Nenhuma** ✅ |
| Diretórios: `agent/ backend/ desktop/ docs/ e2e/ frontend/ logs/ monitoring/ scripts/ whatsapp/` | Estrutura íntegra ✅ |

**Observação (fora do git):** a pasta-pai da sessão (`automação zap/`) contém um **protótipo antigo do serviço WhatsApp** (`src/`, `tests/`, `dist/`, `wwebjs_auth/`, `.wwebjs_cache/`, `server.log`, `analysis-dupes.js`, `tsconfig.json` legado) **fora do repositório**. Não afeta o build, mas `wwebjs_auth/` pode conter dados de sessão sensíveis — recomenda-se arquivar/excluir manualmente. Não incluir no commit de limpeza (não é rastreado).

---

## 3. Código morto / duplicado

### 3.1 Backend (Python) — ruff

| Regra | Qtd. | Detalhe |
|---|---|---|
| F401 (imports não usados) | **0** | Limpo ✅ |
| F811 (redefinição) | **0** | Limpo ✅ |
| F841 (variáveis locais não usadas) | **12** | `agent_engine.py:151,192`, `auth_service.py:356`, `gateway.py:214,399`, `delivery.py:159`, `daily_report.py:91,92,350,351`, `dashboard.py:95`, `driver_api.py:953` |
| ARG (args não usados) | **131** | 88×ARG001 + 42×ARG002 + 1×ARG003 — majoritariamente falsos positivos (assinaturas de DI FastAPI, handlers de evento) |
| C901 (complexidade > 10) | **19** | Piores: `import_service.test_connection` (20), `dashboard.get_dashboard` (15), `triggers.evaluate_condition` (15), `driver_api.handle_sync` (13), `dispatch_engine.score_candidate` (13), `daily_report._generate_with_reportlab` (13), `executor.process_execution` (11) |

### 3.2 Backend — vulture (min-confidence 80)

13 achados, todos variáveis "unused" de 100% — **maioria parâmetros de interface** (handlers de evento do SQLAlchemy, dataclasses de routing):

```
app/application/integrations/import_service.py:519  attrs
app/domain/automation/policy.py:243                 rejected_by
app/domain/delivery/routing.py:34,39,54,61          origin, destination (4×2)
app/domain/security/models.py:369                   expires_minutes
app/infrastructure/database/connection.py:53        connection_record
app/infrastructure/printing/escpos.py:101           extra
```

**Ação proposta:** renomear para `_name` ou prefixar com `_` (convenção); **nenhum arquivo inteiro morto detectado**.

### 3.3 Backend — mypy

`528 errors in 52 files (254 checked)` — código sem type hints estritos; baseline recomendado em vez de correção em massa (INFO).

### 3.4 WhatsApp (Node/TS) — tsc strict

| Arquivo | Problema |
|---|---|
| `src/broadcast.ts:17` | `getContactById` importado e nunca usado |
| `src/provider/provider-manager.ts:18` | `path` importado e nunca usado |
| `src/routes.ts:40` | `setCampaignProtection` exportado e nunca usado |

Arquivos órfãos: **nenhum** (`server.ts` é entry; `anti-ban/` importado via directory import em `broadcast.ts:19` e `routes.ts:47`).

### 3.5 Agent (Node/TS) — tsc strict

| Arquivo | Problema |
|---|---|
| `src/ipc.ts:20` | `runDueIntegrations` importado e nunca usado |

Arquivos órfãos: **nenhum** (`index.ts` é entry).

### 3.6 Frontend (React/TS)

- ESLint: **limpo** ✅
- `tsc -b`: **limpo** ✅
- TODO/FIXME/XXX/HACK no repositório inteiro: **1 falso positivo** (comentário "TODOS os routers" em `backend/app/main.py:239`) ✅
- **Página órfã:** `src/features/contacts/ContactsCrmPage.tsx` (9 KB) — ver A1.
  - Páginas *não* órfãs (verificado): `CopilotPage` (embed em IntelligencePage), `PaymentSettingsPage` (embed em SettingsPage), `ConversationsPage`/`CampaignHistoryPage` (tabs em WhatsAppPage).

---

## 4. Crashes silenciosos

### 4.1 Backend — `except Exception:` + `pass` (25 ocorrências)

Amostra (triagem completa na Fase 2 de limpeza):

| Arquivo | Linha | Contexto |
|---|---|---|
| `application/automation/workflow_engine.py` | 242 | `except Exception: pass` |
| `application/security/auth_service.py` | 59 | cleanup de sessão |
| `application/whatsapp/gateway.py` | 317, 417, 658 | fluxo de mensagens |
| `application/delivery/use_cases.py` | 164, 274 | parsing numérico (ValueError — ok engolir?) |
| `application/whatsapp/use_cases.py` | 147 | idem |

**Ação proposta:** adicionar `logger.debug/warning` com contexto nos `except Exception`; manter `except ValueError` pontuais documentados.

### 4.2 `print()` em código de produção (backend)

| Arquivo | Linha | Conteúdo |
|---|---|---|
| `app/domain/events/event_bus.py` | 99 | `print(f"Delivery {event.aggregate_id} completed!")` — substituir por logger |

### 4.3 `console.log` no serviço WhatsApp (24)

Concentrados em `broadcast.ts`, `provider/*.ts` — o serviço tem `pino` (logger estruturado). **Ação:** migrar para `logger.info/warn`.

`console.log` no agent: 0 ✅ · Empty `catch {}` em TS: **0** ✅

### 4.4 Frontend — promises sem tratamento

| Arquivo | Linha |
|---|---|
| `src/features/orders/OrderFormPage.tsx` | 41 |
| `src/features/segments/SegmentsPage.tsx` | 175, 276 |

**Ação:** tratar com feedback ao usuário (toast) ou logar.

---

## 5. Dependências

### 5.1 Backend — pip-audit (ambiente instalado)

| Pacote | Instalado | Advisories | Correção |
|---|---|---|---|
| **python-multipart** | 0.0.12 | 7 (PYSEC-2026-1851/1852/3036–3040) | ≥ 0.0.31 |
| python-jose* | 3.3.0 | 3 (PYSEC-2024-232/233, 2025-185) | não é dependência real do app |
| cryptography* | 49.0.0 | 1 (PYSEC-2026-3552) | via pip upgrade |
| ecdsa* | 0.19.2 | 1 (PYSEC-2026-1325) | não é dependência real do app |
| httpx2/httpcore2* | 2.7.0 | 6 | artefatos do ambiente local (pacotes shadow) |

\* Auditados no ambiente global — **não são usados pelo código** (`generate_token` usa `secrets`, sem JWT/jose). O crítico é **python-multipart**, que o app usa (upload VCF) e **não está em `requirements.txt`** → instalar versão fixada `python-multipart>=0.0.31`.

`requirements.txt` está **totalmente sem pins** (exceto prometheus-client) — builds não reprodutíveis (INFO/MÉDIA).

### 5.2 Node — depcheck

| Projeto | Problema |
|---|---|
| frontend | `tailwindcss` aparenta não usado — **falso positivo** (Tailwind v4 via `@tailwindcss/vite`) ✅ |
| **whatsapp** | **`@hapi/boom` usado em `baileys-engine.ts:42` mas ausente do `package.json`** (dependência transitiva do Baileys hoje) |
| agent | Limpo ✅ |
| desktop | Limpo ✅ |

---

## 6. Desktop (Electron) — estado atual

| Item | Estado |
|---|---|
| `src/main/` real | ❌ Apenas `src/placeholder.ts` — lógica real só em `dist/main/index.js` compilado |
| `tsconfig.json` + `npm run build` | ✅ Funciona (via placeholder, commit `83b23ed`) |
| `npm test` | ❌ **Falha** — `tests/` vazio e glob sem match |
| `build/icon.ico` | ❌ **Não existe** (sem pasta `build/`) |
| `electron-builder.yml → win.icon` | ❌ Ausente → ícone default do Electron |
| NSIS: `createDesktopShortcut` | ✅ `true` |
| NSIS: `createStartMenuShortcut`, `shortcutName`, `installerIcon`, `uninstallerIcon`, `publisherName`, `artifactName` | ❌ Ausentes |
| `dist` script (encadeia builds agent/whatsapp/frontend) | ✅ Correto |

---

## 7. Plano de ação proposto (Fase 2 — aguardando aprovação)

### Limpeza rápida (baixo risco, ~30 min)
1. [ ] A1 — Adicionar rota `contacts` + item de menu para `ContactsCrmPage` (**decisão de produto**: a feature deve ficar visível?)
2. [ ] A2 — `requirements.txt`: adicionar `python-multipart>=0.0.31` + pins gerais
3. [ ] A3 — Declarar `@hapi/boom` no whatsapp
4. [ ] A7 — Remover 12 F841 + 4 TS6133 (whatsapp/agent)
5. [ ] 4.2 — Substituir `print` por logger
6. [ ] A10 — Corrigir script `test` do desktop (glob vazio)
7. [ ] A9 — Tratar 3 `.catch(() => {})`

### Fase 2 — App real (ícone + instalador)
8. [ ] A4 — Gerar `desktop/build/icon.ico` programaticamente (Pillow: cilindro + chama + "GF")
9. [ ] Completar `electron-builder.yml` (icon, shortcuts, publisher, artifactName)
10. [ ] `npm run dist` → `GasFlow Desktop Setup 1.1.0.exe`
11. [ ] Testar instalação (atalhos, 1 clique, subprocessos)

### Diferido (não bloqueia)
- A5 — Triagem dos 25 `except: pass` (adicionar logs)
- A6 — Migrar 24 `console.log` para pino
- A8 — Refatorar as 19 funções complexas (começar por `test_connection`)
- A11 — Decidir restauração dos fontes do desktop
- A12 — Baseline mypy
- Pasta-pai (`automação zap/`): limpeza manual fora do git
