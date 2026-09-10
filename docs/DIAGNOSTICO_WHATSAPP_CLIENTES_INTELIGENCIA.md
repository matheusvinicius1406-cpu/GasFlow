# 🔍 DIAGNÓSTICO — WhatsApp / Clientes / Inteligência (GasFlow Desktop instalado)

**Data:** 2026-09-10 · **Instalação:** `%LOCALAPPDATA%\Programs\GasFlow Desktop\` (Setup 1.1.0, build de hoje 11:59)
**Dados:** `%APPDATA%\gasflow-desktop\` · **Logs:** `logs\main.log` (12:25–12:35) + `main.old.log` (07/09–10/09)

## Estado dos serviços (quando o app estava aberto)

| Serviço | Porta | Estado |
|---|---|---|
| Backend FastAPI | 8000 | ✅ subiu (python do sistema + uvicorn) |
| Serviço WhatsApp | **3101** (`settings.waPort`) | ✅ subiu (Baileys via ELECTRON_RUN_AS_NODE) |
| Ollama | 11434 | ✅ rodando, modelo `qwen3:0.6b` instalado |

**Conclusão importante:** os subprocessos **sobem**. O problema não é spawn — são (1) sessão WhatsApp deslogando em loop e (2) **banco do app desatualizado vs. código novo** (schema migration faltando).

---

## 1. WhatsApp não envia / não sincroniza contatos

### 🔴 Causa raiz 1 — Sessão Baileys deslogando em loop (`logged_out` ×13 nos 2 logs)

```
event: account.disconnected, reason: logged_out, engine: baileys  (12:31:35, 12:33:20, 12:34:52...)
SessionError: No session record / No matching sessions found / Bad MAC (dezenas)
Closing open session in favor of incoming prekey bundle
```

**Evidência adicional:** `LOGIN.txt` no userData + credenciais em `baileys_auth/` — a sessão **chegou a parear** (havia mensagens sendo descriptografadas, `crm-sync` retornando 200, mensagens `fromMe` decryptadas), mas o par frequentemente é **derrubado e religado**. Cada reconexão com credenciais parciais gera os erros `No session record`/`Bad MAC` (sessions corrompidas do uso anterior) e eventualmente o WhatsApp desloga a sessão.

**Por que não envia:** com a conta em `logged_out`, todo `sendText` falha no Baileys (não há erro de HTTP — falha antes).

**Ação:** (a) limpar `baileys_auth/` para recomeçar com sessão limpa; (b) no serviço, tratar `logged_out` removendo credenciais corrompidas e forçando novo QR imediatamente; (c) investigar o que derruba a sessão (provável: múltiplos `start` do mesmo account id, ou crash do serviceworker com restart que reaproveita creds inválidas).

### 🟠 Causa raiz 2 — `waEnabled: false` não é o gating (mas o config confunde)

`settings.json` tem `waEnabled: false`, porém o main process **inicia o WhatsApp incondicionalmente** (`void ensureWaBridge().start()`). O flag é ignorado no boot — inconsistência de config que confunde o usuário (painel mostra "desativado" mas serviço roda). Alinhar: respeitar o flag OU remover o flag da UI.

### 🟡 Hipóteses descartadas (com evidência)

| Hipótese | Evidência contrária |
|---|---|
| Chaves inconsistentes (401) | main process usa `settings.waApiKey` para backend E whatsapp (`WHATSAPP_SERVICE_KEY`, `MARCOS_GAS_API_KEY`, `GASFLOW_SERVICE_KEY` idênticas); crm-sync → 200 |
| `GASFLOW_BACKEND_URL` ausente | Injetado no spawn: `GASFLOW_BACKEND_URL: backendUrl()` |
| Serviço não sobe | Porta 3101 LISTENING com PID do Electron |

---

## 2. Aba "Clientes" quebrada

### 🔴 Causa raiz — Banco do app DESATUALIZADO: colunas novas não existem no SQLite

```
sqlite3.OperationalError: no such column: clients.has_name   (89 ocorrências)
→ 15× GET /api/clients/contacts -> 500
→  8× GET /api/clients/ -> 500          (a própria aba Clientes!)
→  4× POST /api/clients/contacts/reactivate -> 500
→ + /api/reorder/*, /api/finance/*, touch_last_interaction (gateway) ...
```

**Schema real do banco instalado** (`%APPDATA%\gasflow-desktop\gasflow.db`, clientes: 0):
`tenant_id, id, codigo, nome, telefone, telefone_secundario, rua, numero, complemento, referencia, bairro, observacoes, ativo, tipo, email, updated_at, created_at`

**Faltam 5 colunas** que o código novo (entidade `Client`) espera: **`has_name`, `is_whatsapp`, `last_interaction_at`, `last_sync_at`, `marketing_status`**.

**Causa:** `init_db()` só faz `Base.metadata.create_all()` — que **cria tabelas novas, mas nunca ALTERA tabelas existentes**. O banco foi criado no dia 07/09 pelo app instalado (versão do código daquela data); o build de hoje tem o código novo, mas o schema velho → todo SELECT/INSERT da entidade Client quebra → aba Clientes 500, sync-batch falha, contatos não sincronizam (mesmo com WhatsApp conectado!), reativação quebra.

**Isso explica também "contatos não aparecem no CRM"**: o upsert do sync-batch insere com `has_name` etc. → OperationalError → contato descartado.

**Ação:** migration leve no boot (Alembic ou bootstrap de colunas idempotente): adicionar as 5 colunas se ausentes. Opcionalmente `ALTER TABLE` simples no `init_db`.

---

## 3. Área "Inteligência" não funciona

### 🟠 Causa raiz — `/ai/chat` não é chamado pelo app; e toda a página depende do Client que está 500

- `IntelligencePage` = `CopilotPage`, que chama `POST /api/ai/chat`.
- No log **novo** (12:25–12:35): **zero chamadas a `/api/ai/chat`** — o usuário abriu a Inteligência e **a página nem conseguiu montar** (ou o usuário não chegou a enviar mensagem).
- No log **antigo** (07–10/09): `POST /api/ai/chat -> 200` ×5 — **o endpoint funciona** quando o Ollama está de pé e o modelo existe (`qwen3:0.6b` confirmado em `/api/tags`).
- Porém há erros do tool `update_client_address` (`model = ...filter(codigo == codigo).first()`) no log antigo — o Copilot **tenta executar tools sobre `Client`** e essas tools dependem das colunas novas → com o schema velho, ações do Copilot quebram com o mesmo `no such column`.

**Causa raiz consolidada:** a Inteligência **não tem defeito próprio** — ela fica inutilizável porque (a) o layout/telas que dependem de `GET /api/clients/*` e `/api/clients/contacts` retornam 500 (schema velho), e (b) as tools de IA que tocam `Client` quebram igual. Com o schema corrigido, `/ai/chat` volta a responder (já respondeu 5× com 200).

**Ação:** corrigir a migration (item 2) + garantir degradação graciosa na UI quando Ollama não está disponível (mensagens claras em vez de erro genérico).

---

## Tabela-resumo (sintoma → causa → ação)

| Sintoma | Evidência | Causa raiz | Ação |
|---|---|---|---|
| WhatsApp não envia | `account.disconnected logged_out` ×13; sem `sendText` com sucesso no log | Sessão Baileys deslogando + credenciais corrompidas (`Bad MAC`, `No session record`) | Limpar `baileys_auth/`; tratar `logged_out` → novo QR automático |
| Não sincroniza contatos | `crm-sync → 200` no serviço, mas 0 clientes no banco; `POST /api/clients/contacts/sync-batch` com `no such column` | **Schema do SQLite desatualizado** (5 colunas faltando) | Migration no boot (ALTER TABLE idempotente) |
| Não mostra conversas | Conversas retornam 200, mas sem mensagens entrando decifradas (decrypt falhando) | Sessão corrompida (idem 1) | idem 1 |
| Aba Clientes 500 | `no such column: clients.has_name` ×89 | idem schema | idem migration |
| Inteligência sem resposta | 0 chamadas `/api/chat` no log novo (página nem monta); `/ai/chat` 200 no log antigo; tools de IA quebram no `Client` | Efeito do schema + ausência de fallback na UI | Migration + degradação graciosa |
| Config confusa | `waEnabled: false` mas serviço roda | Flag não é respeitado no boot | Respeitar flag ou removê-lo |

## Próximos passos (ordem)

1. **Migration de schema no boot do backend** (corrige Clientes + sync + reativação + tools de IA) — correção mais impactante.
2. **WhatsApp**: tratar `logged_out` (auto-recovery: limpar creds + QR) + respeitar/alinhar `waEnabled`.
3. Degradar graciosamente a Inteligência quando Ollama/modelo indisponível.
4. Rodar testes, rebuild do instalador, reinstalar e validar E2E (QR → mensagem → contato no CRM → Copilot).
