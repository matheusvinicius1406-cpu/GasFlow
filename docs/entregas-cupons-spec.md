# Spec — Entregas, Cupons/Indicação, Comunidade e Organizador de Contatos

**Data:** 16/09/2026 · **Status:** 📋 AGUARDANDO APROVAÇÃO — spec executável (v2) — nenhum código de feature executado
**Origem:** pedido do dono — consolidar o módulo de entregas, criar indicação com cupons, comunidade de clientes e organizador de contatos.
**Decisões do dono já travadas:** app do entregador em paralelo (desktop + mobile RN), estoque no entregador com modelo detalhado (C1 — §3.3.1), sugestão + confirmação do operador (C3), cupom de indicação com valor igual e limite de 10/mês (G1/G2), auto-cadastro por IA na conversa (§5), fases com critérios de aceitação objetivos (§6).
**Prompts por fase:** `docs/entregas-cupons-prompts.md` (colar no início de cada sessão de codificação).

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
| Ordem | Ajustada na v2: F1+F2 fundidas (entregador+rastreio), contatos antecipado para F6, inteligente para F7 (§6) |

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

### 3.3.1 C1 — Modelo de estoque do entregador (detalhe)
| Pergunta | Decisão |
|---|---|
| Carregamento | **Manual**: entregador declara "peguei N cheios" no app → operador confirma na base → evento `loading` com audit. Sem carga automática. |
| Débito da base | **Só na entrega confirmada** (`deliver_stock_atomic` intocado). O carregamento é **empréstimo temporário** (`full_tanks_loaded += N`) e **não** debita a base — conta dupla é bug. A cada entrega, `full_tanks_loaded` decrementa e a base debita uma única vez. |
| Avaria/perda | Lançamento "avaria" no app com **motivo obrigatório**; debita `full_tanks_loaded` e o estoque da base, com audit `stock.damage`. |
| Vazios | Contagem separada `empty_tanks_returned`; reconciliação no fim do turno: carga − entregas − avarias = cheios restantes + vazios devolvidos. |
| Divergência | Fora da tolerância (config `driver.stock.tolerance`, default 2): alerta ao operador + **bloqueio de novas cargas** até reconciliação manual. |

### 3.4 Impressão em tempo real
- Filtro do auto-print: só pedidos `PAID`/`CONFIRMED` (config `printer.auto_print.min_status`).
- Zap do entregador: na atribuição de entrega, envio automático do resumo (endereço, itens, pagamento) via módulo WhatsApp para o telefone do motorista — reusa o executor de automações existente (idempotente por entrega).
- Impressão manual pelo atendente: botão já existe nas rotas `/printer/print`; falta só wiring na tela de Pedidos.

### 3.5 Cupons como link de auto-cadastro + indicação
- Cupom ganha `invite_token` (link único). Fluxo:
  1. Admin cria cupom → link gerado (ou cupom de indicação gerado por cliente).
  2. Novo cliente recebe o link → **cadastro capturado pela IA na conversa** (decisão §5; link/código do cupom entra como contexto).
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
- Refresh manual; export PDF entra na F9 (critério de aceitação), via printToPDF do Electron (padrão das notas de compra).

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
| **`release.yml` sem gate de CI** — publica mesmo com CI vermelho | **Tarefa pré-F1:** gate no release — job de release só roda se os 4 jobs de teste do CI passarem no mesmo commit (alternativa: rodar os testes dentro do próprio `release.yml` antes do build). Hoje: CI vermelho desde 10/09 → toda release pode publicar código quebrado sem perceber. |

---

## 5. Decisão: canal do auto-cadastro por cupom — ✅ DECIDIDO (a)

**Decisão: IA captura o cadastro na conversa do WhatsApp.** Obrigatória antes da F4; não bloqueia F1–F3.

| Opção | Prós | Contras | Trabalho |
|---|---|---|---|
| **(a) IA na conversa** ✅ | Zero frontend novo; aderente ao produto; captura natural na conversa | Depende do prompt da IA funcionar 100%; depende do número pareado; risco de abuso | Baixo |
| (b) Mini-form web público (fallback) | Independente do WhatsApp; controle total de validação | Página nova; captcha; rate limit; LGPD de formulário | Médio-Alto |

Fallback: se a captura pela IA mostrar atrito no fluxo real, migra-se para (b) **sem descartar o backend** (mesmos endpoints).

---

## 6. Fases de execução (v2 — F1+F2 fundidas; contatos antecipado p/ F6; critérios objetivos)

> **Pré-F1 (tarefa):** gate de CI no `release.yml` — release só roda com os 4 jobs de teste verdes no mesmo commit (ver §4).
> **Requisito transversal:** fases que usam o módulo WhatsApp (F3, F4, F5) exigem **WhatsApp v1.1.6+** (módulo unificado — versões anteriores não têm a API necessária).

| Fase | Bloco | Entrega | Critério de aceitação | Validação |
|---|---|---|---|---|
| **F1** | 1+2 | Entregador **desktop MVP** consolidado (login, lista, status, confirmação, notificação de atribuição) **+** mapa do operador com posição em tempo real + intervalo configurável | Entregador vê entrega nova em **<10s** após atribuição; operador vê posição em **<60s** | Suítes desktop/frontend + LGPD re-run (403 fora da janela, audit) |
| **F2** | 1 | **Mobile RN**: telas finais (login, lista, detalhe, confirmar) sobre a lógica offline já testada + consentimento LGPD no 1º login | App abre **offline**, mostra entregas em cache, confirma entrega e **sincroniza ao voltar** | Suíte mobile + fluxo offline manual |
| **F3** | 4 | Auto-print com filtro + zap do entregador na atribuição | Pedido pago imprime em **<5s** na térmica 80mm; zap chega em **<30s** | Impressão real GT710 + idempotência do zap |
| **F4** | 7 | Referral + auto-cadastro por IA (canal §5) + cupons no perfil + tool IA | Fluxo indicação→cadastro→cupom nos dois perfis em **<2min**; IA oferece cupom na próxima conversa | Testes backend (limites 10/mês, validade 90d, 1/pedido) + e2e da indicação |
| **F5** | 8 | Convite do Community pós-cadastro + filtro de campanha | Cliente entra via link **pós-cadastro**; só admin publica | Envio manual para grupo de teste |
| **F6** | 9 | **Organizador + renomeador de contatos** (antecipado: base de dados limpa antes dos blocos dependentes) | **100%** dos contatos com código sequencial; **zero duplicatas** após renomeação em lote | Preview/review + audit por contato |
| **F7** | 3 | **Entrega inteligente**: `driver_stock` (§3.3.1) + elegibilidade + UI sugestão/confirmar | Sugestão acerta o entregador mais próximo com estoque em **>90%** (medido em 50 pedidos reais) | Testes de consistência de estoque + despacho |
| **F8** | 5 | Mapa de calor por bairro (30d default) | Renderiza em **<3s** com 90 dias de dados; filtrável por período | Contagens vs SQL direto |
| **F9** | 6 | Relatórios com Recharts + export PDF | Gráficos carregam em **<2s**; exportação PDF funciona | Suítes frontend + smoke visual |
