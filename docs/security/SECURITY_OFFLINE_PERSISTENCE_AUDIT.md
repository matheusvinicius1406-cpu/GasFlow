# Auditoria de Segurança — Persistência Offline do App do Entregador

**Data:** 31/10/2026
**Escopo:** `mobile/src/logic/queuePersistence.ts`, `mobile/src/logic/offlineQueue.ts`, `mobile/src/containers/wired.tsx`
**Método:** revisão de código linha a linha + suíte `mobile/tests/queuePersistence.test.ts` e `mobile/tests/queueOwnership.test.ts`
**Resultado:** **APROVADO COM RESSALVAS** (2 observações não bloqueantes, na seção Final)

---

## 1. Contexto

O requisito (prompt 3.1/5.4) é que "o estado offline não pode depender de uma variável em memória que desapareça ao fechar o app". A implementação espelha a `OfflineQueue` num KV assíncrono (`AsyncKV`), versionado por chave `gasflow.driver.queue.v1`.

A pergunta de segurança não é "a fila persiste?" — é **o que persiste, quem pode lê, o que pode ser perdido e o que pode ser reenviado por engano**.

## 2. Análise

### 2.1 O que é persistido — sem credenciais

O snapshot (`QueueSnapshot`) contém apenas `schema`, `sessionOwner` e `items`. Cada `QueueItem` tem `client_action_id`, `kind`, `deliveryId`, `payload`, `status`, `attempts`, `nextAttemptAt`, `createdAt`, `lastError`, `owner`.

**Nenhum token, sessão ou credencial é persistido.** A autenticação vive em `tokenStorage.ts` (Keychain), separado. Revisei a cadeia de `setItem` em `writeIfDirty()` (linha 379): o payload é montado a partir de `this.sessionOwner` + `this.items` — nada mais é serializado.

O `payload` carrega dados de ação de entrega (posição, prova). É PII de localização, tratado em §2.4.

### 2.2 Durabilidade e serialização de escritas

- **Escritas em série:** `scheduleWrite()` encadeia `this.chain = this.chain.then(...)`. Não há corrida entre `save()` e `remove()` — cada mutação aguarda a anterior. Sem perda por interleaving.
- **Retry em falha:** `writeIfDirty()` em falha mantém `dirty = true` (linha 384). A próxima mutação ou `persist()` re-tenta.
- **`persist()` propaga erro** (linha 361): o chamador **não** confirma "salvo" com o disco desatualizado. Correto — evita falso sinal de durabilidade.
- **Boot:** `attach()` troca o KV (memória → AsyncStorage) e re-idrata (`hydrate()`).

### 2.3 Idempotência — nada é reenviado por engano

`hydrate()` faz merge sem ressuscitar ação confirmada:

- `merge()` (linha 332): se o local é `synced`, o snapshot **não** o rebaixa para `pending`. Ação confirmada vence.
- Empate: vence quem tem mais `attempts` (backoff mais avançado).
- `client_action_id` é a chave do Map — replay idempotente no servidor.

### 2.4 Posse e não-descarte implícito (LGPD + segurança multi-tenant)

Este é o ponto mais sensível: **logout ou troca de motorista não podem apagar ação pendente, nem podem fazer a ação de um motorista ser reenviada por outro.**

- `setSessionOwner(null)` (linha 223) **não apaga nada** — apenas para a reprodução. Pendências ficam guardadas.
- `claimUnowned()` (linha 242): **recusa** adotar itens para outra identidade já conhecida da sessão (`ownerMatches`). Um motorista nunca assume fila de outro.
- `heldForOtherOwner()` (linha 254): itens de outra identidade ficam **visíveis e pendentes**, não são escondidos nem descartados.
- `discard()` (linha 266) é o **único** caminho de remoção, explito e auditável (`DiscardRecord`, ring buffer de 50).
- **Teto LGPD** (linha 32): `MAX_PERSISTED_LOCATIONS = 500`, e `enforceLocationCap()` (linha 177) **só poda posições já `synced`** — ação/pendente nunca é podada. Retenção mínima sem perda de dado não-sincronizado.

### 2.5 Falha degradação vs. travamento

`createAsyncStorageKV()` valida o backend e **falha para memória** se inválido (linha 73). Em `hydrate()`, erro de leitura seta `hydrateFailure` e **não trava o boot** — a fila segue em memória. `writeIfDirty()` em falha mantém a fila válida em memória. O sistema degrada, não trava. Correto para um app de entrega em campo.

## 3. Evidência de teste

Rodei a suíte mobile completa neste worktree:

```
tests 101 | suites 9 | pass 101 | fail 0
```

Casos que cobrem os achados acima (em `queuePersistence.test.ts` e `queueOwnership.test.ts`):
- restart com mesmo KV preserva pendentes;
- JSON corrompido não derruba o boot (`hydrateFailure`);
- escrita falhosa e retry;
- `claimUnowned` recusa identidade divergente;
- logout preserva e não reproduz.

## 4. Rastreabilidade

- Commit da persistência: presente em `#79` (`release/home-server-candidate`).
- Branch `parallel/freebuff-mobile-p0` (#77) traz a versão anterior; superseded por #79 (ver `FINAL_PR_INTEGRATION_PLAN.md`).

## 5. Final — ressalvas não bloqueantes

Aprovado. Duas observações para acompanhamento, **nenhuma delas é vulnerabilidade atual**:

1. **Validação de `kind` no `reviveItem()` é estrita** (linha 116): um item com `kind` fora da lista fixa é descartado silenciosamente no boot. Hoje é correto (evita injeção de payload arbitrário via KV adulterado), mas se um novo `kind` for adicionado sem bump de `QUEUE_SCHEMA_VERSION`, itens antigos com o novo tipo seriam perdidos. **Recomendação:** ao adicionar `kind`, fazer `.v2` e migrar na `hydrate()` — já documentado no cabeçalho do módulo (linha 26).

2. **O snapshot é armazenado em claro no AsyncStorage** (que no Android é unificado por app). Contém localização do entregador (PII). Não há credencial — aceitável — mas se o requisito de proteção da posição aumentar, avaliar cifragem do snapshot. Fora do escopo atual.

**Nenhum token é persistido. Nenhum descarte é implícito. Nenhuma ação pode ser reenviada por identidade divergente.**
