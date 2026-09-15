# Spec — Correção Raiz do Módulo WhatsApp (CRM + LID/Baileys 7 + Menu/QR)

**Data:** 2026-09-15
**Status:** planejado (execução imediata — prioridade máxima do usuário para HOJE)
**Pedido:** "continue resolvendo o problema pela raiz... a prioridade máxima é fazer o módulo WhatsApp funcionar, porque ele é o coração do nosso projeto. A mensagem de teste chegou no celular mas NÃO apareceu no GasFlow na área de mensagens (conversas)."
**Doc complementar:** `docs/wa-web-test-spec.md` (sessão F0–F2 do painel WA Web — pausada, retoma depois desta)

---

## 1. Estado verificado (evidências de 15/09)

### 1.1 O que JÁ funciona (validado hoje)

| Item | Evidência |
|---|---|
| Auto-update ponta a ponta | exe 1.1.2 detectou v1.1.4 (log 09:54:40), baixou (09:55:14), instalado → **ProductVersion 1.1.4.0** |
| Envio Baileys (outbound) | `POST /api/whatsapp/accounts/primary/messages` → `{"success":true,"messageId":"3EB088C92B16DF76BCB2A9"}` — **entregue no celular do usuário às 10:36** (confirmado por ele) |
| Recuperação de conexão | `POST /accounts/primary/start` → primary voltou a `connected` sem QR (fix de 401/wipe de 14/09 funcionou) |
| Conta secondary | `connected`, phone 559181376879, `crm-sync.done` |
| Conversas existentes | 9 conversas no CRM; convs 8 e 9 criadas hoje 09:10 (janela dev) — **entrada (inbound) persiste** |

### 1.2 Os 3 defeitos de raiz a corrigir

**D1 — Mensagens ENVIADAS não aparecem nas Conversas (o reportado às 10:36)**
- `whatsapp/src/incoming.ts` encaminha ao backend **apenas mensagens recebidas** (`if (raw.fromMe) return;` linha 131).
- O backend (`POST /whatsapp/incoming` → `MessageGateway.process_incoming`) persiste inbound em `Conversation`/`ConversationMessage`.
- **Nada persiste outbound**: nem envios pela API (`POST /accounts/{id}/messages` → proxy ao serviço), nem replies do bot (a verificar no pipeline), nem envios manuais.
- Resultado: a thread no CRM mostra só metade da conversa — o usuário vê "conversa vazia" mesmo com tráfego real.

**D2 — Erro Bad MAC / `@lid` contínuo na conta primary (raiz: era LID do WhatsApp)**
- Sintoma: `Failed to decrypt message with any known session... Bad MAC` a cada ~5s, `fromMe:true`, JIDs `136459868758120@lid`, `40316908380191@lid` etc.
- Causa raiz confirmada: migração de JIDs para **LID** do WhatsApp; Baileys `6.7.24` (tag `legacy`) não tem o fix — issues WhiskeySockets #1725/#1769 (label "LID related").
- Sessões Signal da primary corrompidas por essa era → decrypt falha permanentemente até re-pareio/migração.

**D3 — Menu/sidebars invisíveis na tela do usuário**
- Sidebar é `hidden w-64 lg:block` (só aparece ≥1024px). Em Windows com escala de DPI 125–150%, a viewport efetiva fica <1024px → sidebar some (sobra o hamburger do `MobileSidebar`, que o usuário não reconheceu como menu).
- Além disso, em 15/09 de manhã o app servia um `frontend/dist` de 13/09 (sem a página WhatsApp Web) — já corrigido no bundle da v1.1.4.

### 1.3 Estado do repo (não commitado)

- `whatsapp/package.json` + `package-lock.json`: **Baileys já atualizado para 7.0.0-rc14** (npm install executado; tsc passou; dist compilado) — **não commitado**.
- `.github/workflows/release.yml`: fix `--publish never` já commitado e validado (v1.1.4 publicou completa: exe 171.5MB + latest.yml).
- Pendência conhecida do CI: publish do electron-builder pode falhar silenciosamente no upload do exe (v1.1.3 publicou só o blockmap) — retry com nova tag resolveu; monitorar na v1.1.5.

---

## 2. Decisões do usuário (entrevista)

| Decisão | Escolha |
|---|---|
| Ordem de prioridade | **1º CRM (thread completa) → 2º erro @lid/Bad MAC → 3º menu/QR na tela** |
| Re-pareio da primary | **Sim, aprovado** (deslogar, apagar creds, QR novo) |
| Estratégia Baileys | **Migrar para o 7 HOJE, a qualquer custo** (sem fallback para 6.x — o usuário rejeitou o plano B) |
| QR aparece em | **Página /whatsapp existente** (botão QR da conta) — painel WA Web fica para a sessão F0–F2 posterior |
| Mensagens de teste | **Liberadas** — par primary↔secondary pode ser usado à vontade |
| Thread no CRM | **Completa**: entrada + saída (como no WhatsApp) |
| Release | **Publicar v1.1.5 hoje** — exe atualiza sozinho |

---

## 3. Plano de execução

### Fase 1 — CRM: thread completa de mensagens (prioridade 1)

**1.1 — Persistir outbound no backend (raiz de D1)**
- No endpoint `POST /api/whatsapp/accounts/{account_id}/messages` (backend `whatsapp.py`): após sucesso do proxy, persistir `ConversationMessage` na conversa `(account_id, customer_phone=recipient)` via `_get_or_create_conversation` equivalente (normalizar telefone com a mesma regra do gateway), com `from_me=true`, `provider_message_id` da resposta e texto.
- Verificar se os **replies do bot** (gateway → `outbound_text` → serviço envia) já persistem; se não, persistir no mesmo formato (ponto único: o gateway já tem a conversa em mão — persistir lá antes de devolver `outbound_text`).
- Mensagens de sistema (ex.: erro de envio) não persistem como mensagem; ficam só em log.

**1.2 — Contracto/normalização**
- Reusar `normalizePhone` (TS) / normalização do gateway (Python) — mesmas regras dos dois lados para que inbound e outbound caiam na MESMA conversa.
- JIDs `@lid`: normalizar para o PN (phone number) quando o mapeamento existir no payload do Baileys 7 (`lid_mapping`/`participant`), senão usar os dígitos disponíveis. **Detalhe crítico pós-migração**: com Baileys 7, `msg.key.remoteJid` pode vir `@lid` — o bridge precisa resolver o PN real antes de postar no backend (verificar `msg.key.participantPn` / `contextInfo`), senão o CRM cria conversas com "telefone" LID.

**1.3 — Validação da fase**
- Enviar mensagem primary→secondary → **aparece na thread** em Conversas (UI).
- Responder do celular → aparece na mesma thread; bot responde (se pipeline ativo) e a resposta também persiste.
- `GET /api/v1/whatsapp/conversations/{id}` retorna messages com in+out ordenados.

### Fase 2 — Migração Baileys 7 + re-pareio (raiz de D2)

**2.1 — Conversão ESM do serviço `whatsapp/`**
- `package.json`: `"type": "module"`; `dist/` emitido como ESM (tsconfig `module: NodeNext`/`moduleResolution: NodeNext`); ajustar imports relativos com extensão `.js`.
- `src/` inteiro revisado para ESM (`import`/`export` já usados — o grosso é só o emit + extensões).
- **Testes**: tsx quebrava com `ERR_PACKAGE_PATH_NOT_EXPORTED` no `whatsapp-rust-bridge` (pacote ESM-only sem `exports.main`). Com o pacote todo em ESM, o tsx resolve pelo caminho ESM — validar empiricamente; se o tsx 4.23 ainda falhar, usar `node --import tsx/esm` ou vitest node.
- **Compat de API Baileys 6→7**: revisar pontos de uso — `makeWASocket` (default export), `useMultiFileAuthState`, `fetchLatestBaileysVersion`, `DisconnectReason`, `jidNormalizedUser`, eventos `messages.upsert`/`connection.update`, `sendMessage`, `groupMetadata`. O typecheck já passou (tsc 0 erros) — bom sinal de que a superfície usada é compatível.
- **LID no 7**: o Baileys 7 resolve PN↔LID nativamente (é o fix da era LID) — verificar em runtime que `remoteJid` chega normalizável.

**2.2 — Electron/desktop carrega o serviço ESM**
- Em dev: `npx tsx src/server.ts` (com `WA_DEV=1`) — validar boot.
- Empacotado: o desktop roda `process.execPath` (Electron as Node, v24.20 — **require(esm) validado funcionando** no exe) com `resources/whatsapp/dist/server.js`. Com `"type":"module"` no package.json do serviço, o `.js` carrega como ESM. **O electron-builder precisa levar o `package.json` atualizado do serviço junto com o dist** — verificar como `resources/whatsapp` é montado (extraResources) e se o node_modules do serviço (com baileys 7 + rust-bridge + wasm) entra completo no pacote.

**2.3 — Re-pareio da primary (após a migração no ar)**
1. Deslogar primary via API (`/accounts/primary/logout`) e/ou pelo celular (Dispositivos conectados → sair).
2. Wipe de `baileys_auth/primary/` (guard: só depois do logout limpo; logar antes/após).
3. `POST /accounts/primary/start` → estado `qr_pending` → **QR na página /whatsapp** → usuário escaneia (celular do número principal 559181689969).
4. Critério: `connected` + `crm-sync.done` + **zero Bad MAC por 15 min**.

**2.4 — Validação da fase**
- Enviar/receber no par primary↔secondary; decrypt sem erro; thread completa no CRM.
- Monitor de erros: `grep "Failed to decrypt" main.log` → contagem nova deve ser 0 durante a janela de teste.

### Fase 3 — Menu/QR visível (D3)

- **Causa provável**: breakpoint `lg` (1024px) + DPI scaling do Windows. Correção mínima: baixar o breakpoint da sidebar para `md` (768px) em `Sidebar.tsx`/`Header.tsx`/`MobileSidebar.tsx` (troca `lg:` → `md:`), mantendo o hamburger para telas pequenas.
- Alternativa se a causa for outra (ex.: zoom do Electron): diagnosticar com a viewport real (`window.innerWidth` no app) antes de trocar CSS — registrar o valor medido no log de execução.
- Critério: usuário vê a sidebar com o item **WhatsApp Web** na janela padrão do app, sem redimensionar nada.

### Fase 4 — Release v1.1.5 + registro

1. Commit das fases 1–3 (commits separados por fase, mensagens no padrão do repo).
2. Suítes: whatsapp `npm test` (após migração ESM), desktop `npm test` (41), frontend `vitest run` (194 + novos testes do outbound-persist se aplicável), backend pytest dos testes de gateway/outbound.
3. `npm version patch` no desktop → v1.1.5 → push + tag → **monitorar o publish** (exe + latest.yml na release; se o upload do exe morrer de novo, retag imediata).
4. Atualizar no exe instalado (auto-update) e revalidar: menu visível, thread completa, sem Bad MAC.
5. Registro: seção nova no `CHANGELOG.md` (correções WhatsApp + ESM + CRM thread + sidebar) e resultados em `docs/whatsapp-fix-log.md` (evidências com timestamps).

---

## 4. Riscos e condutas

| Risco | Conduta |
|---|---|
| Migração ESM quebra testes do tsx | Caminho ESM nativo (`node --import tsx/esm`) ou vitest; usuário aceitou "a qualquer custo" — sem volta pro 6.x |
| electron-builder não leva o node_modules do serviço ESM no pacote | Verificar `extraResources` do `electron-builder.yml`; ajustar para incluir `package.json` do serviço + deps |
| Publish do CI falha de novo (upload do exe) | Retag imediata (padrão v1.1.3→v1.1.4); se repetir 2x, investigar `publish always` vs upload manual do artifact |
| Re-pareio falha (QR não aparece) | Conduta do spec F0: parar e reportar; QR pela página /whatsapp (fluxo já conhecido) |
| Conversas criadas com "telefone" @lid antes da correção | Migração/dedup dos registros existentes: normalizar `customer_phone` das conversas legadas (@lid → PN) ou aceitar e documentar; decidir na execução com evidência |
| Usuário sem acesso à tela no momento do QR | QR tem timeout — reemitir quantas vezes precisar via botão QR |

## 5. Critérios de aceite (definição de "funcionando" para HOJE)

1. **Thread completa**: mensagem enviada pela API aparece nas Conversas do CRM, junto das recebidas, na mesma conversa.
2. **Zero Bad MAC**: 15 min de operação da primary sem `Failed to decrypt` novo (após re-pareio no Baileys 7).
3. **Envio + recebimento E2E**: primary envia → celular recebe; celular responde → GasFlow recebe e persiste.
4. **Menu visível**: sidebar com WhatsApp Web visível na janela padrão do app do usuário.
5. **v1.1.5 publicada** com exe + latest.yml, e o exe do usuário atualizado sozinho.
6. Tudo commitado, suítes verdes, CHANGELOG + log de execução preenchidos.
