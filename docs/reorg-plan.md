# Reorg Plan — Consolidation

> **Status: v2 — SUPERSEDED by owner decision (Sept 17, 2026).**
> The 8-group sidebar was consolidated to **7 groups**: "Pedidos" (direct link) merged into the
> logistics group, now **"Pedidos & Entregas"** (sub-items: Pedidos, Entregas, Motoristas).
> Dashboard remains the only direct item. The §1 map below reflects v2.
> Original v1 structure kept at the bottom for history.

---

Mecanismo de migração: Alembic (9 versões) + `SCHEMA_VERSION` no init_db **com backup automático do arquivo** antes de migrar.

---

## 1. Mapa da nova estrutura de módulos

### Sidebar: de 18 itens chapados → **7 grupos (v2)**

```
📊 Dashboard                          (item único)
💬 WhatsApp                           (grupo)
   ├── Conversas            ← home do módulo (/whatsapp)
   ├── Contatos             ← ex "Contatos WhatsApp" (/whatsapp/contacts)
   ├── Campanhas            ← wizard + resultados + histórico
   ├── Automações
   └── Contas & Conexão     ← contas + QR + WhatsApp Web como SEÇÃO/opção ligável
🛒 Pedidos & Entregas                 (grupo — v2: logística de ponta a ponta)
   ├── Pedidos               ← entrada do fluxo (/orders)
   ├── Entregas              ← execução (/deliveries)
   └── Motoristas            ← recursos (/drivers)
👥 Clientes                           (grupo)
   ├── Lista               ← /customers
   ├── Segmentos
   ├── Recompra
   └── Cupons
🏷️ Produtos & Estoque                 (grupo)
   ├── Produtos
   ├── Estoque
   └── Notas de Compra
💰 Financeiro & Relatórios            (grupo)
   ├── Financeiro
   └── Relatórios
⚙️ Configurações                      (grupo: geral, usuários, auditoria, IA)

🤖 IA = BOLINHA FLUTUANTE (não é item de menu)
```

### O que funde com o quê / o que é removido (v2)

| Ação | De | Para |
|---|---|---|
| **MOVE+REROTA** | `/contacts` (Contatos WhatsApp) | `/whatsapp/contacts` — feature `contacts` **deletada**, vira aba do módulo WhatsApp |
| **ABSORVE (seção)** | `/whatsapp/web` (WhatsApp Web) | vira seção "WhatsApp Web" dentro de *Contas & Conexão*, **gated pela flag `waWebPanel.enabled`** (ligável/desligável). Rota própria some. |
| **AGRUPA (v2)** | `Pedidos` (item direto) | entra no grupo **Pedidos & Entregas** — fluxo pedido→entrega em um só lugar |
| **FUNDE** | products + inventory | grupo **Produtos & Estoque** (frontend); backend agrupa em módulo `catalog/` mantendo rotas `/products`, `/inventory` (zero quebra de API) |
| **ABSORVE** | Notas de Compra | entra no grupo Produtos & Estoque (compra de estoque) |
| **FUNDE** | finance + reports | grupo **Financeiro & Relatórios** (abas internas) |
| **ABSORVE** | Motoristas | grupo **Pedidos & Entregas** (logística) |
| **AGRUPA** | segments + reorder + promotions (Cupons) | sub-itens do grupo **Clientes** (marketing de clientes) — *ponto de decisão, ver §6* |
| **REMOVE** | `/intelligence` + IntelligencePage | **deletados** (não escondidos). CopilotPage vira painel da bolinha flutuante |
| **REMOVE** | item "Contatos WhatsApp" | substituído por aba Contatos no WhatsApp |

**Resultado (v2):** 18 → 7 grupos; todo WhatsApp em 1 módulo; fluxo pedido→entrega em 1 grupo; nada duplicado; nada órfão.

---

## 2. Plano de migração do banco (limpeza + dados reais)

**Ordem rígida:** backup → limpeza → dados reais → validação.

1. **Backup automático** (init_db já faz antes de qualquer migration) + cópia manual extra `gasflow-backup-reorg.db`.
2. **Migration SCHEMA_VERSION v4** (`_reorg_cleanup`), que:
   - `DELETE FROM whatsapp_messages` e `whatsapp_conversations` (28/160 — era tudo teste/LID; conversas reais renascem limpas com a ponte nova).
   - `DELETE FROM ai_conversations` / `ai_messages` (lixo do Copilot).
   - Clients: **deleta os 5 LID-lixo** (`telefone` fora do padrão BR 12–13 dígitos) e os **66 sem nome** *só se* o dono aprovar limpeza total (ver §6) — decisão pendente.
   - `DELETE FROM products` + re-seed com **preços reais informados pelo dono**.
   - VACUUM (SQLite) para não deixar lixo de página.
3. **Dados reais a inserir (fornecidos pelo dono):**
   - Catálogo: nome, preço e estoque real de cada gás/água.
   - Contatos-chave (se aprovar limpeza total de clients): os números que realmente importam hoje.
4. **O que NUNCA se toca:** `auth_*`, `system_settings`, `permissions`, `role_permissions`, sessões.

Rollback: restaurar o backup (o app nem precisa fechar — migração roda no boot seguinte).

---

## 3. Plano de reorganização do frontend

### 3.1 Navegação
- `Sidebar.tsx`: vira estrutura de **grupos** (colapsáveis) com sub-itens; `DashboardLayout`/`MobileSidebar` acompanham. Ícone por grupo, badge de estado no WhatsApp (contas conectadas).
- Rotas novas: `/whatsapp/contacts` (recebe a antiga página de contatos), rotas dos grupos mantêm paths atuais de páginas (zero perda de deep-link interno).
- Rotas **removidas**: `/contacts`, `/whatsapp/web` (vira seção), `/intelligence` (redirect 301 interno para `/` e depois deletada — sem fantasma).

### 3.2 Bolinha flutuante da IA
- `FloatingCopilot.tsx`: FAB canto inferior-direito (z-index sobre tudo, some em `/login` e `/driver/*`), abre **painel slide-over** (380px,glass/blur, transição suave) com o CopilotPage adaptado (chat + tools).
- Persistência: aberto/fechado + tamanho no localStorage.
- `IntelligencePage.tsx` e a rota são **deletados**.

### 3.3 WhatsApp como módulo único
- `WhatsAppPage` (Contas & Conexão) ganha **abas**: Contas | WhatsApp Web (seção só aparece com flag ON).
- Conversas continua `/whatsapp` como home do módulo (lista à esquerda, thread à direita — já feito).
- Campanhas/Automações como sub-itens no menu.

### 3.4 Polimento visual (padrão único)
- Design tokens já existentes (Tailwind + shadcn-like): padronizar cards, espaçamentos, tipografia, estados vazios, skeletons em TODOS os grupos (mesma receita visual do Dashboard).
- Micro-interações: hover consistente, transições 150–200ms, foco visível.

---

## 4. Plano de reorganização do backend

### 4.1 Pastas por módulo (arquivos movem, rotas estáveis)
```
presentation/api/
├── whatsapp/            # TODO o WhatsApp
│   ├── accounts.py      ← whatsapp.py
│   ├── gateway.py       ← whatsapp_gateway.py
│   ├── automation.py    ← whatsapp_automation.py
│   ├── cloud_webhook.py ← whatsapp_cloud_webhook.py
│   └── contacts.py      ← contacts_crm.py  (ROTA MUDA: /clients/contacts → /whatsapp/contacts)
├── catalog/
│   ├── products.py      (rota /products mantida)
├── catalog/
│   ├── products.py      (rota /products mantida)
│   └── inventory.py     (rota /inventory mantida)
├── logistics/           # delivery*, dispatch, driver_* (rotas mantidas)
├── finance/             # finance, payments, reports (rotas mantidas)
└── core/                # auth, health, settings, admin...
```
- **Única mudança de URL**: `/clients/contacts` → `/whatsapp/contacts` (consumidor único = nossa página; router antigo **deletado**).
- `main.py` importa dos novos módulos; zero rota órfã; nada de lógica duplicada (o gateway é o único caminho de entrada/saída de mensagens).

### 4.2 Migração
- SCHEMA_VERSION v4 com os passos do §2, codificada como função idempotente em `init_db.py` (padrão atual) + doc `docs/migrations/2026-09-reorg-cleanup.md`.

### 4.3 Integridade
- Serviço WhatsApp (Node/Baileys) **não é tocado** — ponte, pareio, envio e recebimento intactos.
- Testes de regressão completos rodam em cada fase (números atuais: backend 1446, frontend 194, whatsapp 94, desktop 41).

---

## 5. Riscos e validações antes de publicar

| Risco | Mitigação |
|---|---|
| Apagar 6917 clients (irreversível) | Backup duplo + **decisão explícita do dono** (§6) antes da migration |
| Preços placeholder virarem catálogo oficial | NÃO publicar sem preços reais do dono (§6) |
| Quebrar página de Contatos ao mudar rota | Único consumidor é nossa UI — mudar api client + router juntos, remover rota antiga no mesmo commit |
| Bolinha da IA quebrar layout existente | FAB fora do fluxo dos módulos; testes do CopilotPage adaptados |
| Flag WhatsApp Web escondida quebrar teste F0–F5 | Seção respeita a MESMA flag; re-executar F0 (QR) e F5 (flag off) pós-mudança |
| Regressão no fluxo de mensagens | E2E completo após cada fase: msg in → conversa → IA → pedido → Pedidos |
| Links antigos (/intelligence) | Rota removida sem redirect é aceitável (app desktop, sem SEO) |

**Checklist de publicação:** suítes 100% verdes → E2E WhatsApp de ponta → smoke manual dos grupos do menu → pareio OK → release v1.1.6.

---

## 6. Decisões pendentes do dono (bloqueiam execução)

1. **Clientes (6917):** (a) limpeza TOTAL — só entram de novo quem mandar mensagem (auto-cadastro) ou os que você informar; ou (b) limpeza cirúrgica — apagar só os 5 LID-lixo (+66 sem nome) e manter os 6846 reais sincronizados.
2. **Preços reais** do catálogo (gás P13, P45, água 20L e qualquer outro produto).
3. **Segmentos / Recompra / Cupons:** confirmar que viram sub-itens de **Clientes** (proposta) ou prefere grupo "Marketing" separado.
4. **WhatsApp Web:** confirmar como seção dentro de *Contas & Conexão* (ligável pela flag que já existe).

---

## 7. Fases de execução (após aprovação)

| Fase | Escopo | Validação |
|---|---|---|
| **F0** | Decisões do §6 + backup duplo | dono confirma |
| **F1** | Migration v4 (limpeza + catálogo real) | contagens pós-limpeza + app sobe |
| **F2** | Sidebar em grupos + rotas (frontend) | 194 testes + smoke dos grupos |
| **F3** | WhatsApp único (Contatos absorvido, Web como seção) | F0–F5 do painel + E2E mensagem |
| **F4** | Bolinha da IA + delete IntelligencePage | testes do Copilot + visual |
| **F5** | Backend em pastas + rota contacts + limpeza órfãos | 1446 testes + grep sem rota morta |
| **F6** | Polimento visual global + release v1.1.6 | checklist §5 completo |
