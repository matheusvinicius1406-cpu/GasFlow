# IA no GasFlow — Setup e Operação (Item 3)

**Data:** 2026-09-14
**Decisão de provider:** ver `docs/ai-provider-decision.md` (Fase 4.2, cenário B — Ollama local como único provider, sem fallback externo).

---

## O que o Item 3 entregou

A IA funciona **no primeiro boot do app**, sem o dono configurar nada, e o admin pode desligá-la completamente — tudo sem expor jargão técnico na UI.

### 1. Desktop (`ai-setup.ts`) — preparação em background

No boot do GasFlow Desktop, `AiSetupRunner.run()` roda **fire-and-forget** (nunca bloqueia a janela):

1. Procura o binário do serviço local em `C:\Program Files\Ollama` e em `%LOCALAPPDATA%`.
2. Não encontrado → pergunta ao dono: **"Preparar IA local? (~800 MB, uma vez só)"**. Recusa → marca `skipped` e não insiste mais.
3. Encontrado → `GET /api/tags` (timeout 2s) verifica se o modelo está presente; ausente → `POST /api/pull` com progresso.
4. Estado persistido em `settings.json` (chave `ai`) e emitido via IPC (`ai:status-changed`, `ai:download-progress`).

Regras: instalação **só com consentimento explícito**; retry 3x com backoff exponencial (1s/2s/4s); timeout de 120s por request HTTP (pull: 1h); qualquer erro vira estado `unavailable` — o boot do app nunca é afetado.

### 2. Backend — factory com toggle e degradação graciosa

`app/application/ai/provider_factory.py` (reexportado pelo caminho legado `app/infrastructure/ai/factory.py`):

```
1. ai.enabled == false  → NullProvider (IA desligada)
2. health check 2s OK   → OllamaProvider (qwen3, think:false)
3. Ollama caiu          → NullProvider + log (cenário B — sem fallback externo)
```

- **Health check cacheado por 30s** — não bate no serviço local a cada request; `PATCH /ai/settings` limpa o cache.
- **Toggle admin** `ai.enabled` (default ON) vive no quadro de configurações (`system_settings`) — desligar em runtime derruba **toda** a IA (Copilot, WhatsApp agent, teste) sem restart. `AI_ENABLED` (env) é kill switch de emergência quando o quadro não está disponível.
- `AI_PROVIDER=xpto` (valor desconhecido) degrada para `NullProvider` — nunca cai silenciosamente no mock em produção.

### 3. Endpoints (`/ai/*`)

| Método | Rota | Permissão | Função |
|---|---|---|---|
| GET | `/ai/status` | `ai.use` | Estado p/ o dono: `ready / preparing / unavailable / disabled` (sem jargão) |
| POST | `/ai/test` | `ai.use` | Prompt de teste; resposta + provider usado (`local`/`none`) |
| GET | `/ai/settings` | `ai.configure` | Config completa (tela Admin → Inteligência) |
| PATCH | `/ai/settings` | `ai.configure` | Atualiza `enabled` (audit com before/after) |
| POST | `/ai/model/download` | `ai.configure` | Dispara pull em background (202) |
| GET | `/ai/model/download-progress` | `ai.configure` | Progresso do pull (polling JSON) |

**Auditoria** (`auth_audit_log`): `ai.settings.changed` (before/after), `ai.test.prompt` (provider, latência, **hash** do prompt — nunca conteúdo), `ai.model.download`.

**RBAC**: `ai.configure` nova (catálogo + `MANAGER`); `ai.use` adicionada a `OPERATOR`. Sempre a validação primária é no backend (`require_permission`).

### 4. Frontend — tela Admin → Inteligência

`frontend/src/features/settings/AISettings.tsx`, rota `/settings/ai` com guard `ai.configure`. Card de status (verde/âmbar/cinza), toggle "Ativar Inteligência", seção Avançado colapsada (nome técnico do modelo só aqui), teste rápido. **Nenhum termo técnico aparece fora do Avançado.**

---

## Checklist de instalação no depósito (primeiro boot)

1. Instalar o GasFlow Desktop e abrir. Fazer login com a senha de `LOGIN.txt`.
2. Se o diálogo "Preparar IA local?" aparecer, aceitar **uma vez** (~800 MB).
3. Verificar em **Configurações → Inteligência**: status deve ficar **"IA pronta"**.
4. Usar o **Teste rápido** com uma pergunta simples.
5. (Opcional) O admin pode desligar a IA por completo no toggle da mesma tela.

O modelo padrão (`qwen3:0.6b`) roda em 8 GB de RAM; `qwen3:1.7b` é recomendado para conversação melhor (ver números medidos em `ai-provider-decision.md`).

---

## Limitações conhecidas (cenário B)

- **Não há serviço externo de fallback** — decisão deliberada de privacidade (dados do depósito nunca saem da máquina). Sem internet ou com o serviço local parado, a IA responde "IA temporariamente indisponível".
- Reavaliar fallback keyless apenas se as condições de `ai-provider-decision.md` forem atendidas (P2).
- O primeiro `pull` de modelo acontece no boot; até concluir, o status fica "Preparando IA…" e o Copilot responde com a mensagem de indisponibilidade.
