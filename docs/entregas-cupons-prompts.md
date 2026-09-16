# Prompts de Sessão — Entregas, Cupons/Indicação, Comunidade e Contatos

**Uso:** colar o bloco da fase no início de cada sessão de codificação. Um bloco = uma sessão.
**Spec de referência:** `docs/entregas-cupons-spec.md` (inventário §0, decisões §1, design §3, fases §6).

---

## PRÉ-F1 — Gate de CI no release.yml

```
# Sessão de codificação — GasFlow PRÉ-F1: Gate de CI no release

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§4 — riscos; tarefa pré-F1 do §6)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Impedir que o release.yml publique com CI vermelho: o job de release só roda
se os 4 jobs de teste do CI passarem no mesmo commit (ou rodar os testes
dentro do release.yml antes do build).

## Arquivos-chave a ler antes de codar
- .github/workflows/release.yml
- .github/workflows/ci.yml (jobs backend/frontend/whatsapp/agent)

## O que JÁ existe (não reimplementar)
- ci.yml com 4 jobs de teste verdes nos commits atuais
- release.yml disparado por tag v*, sem `needs` de CI (problema)

## O que falta implementar
- Gate: workflow_run + verificação de SHA, ou needs via job reutilizável,
  ou testes duplicados dentro do release.yml (escolher o mais simples)

## Critério de aceitação
Tag de teste criada num commit com CI vermelho NÃO dispara o build do exe;
commit verde dispara normalmente.

## Restrições
- Não quebrar o publish atual (electron-builder --publish always)
- concurrency do release: manter cancel-in-progress: false

## Passos sugeridos
1. Ler os dois workflows
2. Implementar o gate
3. Validar sintaxe (actionlint se disponível)
4. Atualizar CHANGELOG
5. Commit

## O que NÃO fazer
- Não "consertar" o CI (E2E boot/Trivy) nesta sessão — é outra tarefa
- Não mudar a lógica de build/publish do instalador
```

---

## F1 — Entregador + Rastreio (desktop MVP)

```
# Sessão de codificação — GasFlow F1: Entregador + Rastreio (desktop MVP)

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.1, §3.2 — Fase F1)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Consolidar o desktop como MVP do entregador (login, lista, status, confirmação,
notificação de nova atribuição) e mostrar a posição do entregador no mapa do
operador em tempo real, com intervalo configurável.

## Arquivos-chave a ler antes de codar
- frontend/src/features/driver/DriverLoginPage.tsx
- frontend/src/features/driver/DriverHomePage.tsx
- frontend/src/components/layout/DashboardLayout.tsx (guard/sidebar por sessão)
- frontend/src/components/realtime/RealtimeBridge.tsx + lib/hooks/useRealtime.ts
- backend/app/presentation/api/logistics/driver_api.py (e driver_* do módulo logistics)
- backend/app/application/settings/ (para driver.tracking.interval_seconds)

## O que JÁ existe (não reimplementar)
- /driver/login e /driver funcionando contra /api/v1/driver/*
- Auth mobile JWT (access 15min + refresh rotativo), LGPD completo
  (janela de trabalho 403, retenção 90d, audit), POST /driver/location
- Eventos realtime delivery.* já emitidos e consumidos pelo RealtimeBridge

## O que falta implementar
- Esconder módulos admin quando a sessão é de entregador
- Notificação (som/toast) de nova entrega atribuída via evento realtime
- Painel de mapa na página de Entregas consumindo posição (polling ≤30s ou WS)
- Config driver.tracking.interval_seconds (default 60) aplicada no app

## Critério de aceitação
Entregador vê entrega nova em <10s após atribuição; operador vê posição em <60s.

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Não duplicar lógica existente (LGPD/janela de trabalho já prontos)
- Seguir o padrão de módulos consolidados da v1.1.6
- Testes obrigatórios: frontend (driver), backend (interval config + LGPD re-run)

## Passos sugeridos
1. Ler arquivos-chave
2. Implementar guard de sessão + notificação
3. Implementar painel de mapa + config de intervalo
4. Rodar testes (desktop/frontend/backend)
5. Atualizar CHANGELOG
6. Commit

## O que NÃO fazer
- Não criar endpoint novo de tracking (delta sync + location já existem)
- Não tocar no mobile/ nesta fase (é a F2)
- Não remover o poll de 5 min do heartbeat do driver
```

---

## F2 — Mobile RN (evolução)

```
# Sessão de codificação — GasFlow F2: Mobile RN

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.1 — Fase F2)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Completar as telas do app mobile (login, lista, detalhe, confirmação de entrega)
sobre a lógica offline já testada, com consentimento LGPD no 1º login.

## Arquivos-chave a ler antes de codar
- mobile/ (lógica pura: fila offline, client_action_id, backoff, work-hours)
- mobile/src/ (telas RN do MVP escritas — completar)
- backend/app/presentation/api/logistics/driver_api.py (endpoints /driver/*)
- backend/app/presentation/api/core/auth.py ou equivalente /auth/mobile/*

## O que JÁ existe (não reimplementar)
- Lógica pura testada (9 testes): fila offline com client_action_id/backoff
  (cap 5min), work-hours fail-closed, fallback LAN→nuvem→offline
- Endpoints /auth/mobile/login|refresh|logout e /driver/* prontos
- Delta sync GET /driver/sync?since= com offline_sync_log

## O que falta implementar
- Telas finais: login, lista de entregas, detalhe, confirmar entrega
- Consentimento LGPD (checkbox + termo) no 1º login, auditado
- Wiring das telas com a lógica offline existente (sem duplicar)

## Critério de aceitação
App abre offline, mostra entregas em cache, confirma entrega e sincroniza
ao voltar online.

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Não duplicar lógica existente (fila offline é a ÚNICA fonte de verdade)
- Mobile usa os MESMOS endpoints do desktop — nenhum endpoint novo
- Testes obrigatórios: mobile (lógica + novos fluxos)

## Passos sugeridos
1. Ler arquivos-chave
2. Completar telas + consentimento
3. Rodar testes mobile
4. Atualizar CHANGELOG
5. Commit

## O que NÃO fazer
- Não reimplementar fila de sync nem backoff (já testados)
- Não adicionar dependência nativa nova sem necessidade
- Não logar coordenadas GPS (LGPD — audit sem coordenadas)
```

---

## F3 — Impressão em tempo real

```
# Sessão de codificação — GasFlow F3: Impressão em tempo real

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.4 — Fase F3)
- Requisito: WhatsApp módulo v1.1.6+ (módulo unificado)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Auto-print com filtro de status (só pagos/aprovados) e envio automático do
resumo do pedido no WhatsApp do entregador na atribuição da entrega.

## Arquivos-chave a ler antes de codar
- backend/app/infrastructure/printing/print_agent.py (auto_print_enabled)
- backend/app/infrastructure/printing/escpos.py (80mm, GT710)
- backend/app/presentation/api/printer.py (rotas /printer/*)
- backend/app/application/whatsapp_automation/executor.py (ExecutionProcessor)
- backend/app/application/whatsapp_automation/ (criação de executions)
- frontend/src/lib/api/client.ts (api.printer)

## O que JÁ existe (não reimplementar)
- ESC/POS 80mm completo (GT710) + print agent + jobs/retry/status
- Flag auto_print_enabled no print agent
- Executor de automações idempotente (process_pending_executions)
- Rotas /printer/print|status|jobs|retry e client printer no frontend

## O que falta implementar
- Filtro: auto-print só em PAID/CONFIRMED (config printer.auto_print.min_status)
- Envio do resumo (endereço, itens, pagamento) ao motorista na atribuição
  via executor de automações, idempotente por entrega
- Wiring do botão de impressão manual na tela de Pedidos

## Critério de aceitação
Pedido pago imprime em <5s na térmica 80mm; zap do entregador chega em <30s.

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Respeitar anti-ban do serviço WhatsApp (pacing/caps/quiet hours)
- Testes obrigatórios: backend (filtro + idempotência do zap)

## Passos sugeridos
1. Ler arquivos-chave
2. Implementar filtro do auto-print + config
3. Implementar zap do entregador via executor
4. Wiring do botão manual
5. Rodar testes backend
6. Atualizar CHANGELOG
7. Commit

## O que NÃO fazer
- Não enviar via número fora do módulo WhatsApp existente (D3)
- Não imprimir pedidos não pagos (sem bypass do filtro)
- Não criar envio direto ao serviço Node — usar o executor (idempotência)
```

---

## F4 — Cupons + Indicação + IA de cupom

```
# Sessão de codificação — GasFlow F4: Cupons + Indicação

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.5, §5 — Fase F4)
- Requisito: WhatsApp módulo v1.1.6+ (módulo unificado)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Sistema de indicação com cupom: link de convite, auto-cadastro capturado pela
IA na conversa (decisão §5), cupons no perfil do cliente e tool de IA que
consulta/oferece cupons antes de fechar o pedido.

## Arquivos-chave a ler antes de codar
- backend/app/domain/coupon/models.py (CouponSnapshot, validação, cálculo)
- backend/app/application/coupon/coupon_service.py
- backend/app/infrastructure/repositories/coupon_model.py (constraints)
- backend/app/presentation/api/coupons.py (9 rotas existentes)
- backend/app/application/ai/tools_impl.py (AIToolsFactory) + prompts.py
- backend/app/application/contacts/service.py (auto-cadastro placeholder)
- backend/app/application/whatsapp/gateway.py (captura de dados na conversa)

## O que JÁ existe (não reimplementar)
- Domínio de cupons completo: tipos, validade, não-acumulável,
  1 cupom por pedido (constraint no redemption), RBAC coupon.*
- CouponService (CRUD + apply) e relatórios de uso
- Contacts service com auto-cadastro por placeholders (bairro etc.)
- IA com tool-calling (update_client_address como padrão a seguir)

## O que falta implementar
- invite_token no cupom + link de convite
- Registro de referral (tabela referrals: referrer, referee, cupom, status)
- Regras: mesmo valor pros dois, 10 indicações/mês/cliente, validade 90d
- Cupons no perfil (aba "Meus cupons" no CRM)
- Tool IA list_client_coupons + oferta no fluxo de pedido (G4: só se não
  usado; cap 1 oferta por conversa)
- Rate limit e máximo de cadastros por link (anti-spam do §4)

## Critério de aceitação
Fluxo indicação→cadastro→cupom nos dois perfis em <2min; IA oferece cupom
na próxima conversa.

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Reuso estrito do domínio de cupons (nada de validação paralela)
- Testes obrigatórios: backend (limites 10/mês, validade 90d, 1/pedido,
  rate limit), frontend (aba cupons), whatsapp (captura do cadastro)

## Passos sugeridos
1. Ler arquivos-chave
2. Modelo referrals + invite_token + regras
3. Captura do cadastro pela IA (gateway + contacts service)
4. Tool de IA + prompts
5. Aba "Meus cupons"
6. Rodar testes (backend/frontend/whatsapp)
7. Atualizar CHANGELOG
8. Commit

## O que NÃO fazer
- Não permitir 2 cupons no mesmo pedido (constraint existente)
- Não oferecer cupom já usado (G4)
- Não capturar cadastro sem os placeholders obrigatórios do domínio
- Não criar mini-form web (é o fallback §5, só se a IA falhar no real)
```

---

## F5 — Comunidade WhatsApp

```
# Sessão de codificação — GasFlow F5: Comunidade

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.6 — Fase F5)
- Requisito: WhatsApp módulo v1.1.6+ (módulo unificado)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Envio automático do link de convite do WhatsApp Community após o cadastro do
cliente e filtro de campanha para "membros da comunidade".

## Arquivos-chave a ler antes de codar
- backend/app/application/whatsapp_automation/executor.py
- backend/app/application/contacts/reactivate.py (padrão de template/vars)
- backend/app/domain/settings/models.py (configs de template)
- backend/app/presentation/api/whatsapp/automation.py
- backend/app/infrastructure/repositories/coupon_model.py / referrals (F4)

## O que JÁ existe (não reimplementar)
- Executor de automações (idempotente por cliente/dia)
- Sistema de templates com variáveis ({{nome}} etc.)
- Campanhas com pacing anti-ban e segmentação
- Community é nativo do WhatsApp — GasFlow só orquestra convite/broadcast

## O que falta implementar
- Config do link do Community (admin) + template da mensagem de convite
- Trigger: convite após cadastro (idempotente — nunca reenviar)
- Filtro de campanha "membros da comunidade" (flag por cliente)

## Critério de aceitação
Cliente entra via link pós-cadastro; só admin publica (admin-only nativo).

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Respeitar anti-ban (pacing/caps/quiet hours)
- Testes obrigatórios: backend (trigger idempotente, filtro de campanha)

## Passos sugeridos
1. Ler arquivos-chave
2. Config + template do convite
3. Trigger pós-cadastro no executor
4. Filtro de campanha
5. Rodar testes backend
6. Atualizar CHANGELOG
7. Commit

## O que NÃO fazer
- Não tentar gerenciar o Community via Baileys (nativo, fora do escopo)
- Não reenviar convite para quem já recebeu (idempotência)
- Não criar grupo paralelo informal (risco de ban — usar Community oficial)
```

---

## F6 — Organizador + Renomeador de Contatos

```
# Sessão de codificação — GasFlow F6: Organizador de Contatos

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.7 — Fase F6)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Renomeador em lote com preview e revisão, códigos sequenciais globais para
toda a base e lista de conflitos sinalizados (nada sobrescrito sem confirmação).

## Arquivos-chave a ler antes de codar
- backend/app/application/contacts/service.py
- backend/app/infrastructure/repositories/client_model.py (codigo)
- backend/app/infrastructure/repositories/client_repository.py
- backend/app/presentation/api/whatsapp/contacts.py
- frontend/src/features/contacts/ ou whatsapp/ (página de Contatos atual)
- backend/app/domain/audit/ (padrão de audit)

## O que JÁ existe (não reimplementar)
- Contacts service: upsert idempotente, VCF in/out, enriquecimento IA
- codigo sequencial em clients (novos cadastros já recebem código)
- Página de Contatos em /whatsapp/contacts (módulo unificado)

## O que falta implementar
- Renomeador em lote: regra configurável (trim, capitalização, remoção de
  prefixos tipo "WA-", padrão "Nome — Bairro"), preview obrigatório, audit
- Backfill de código sequencial para quem não tem
- Lista "Revisar": conflitos (nome duplicado/telefone divergente)
  preservados e sinalizados

## Critério de aceitação
100% dos contatos com código sequencial atribuído; zero duplicatas após
renomeação em lote.

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Nada sobrescrito sem confirmação (I3)
- Testes obrigatórios: backend (regras de renomeação, backfill, conflitos),
  frontend (preview/review)

## Passos sugeridos
1. Ler arquivos-chave
2. Regras de renomeação + endpoint de preview/apply
3. Backfill de códigos
4. Lista de conflitos na UI
5. Rodar testes
6. Atualizar CHANGELOG
7. Commit

## O que NÃO fazer
- Não sobrescrever nome/telefone sem confirmação explícita
- Não renomear sem preview (audit em cada contato alterado)
- Não tocar nos consumidores externos (driver app, relay — rotas driver_*)
```

---

## F7 — Entrega Inteligente + Estoque do Entregador

```
# Sessão de codificação — GasFlow F7: Entrega Inteligente

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.3 + §3.3.1 — Fase F7)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Controle de estoque carregado pelo entregador (modelo §3.3.1) e despacho
inteligente filtrando elegibilidade por cheio disponível, com UI de
sugestão + confirmação do operador.

## Arquivos-chave a ler antes de codar
- backend/app/domain/delivery/dispatch_engine.py (score + explicação)
- backend/app/domain/delivery/driver.py (haversine, distância)
- backend/app/infrastructure/repositories/inventory_repository.py
  (deliver_stock_atomic — NÃO DUPLICAR)
- backend/app/infrastructure/repositories/delivery_persistence_repository.py
  (chamada do deliver_stock_atomic na entrega)
- backend/app/presentation/api/logistics/delivery_ops.py (atribuição)
- frontend/src/features/drivers/ + deliveries/ (UI)

## O que JÁ existe (não reimplementar)
- dispatch_engine com haversine, proximity_score e explicação textual
- deliver_stock_atomic: débito ATÔMICO da base na entrega confirmada
  (1 cheio sai, 1 vazio entra, idempotente, commit único)
- Reversão em cancelamento pós-DELIVERED (reverse_delivery_stock_atomic)

## O que falta implementar
- driver_stock: full_tanks_loaded (empréstimo, NÃO debita a base),
  empty_tanks_returned, avaria com motivo obrigatório
- Reconciliação de fim de turno: carga − entregas − avarias = cheios
  restantes + vazios devolvidos; divergência > tolerância (config
  driver.stock.tolerance, default 2) → alerta + bloqueio de nova carga
- Elegibilidade no despacho: tem cheio + disponível + distância
- UI: carga no cadastro do motorista, sugestão/confirmar na atribuição

## Critério de aceitação
Sugestão acerta o entregador mais próximo com estoque em >90% dos casos
(medido em 50 pedidos reais).

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Testes obrigatórios: backend (consistência base+entregador, reconciliação,
  avaria, bloqueio), frontend (UI de carga/sugestão)

## Passos sugeridos
1. Ler arquivos-chave
2. Modelo driver_stock + eventos de carga/avaria/reconciliação
3. Filtro de elegibilidade no dispatch_engine
4. UI de carga + sugestão/confirmar
5. Rodar testes
6. Atualizar CHANGELOG
7. Commit

## O que NÃO fazer
- NÃO duplicar débito de estoque: carregamento é empréstimo — a base só
  debita no deliver_stock_atomic (conta dupla = bug, risco §4 do spec)
- Não atribuir sozinho (C3: operador confirma)
- Não desbloquear carga com divergência aberta (fail-closed)
```

---

## F8 — Mapa de Calor

```
# Sessão de codificação — GasFlow F8: Mapa de Calor

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.8 — Fase F8)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Densidade de entregas por bairro com visualização em mapa e filtro de
período (7/30/90 dias, default 30). Só visualização (E3).

## Arquivos-chave a ler antes de codar
- backend/app/infrastructure/repositories/delivery_persistence_model.py
  (address_neighborhood)
- backend/app/presentation/api/reports.py (padrão de agregações)
- frontend/src/features/reports/ReportsPage.tsx
- frontend/src/features/deliveries/ (onde o mapa do operador entrou na F1)

## O que JÁ existe (não reimplementar)
- address_neighborhood persistido em cada entrega
- Endpoints de reports com RBAC
- Mapa do operador (F1) como base de visualização

## O que falta implementar
- Agregação SQL: entregas por bairro por período (cache 5min, sem postgis)
- Endpoint do heatmap (RBAC reports.read)
- Camada de densidade no mapa (grade por bairro, escala de cor) + filtro

## Critério de aceitação
Renderiza em <3s com 90 dias de dados; filtrável por período.

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Testes obrigatórios: backend (contagens vs SQL direto), frontend (render)

## Passos sugeridos
1. Ler arquivos-chave
2. Agregação + endpoint com cache
3. Camada no mapa + filtro de período
4. Rodar testes
5. Atualizar CHANGELOG
6. Commit

## O que NÃO fazer
- Não adicionar postgis nem dependência pesada de mapa
- Não sugerir posicionamento de entregador (E3: só visualização)
- Não agregar dados de outros tenants (sempre filtrar por tenant)
```

---

## F9 — Relatórios com Gráficos

```
# Sessão de codificação — GasFlow F9: Relatórios com Gráficos

## Contexto
- Repo: GasFlow (desktop Electron + backend FastAPI + frontend React + WhatsApp Node)
- Versão base: v1.1.6 (módulos reorganizados, WhatsApp unificado)
- Spec: docs/entregas-cupons-spec.md (§3.9 — Fase F9)
- Suítes atuais: backend 1446 · frontend 194 · whatsapp 94 · desktop 41 · mobile 9

## Objetivo desta sessão
Gráficos de entregas (período, entregador, região), tempo médio de entrega e
comparativo de performance, com exportação PDF.

## Arquivos-chave a ler antes de codar
- frontend/src/features/reports/ReportsPage.tsx
- frontend/package.json (instalar recharts)
- backend/app/presentation/api/reports.py (endpoints existentes)
- backend/app/presentation/api/logistics/delivery_ops.py (agregados F8)
- desktop/ (printToPDF — padrão das notas de compra)

## O que JÁ existe (não reimplementar)
- ReportsPage com métricas (texto/cards) e estado de erro corrigido
- Endpoints de reports + agregação por bairro (F8)
- printToPDF do Electron já usado nas notas de compra

## O que falta implementar
- Instalar recharts
- Gráficos: entregas por período, por entregador, por região (bairro),
  tempo médio (atribuição → DELIVERED), comparativo de performance
- Export PDF via printToPDF
- Refresh manual (F2 do bloco 6: sem tempo real no começo)

## Critério de aceitação
Gráficos carregam em <2s; exportação PDF funciona.

## Restrições
- Não quebrar o que já funciona (suítes verdes)
- Testes obrigatórios: frontend (render dos gráficos, loading/erro/vazio)

## Passos sugeridos
1. Ler arquivos-chave
2. Instalar recharts + componentes de gráfico
3. Tempo médio de entrega (agregado backend se faltar)
4. Export PDF
5. Rodar testes frontend
6. Atualizar CHANGELOG
7. Commit

## O que NÃO fazer
- Não trocar de biblioteca de gráficos (Recharts decidido — F1 do bloco 6)
- Não implementar tempo real/autorefresh (refresh manual)
- Não agregar sem filtro de tenant
```
