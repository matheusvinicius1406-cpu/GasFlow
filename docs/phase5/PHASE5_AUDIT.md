# FASE 5 — AUDITORIA DO ESTADO ATUAL

## Estado Atual

### Componentes Existentes

| Componente | Status | Notas |
|------------|--------|-------|
| `ProviderManager` | ✅ | Multi-account, singleton |
| `WhatsAppProvider` interface | ✅ | connect, disconnect, sendMessage, getStatus, getQr |
| `WhatsAppWebJsProvider` | ✅ | whatsapp-web.js, LocalAuth |
| `normalizePhone` | ✅ | Strip non-digits, remove leading zeros |
| `routes.ts` | ✅ | Multi-account endpoints |
| `server.ts` | ✅ | Liveness + Readiness |
| `auth.ts` | ✅ | API Key middleware |
| `broadcast.ts` | ⚠️ | Uses singleton `whatsappProvider`, not `providerManager` |
| `db.ts` | ✅ | SQLite with contacts, lists, customers, campaigns |
| Backend bridge | ✅ | Proxies to WhatsApp Service |
| Frontend WhatsApp | ✅ | Uses backend API, multi-account |

### Contratos Existentes

| Contrato | Campos |
|----------|--------|
| `MessagePayload` | `text: string` |
| `SendResult` | `success, messageId?, error?` |
| `WhatsAppStatus` | `state, connected, hasQr` |
| `WhatsAppConnectionState` | `disconnected, connecting, qr_pending, connected` |

### Endpoints Existentes

| Método | Endpoint | Auth | Status |
|--------|----------|------|--------|
| GET | `/api/whatsapp/accounts` | ❌ | ✅ |
| GET | `/api/whatsapp/accounts/:id` | ❌ | ✅ |
| POST | `/api/whatsapp/accounts/:id/start` | ✅ | ✅ |
| POST | `/api/whatsapp/accounts/:id/stop` | ✅ | ✅ |
| POST | `/api/whatsapp/accounts/:id/logout` | ✅ | ✅ |
| GET | `/api/whatsapp/accounts/:id/qr` | ❌ | ✅ |
| GET | `/api/whatsapp/accounts/:id/health` | ❌ | ✅ |
| POST | `/api/whatsapp/accounts/:id/messages` | ❌ | **NÃO EXISTE** |

### Gaps Identificados

1. **Sem endpoint de envio de mensagem** — `/messages` não existe
2. **Sem idempotência** — nenhuma deduplicação de envio
3. **Sem persistência de mensagens** — nenhuma tabela `sent_messages`
4. **broadcast.ts usa singleton** — deveria usar `providerManager`
5. **Sem erros padronizados** — erros são strings avulsas
6. **Sem teste de concorrência** — nenhum teste parallel
7. **Frontend sem envio** — não tem UI para enviar mensagem de teste

### Riscos

| Risco | Severidade | Probabilidade |
|-------|------------|---------------|
| Duplicação de mensagem via retry | ALTA | ALTA |
| Race condition no envio | MÉDIA | MÉDIA |
| Perda de mensagem sem persistência | ALTA | MÉDIA |
| broadcast.ts usando provider errado | MÉDIA | ALTA |

### Decisões Necessárias

1. **Idempotência**: SQLite em memória vs tabela persistente → Tabela persistente (sobrevive restart)
2. **Erros**: Códigos de erro padronizados vs strings → Códigos de erro
3. ** broadcast.ts**: Migrar para `providerManager` → SIM, mas não nesta fase (escopo limitado)
4. **Persistência**: Criar tabela `sent_messages` → SIM

### Divergências

- `broadcast.ts` importa `whatsappProvider` (singleton antigo) em vez de `providerManager`
- Frontend não tem UI de envio de mensagem
- Backend bridge não tem endpoint `/messages`

### Decisões de Design

1. Manter `broadcast.ts` como está (fora do escopo FASE 5)
2. Criar tabela `sent_messages` para idempotência
3. Usar `providerManager` para envio via API
4. Padronizar erros com códigos
