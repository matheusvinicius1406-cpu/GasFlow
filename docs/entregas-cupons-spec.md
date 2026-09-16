# Spec — Entregas, Cupons/Indicação, Comunidade e Organizador de Contatos

**Data:** 16/09/2026 · **Status:** 📋 AGUARDANDO APROVAÇÃO — sem código executado
**Origem:** pedido do dono — consolidar o módulo de entregas, criar indicação com cupons, comunidade de clientes e organizador de contatos.
**Decisões do dono já travadas:** app do entregador em paralelo (desktop + mobile RN), estoque no entregador (C1), sugestão + confirmação do operador (C3), cupom de indicação com valor igual e limite de 10/mês (G1/G2), ordem de execução mantida conforme plano original.

---

## 0. Diagnóstico — o que JÁ existe (medido no código em 16/09/2026)

O plano original foi escrito como "do zero", mas grande parte já está implementada. O esforço real é de consolidação, não de criação.

| Bloco | Status | Já existe | Falta |
|---|---|---|---|
| 1. App do Entregador | 🟡 ~80% | `frontend/src/features/driver/` (login + home com status, confirmar/indisponibilizar entrega); backend `driver_*` + auth JWT mobile (access 15min, refresh rotativo com detecção de replay); `mobile/` RN com fila offline testada (9 testes) | Notificação de nova atribuição no desktop; telas finais do RN; deploy do relay |
| 2. Rastreamento | 🟢 ~90% | LGPD completo: janela de trabalho (fora dela = 403 + audit), consentimento e retenção 90d com purge no boot, `POST /driver/location`, delta sync `GET /driver/sync?since=`, relay na nuvem pronto (não deployado) | Visualização da posição no mapa do operador; ajuste fino de frequência |
| 3. Entrega Inteligente | 🟡 ~60% | `domain/delivery/dispatch_engine.py` com haversine, `proximity_score` e explicação textual da sugestão | Controle de **estoque carregado pelo entregador** (0 matches no repo); UI de sugestão/confirmar |
| 4. Impressão | 🟡 ~70% | ESC/POS **80mm** completo (GT710, `infrastructure/printing/`), print agent, rotas `/printer/*` (print/status/jobs/retry), flag `auto_print_enabled` | Filtro "pagos/aprovados" no auto-print; envio do pedido no zap do entregador |
| 5. Mapa de Calor | 🔴 0% | Campo `bairro` já existe no endereço de entrega | Agregação por bairro + visualização |
| 6. Relatórios/Gráficos | 🟡 ~40% | `ReportsPage` com métricas em texto/cards | Biblioteca de gráficos (Recharts **não instalado**); entregas por entregador/região; tempo médio |
| 7. Cupons/Indicação | 🟡 ~50% | Sistema de cupons **completo**: domain puro (validação/cálculo), `CouponService`, 9 rotas API, RBAC `coupon.*`, 1 cupom por pedido (constraint) | Referral (0 matches); link de auto-cadastro; cupons no perfil; tool de cupom para a IA |
| 8. Comunidade | 🔴 0% | Módulo WhatsApp (envio em massa, campanhas, pacing anti-ban) como base | Fluxo de entrada via link pós-cadastro; broadcast admin-only |
| 9. Organizador de Contatos | 🟡 ~50% | `contacts/service.py` (upsert idempotente, VCF in/out, enriquecimento IA), `codigo` sequencial em clients | Renomeador em lote com revisão; detecção/sinalização de conflitos |

Suítes atuais: backend 1446 ✅ · frontend 194 ✅ · whatsapp 94 ✅ · desktop 41 ✅ · mobile 9 ✅.

---

## 1. Decisões do dono (travadas — não reabrir)

| # | Decisão |
|---|---|
| A1/A2 | **Paralelo**: desktop consolidado como MVP (mesmo instalador, login do entregador esconde módulos admin — `/driver/login` já existe) + mobile RN evoluído em paralelo |
| A3 | Offline **só no mobile** (fila offline já implementada e testada); desktop assume online |
| C1 | **Entregador carrega estoque**: sistema registra quantos cheios cada entregador levou; despacho filtra por quem tem botijão disponível |
| C3 | **Sugere + operador confirma** (design atual do `dispatch_engine` mantido; atribuição automática descartada) |
| G1 | **Mesmo valor de cupom** para indicador e indicado |
| G2 | **Limite de 10 indicações/mês** por cliente |
| Ordem | Mantida a do plano original (seção 8) |

---

## 2. Propostas (sujeitas a revisão do dono)

| # | Proposta | Justificativa |
|---|---|---|
| B1/B2 | Rastreio a cada **60s, só em rota** (configurável nas Configurações › Sistema) | Bateria, aceitação do entregador, cobre o caso de uso |
| B3 | Consentimento LGPD: checkbox + termo no 1º login do app, auditado | Padrão do backend já audita acesso/ingestão |
| D1 | Térmica **80mm** | Já é o que `escpos.py` implementa |
| D2 | Auto-print **só pedidos pagos/aprovados** | Imprimir todo pedido vira lixo |
| D3 | Zap do entregador via **mesmo módulo WhatsApp** (conta primary) | Reaproveita pacing/anti-ban |
| E1–E3 | Mapa de calor **por bairro, 30 dias padrão com filtro, só visualização** | Posicionamento de entregador é sofisticado demais agora |
| F1–F3 | **Recharts** (padrão React, tree-shakeable), export PDF depois, **refresh manual** no começo | Consistência com stack |
| G3 | Validade do cupom de indicação: **90 dias** | Equilíbrio urgência x risco |
| G4 | IA oferece cupom **se o cliente ainda não usou** | Evita oferta redundante |
| H1–H3 | **WhatsApp Community nativo**, entrada via link **após cadastro**, **qualquer cliente cadastrado** | Admin-only nativo do Community |
| I1–I3 | Código **sequencial global**, renomeação **automática por regra com revisão manual**, conflitos **preservados e sinalizados** | Segurança sobre conveniência |

---

## 3. Design por bloco

### 3.1 App do Entregador (desktop MVP + mobile paralelo)
- Desktop: `/driver/login` e `/driver` já existem — consolidar (guard de sessão, esconder sidebar/módulos admin quando sessão é de entregador, som/toast de nova atribuição via eventos realtime `delivery.*` já emitidos).
- Mobile RN: completar telas do MVP (login, lista, detalhe, confirmar), apontando para `/auth/mobile/*` + `/driver/*` com fallback LAN→nuvem→offline (já implementado na lógica pura).
- **Decisão de arquitetura:** nenhum endpoint novo para o desktop; mobile já tem os endpoints de que precisa.

### 3.2 Rastreamento embutido (falta só a visualização)
- Mapa do operador: painel na página de Entregas consumindo `GET /driver/location`/delta sync; polling 30s ou push via WS existente.
- Frequência do app em rota: 60s default, `driver.tracking.interval_seconds` nas Configurações.
- LGPD: já implementado (janela de trabalho + retenção + audit). Só plugar a visualização.

### 3.3 Entrega inteligente (C1 + C3 decididos)
- Nova tabela `driver_stock` (ou colunas em drivers): `full_tanks_loaded`, decrementado por entrega `DELIVERED`, devolvido em cancelamento. Integra com `deliver_stock_atomic` existente (débito da base na entrega — o botijão entregue sai do que o entregador carrega).
- Evento "carregamento": operador registra N cheios no entregador (tela de Motoristas) → audit.
- Despacho: filtro de elegibilidade = tem cheio + disponível + distância; UI mostra a sugestão do `dispatch_engine` com a explicação já gerada; operador confirma.

### 3.4 Impressão em tempo real
- Filtro do auto-print: só pedidos `PAID`/`CONFIRMED` (config `printer.auto_print.min_status`).
- Zap do entregador: na atribuição de entrega, envio automático do resumo (endereço, itens, pagamento) via módulo WhatsApp para o telefone do motorista — reusa o executor de automações existente (idempotente por entrega).
- Impressão manual pelo atendente: botão já existe nas rotas `/printer/print`; falta só wiring na tela de Pedidos.

### 3.5 Cupons como link de auto-cadastro + indicação
- Cupom ganha `invite_token` (link único). Fluxo:
  1. Admin cria cupom → link gerado (ou cupom de indicação gerado por cliente).
  2. Novo cliente recebe o link → **canal a decidir** (ver §5): (a) IA captura o cadastro na conversa (link vira parâmetro de contexto); ou (b) mini-form web público.
  3. Sistema registra `referred_by` + novo cliente.
  4. Ambos ganham cupom (mesmo valor, limite 10 indicações/mês/cliente, validade 90 dias).
  5. Cupons ficam no perfil do cliente (aba "Meus cupons" no CRM).
  6. IA consulta cupons do cliente antes de fechar pedido e pergunta "Deseja usar o desconto do cupom X?" (G4: só se não usado).
- Reuso estrito do domínio de cupons existente: geração via `CouponService`, validação/aplicação via fluxo atual, 1 cupom por pedido, não acumulável.
- Novo: tabela `referrals` (referrer, referee, cupom, status), endpoints admin + público protegido (rate limit), tool IA `list_client_coupons`.

### 3.6 Comunidade
- Link de convite do Community gerado no admin, enviado ao cliente via WhatsApp após cadastro (automations executor).
- Broadcast admin-only: campanhas existentes podem segmentar "membros da comunidade" (novo filtro na campanha).
- GasFlow **não gerencia** o Community (é nativo do WhatsApp) — só orquestra o convite e a comunicação.

### 3.7 Organizador de contatos
- Renomeador em lote: regra configurável (trim, capitalização, remoção de prefixos tipo "WA-", padrão "Nome — Bairro"), preview antes de aplicar, audit por contato.
- Códigos sequenciais globais: garantir sequência sem buracos para novos cadastros (existente) + backfill dos que não têm código.
- Conflitos (nome duplicado/telefone divergente): preservar original, sinalizar em lista "Revisar" (nada sobrescrito sem confirmação).

### 3.8 Mapa de calor
- Backend: agregação `entregas por bairro por período` (SQL group by, cache 5min). Sem postgis.
- Frontend: camada de densidade no mapa (grade por bairro, escala de cor), filtro 7/30/90 dias.
- Só visualização (E3).

### 3.9 Relatórios com gráficos
- Instalar `recharts`; telas: entregas por período, por entregador, por região (bairro), tempo médio de entrega (da atribuição ao `DELIVERED`), comparativo de performance.
- Dados: endpoints de reports existentes + novos agregados do 3.8.
- Refresh manual; export PDF/CSV fica para depois (F2).

---

## 4. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| `driver_stock` divergir do débito da base (`deliver_stock_atomic`) | Mesma transação/idempotência do débito atual; teste de consistência base+entregador |
| Auto-cadastro público virar vetor de spam | Rate limit + validação de telefone (código via WhatsApp) + máximo de cadastros por link |
| IA oferecer cupom errado/insistente | G4 (só se não usado) + cap de 1 oferta por conversa + tool com confirmação |
| Parallel desktop+mobile duplicar lógica | Mobile usa os MESMOS endpoints; lógica de negócio só no backend |
| Comunidade fora do nosso controle (ban do WhatsApp) | Anti-ban já existe (pacing/caps); Community nativo reduz risco de grupo informal |
| Renomeador corromper nomes reais | Preview obrigatório + audit + nada sobrescrito sem confirmação (I3) |
| CI quebrado (E2E boot + Trivy CVEs na imagem backend) pré-existente desde 10/09 | Não bloqueia desenvolvimento, mas **corrigir antes da release que fechar estas fases** |

---

## 5. Decisão pendente (única, não bloqueia o início)

- **Canal do auto-cadastro por cupom (Bloco 7, passo 2):**
  (a) IA captura o cadastro direto na conversa do WhatsApp (link/código do cupom entra como contexto) — mais aderente ao produto, sem página pública;
  (b) mini-form web público (link do cupom abre formulário) — mais simples, mas exige página nova + honeypot/anti-spam.
  Proposta: **(a)**, com (b) como fase 2 se a captura pela IA mostrar atrito.

---

## 6. Fases de execução (ordem mantida pelo dono)

| Fase | Bloco | Entrega | Validação |
|---|---|---|---|
| **F1** | 1 | Desktop do entregador consolidado (sessão, notificação de atribuição) + telas finais do mobile RN | Suítes desktop/frontend/mobile + fluxo manual das 2 pontas |
| **F2** | 2 | Mapa do operador com posição do entregador + intervalo configurável | Testes de UI + LGPD re-run (403 fora da janela, audit) |
| **F3** | 4 | Auto-print com filtro + zap do entregador na atribuição | Impressão real GT710 + idempotência do zap |
| **F4** | 7 | Referral + link/cupom auto-cadastro + cupons no perfil + tool IA | Testes backend (limites, validade, 1/pedido) + e2e do fluxo de indicação |
| **F5** | 8 | Convite do Community pós-cadastro + filtro de campanha | Envio manual para grupo de teste |
| **F6** | 3 | `driver_stock` + elegibilidade + UI sugestão/confirmar | Testes de consistência de estoque + despacho com explicação |
| **F7** | 9 | Renomeador em lote + códigos + conflitos sinalizados | Preview/review manual + audit |
| **F8** | 5 | Mapa de calor por bairro (30d default) | Contagens vs SQL direto |
| **F9** | 6 | Relatórios com Recharts | Suítes frontend + smoke visual |
