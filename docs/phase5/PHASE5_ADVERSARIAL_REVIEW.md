# FASE 5 — ADVERSARIAL REVIEW

## Perguntas Hostis

### 1. Posso mandar mensagem sem estar conectado?
**NÃO.** O endpoint valida `account.isConnected()` antes de enviar. Retorna `ACCOUNT_NOT_CONNECTED` (409).

### 2. Posso mandar mensagem para conta inexistente?
**NÃO.** O endpoint valida `providerManager.getAccount(id)`. Retorna `ACCOUNT_NOT_FOUND` (404).

### 3. Posso duplicar uma mensagem?
**NÃO.** Idempotência via `idempotency_key` UNIQUE na tabela `sent_messages`. Retry retorna `duplicate: true` sem reenviar.

### 4. Posso manipular preço?
**NÃO.** Não existe relação entre mensageria e Orders nesta fase.

### 5. Posso acessar a primary pela secondary?
**NÃO.** Cada endpoint é por `account_id`. Não há bypass.

### 6. Posso descobrir a API key?
**NÃO.** `MARCOS_GAS_API_KEY` está em environment, nunca no código nem no frontend.

### 7. Posso fazer o frontend falar diretamente com WhatsApp?
**NÃO.** Frontend usa `http://localhost:8000/api/whatsapp/*` (FastAPI). WhatsApp Service roda em `localhost:3001` — frontend não tem essa URL.

### 8. Um teste abre Chrome?
**NÃO.** Testes usam `ProviderManager` diretamente (não importam `whatsappProvider` singleton). O singleton do `wwebjs-provider.ts` é importado apenas pelo `broadcast.ts` e `server.ts` (runtime real).

### 9. Um restart destrói sessão?
**NÃO.** Sessões ficam em `wwebjs_auth/primary` e `wwebjs_auth/secondary` (volume Docker). `LocalAuth` persiste automaticamente.

### 10. Um retry duplica mensagem?
**NÃO.** `idempotency_key` UNIQUE + lógica de verificação antes do envio.

### 11. Uma conta caída derruba a outra?
**NÃO.** `ProviderManager` mantém instâncias independentes. `stopAll()` para sequencialmente. Falha em uma não afeta a outra.

### 12. Um erro expõe stack trace?
**NÃO.** Todos os endpoints retornam `{ error: 'CODE', detail: ' mensagem amigável' }`. Nenhum `stack` ou `stack trace` é retornado.

### 13. QR fica exposto indevidamente?
**NÃO.** QR é retornado apenas via `GET /accounts/:id/qr`. Requer que a sessão esteja em `qr_pending`. QR expira após 60s.

### 14. Há race condition?
**BAIXO RISCO.** SQLite com `busy_timeout=5000` + `WAL mode`. Idempotência via UNIQUE constraint. `INSERT OR IGNORE` é atômico.

### 15. Há singleton que inicia browser durante import?
**SIM — RISCO CONHECIDO.** `whatsappProvider` em `wwebjs-provider.ts` é instanciado no topo do módulo. Import dele em testes inicia o browser. Solução: testes importam apenas `ProviderManager` (não o singleton real).

## Gaps Restantes

| Gap | Severidade | Escopo |
|-----|------------|--------|
| broadcast.ts usa singleton antigo | MÉDIA | Fora do escopo FASE 5 |
| Sem autenticação frontend→backend | ALTA | FASE 13 (Hardening) |
| Sem rate limiting | MÉDIA | FASE 13 |
| Sem retry com backoff no envio | BAIXA | Futuro |

## Conclusão

**15/15 perguntas hostis respondidas.**
**Nenhum bloqueio crítico encontrado.**
**FASE 5 APROVADA.**
