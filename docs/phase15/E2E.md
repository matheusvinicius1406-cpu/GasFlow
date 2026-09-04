# E2E — Testes End-to-End (Playwright)

## Visão Geral

Testes end-to-end que exercitam o **stack real completo** do GasFlow
(nginx → backend → PostgreSQL) exatamente como um usuário faz, via browser
Chromium controlado pelo Playwright.

- **Ambiente**: `docker-compose.e2e.yml` (postgres + redis + backend +
  frontend/nginx), sem o serviço whatsapp (depende de pareamento manual).
- **Entrada pública única**: `http://localhost:8080` (nginx do frontend);
  `/api` é prefixo que o nginx remove antes de encaminhar ao backend — o
  Playwright usa a mesma porta que um navegador real.

## Fluxos Cobertos

| ID | Spec | O que valida |
|----|------|--------------|
| E2E-01 | `auth.spec.ts` | Login inválido mostra erro; rota protegida redireciona p/ `/login`; sessão de admin (storageState) acessa o dashboard |
| E2E-04 | `products.spec.ts` | Criar produto pela UI → detalhe com o nome no título |
| E2E-05 | `customers.spec.ts` | Criar cliente pela UI → detalhe com o nome no título |
| E2E-06 | `drivers.spec.ts` | Criar motorista pela UI → volta para a lista |
| E2E-02/03 | `orders.spec.ts` | Seed de cliente+produto com estoque via API → criar pedido pela UI → confirmar status (PENDING → CONFIRMED) |
| E2E-09/10 | `pix.spec.ts` | Configurar chave PIX + gerar payload BR Code com QR válido |

## Como Rodar

```bash
# 1. Sobe o stack E2E (build das imagens na primeira vez)
docker compose -f docker-compose.e2e.yml up -d --build

# 2. Instala o Playwright + Chromium
cd e2e
npm ci
npx playwright install chromium

# 3. Roda a suíte (global-setup faz 1 login real via API e salva em .auth/)
npx playwright test

# (opcional) abre o relatório HTML
npx playwright show-report

# 4. Derruba o stack
docker compose -f docker-compose.e2e.yml down
```

## Arquitetura dos Testes

```
e2e/
├── playwright.config.ts      # chromium, 1 worker (DB compartilhado), storageState
├── global-setup.ts           # 1 login via API → .auth/admin.json (evita 429 do rate limiter)
├── tests/
│   ├── helpers.ts            # uid/uidPhone únicos + seeds via API (cliente/produto/estoque)
│   ├── auth.spec.ts
│   ├── customers.spec.ts
│   ├── drivers.spec.ts
│   ├── orders.spec.ts
│   ├── pix.spec.ts
│   └── products.spec.ts
└── .auth/                    # sessão do admin (gitignored)
```

### Decisões de Design

- **Um login por run**: o backend tem rate limiter de login (5 tentativas/5
  min). O `global-setup` loga uma única vez via API e persiste em
  `storageState`; os specs reutilizam essa sessão. Isso elimina flakiness
  por 429 e acelera a suíte.
- **Seeds via API real**: pedidos exigem cliente + produto **com estoque na
  tabela Inventory** (não `Product.estoque`). Os seeds usam os mesmos
  endpoints `/api/...` do produto, passando pelo nginx.
- **Dados únicos por run**: nomes e telefones com sufixo `Date.now()` —
  o DB do compose persiste em volume entre runs, e o backend rejeita
  telefone duplicado em clientes.
- **Selectors reais**: nenhum `data-testid` inventado; os testes usam
  placeholders/labels/roles que existem de fato na UI (ex.: placeholder
  `Ex: Gás P13, Água 20L`, label `Tipo *`).

## Bugs Reais Encontrados (e corrigidos)

### 1. `AuthService` singleton compartilhava uma única Session SQLAlchemy

**Sintoma (E2E)**: ao abrir o detalhe de um produto recém-criado, o backend
retornava 500 `"This session is in 'prepared' state"` para GETs paralelos
(detalhe do produto + inventário + handshake do WebSocket). Depois do
primeiro 500, todos os requests autenticados continuavam falhando até o
restart do processo.

**Causa raiz**: `get_auth_service()` devolve um singleton que guarda **uma**
`Session` SQLAlchemy criada uma única vez e reutilizada por todas as
requests. FastAPI executa endpoints/dependencies síncronos num threadpool
(e a validação do WebSocket roda na event loop) — threads concorrentes
intercalavam `commit()`/queries na mesma Session, corrompendo a máquina de
estados interna da transação ("prepared state"). O `curl` sequencial não
reproduzia; só o browser com requests paralelos.

**Correção**: `app/application/security/auth_service.py` — decorador
`_db_synchronized` aplicado aos métodos públicos que tocam o DB: serializa
com um `RLock` por instância e faz `rollback` em caso de exceção, para um
erro pontual não envenenar a sessão compartilhada para os requests
seguintes.

**Teste de regressão**: `tests/test_security.py::TestConcurrentSharedSession`
— 6 threads × 10 `validate_token` na mesma service DB-backed. Sem o lock,
5/6 threads falham com `IllegalStateChangeError ... '_prepare_impl()'
already in progress`; com o lock, 60/60 passam e a sessão segue utilizável.

### 2. Fluxos E2E não eram re-executáveis

Clientes/motoristas usavam telefone fixo; o 2º run esbarrava na validação
de telefone duplicado (409 silencioso no formulário). Corrigido com
`uidPhone()` (11 dígitos únicos) nos specs e nos seeds de `helpers.ts`.

## Resultados

```text
8 passed (≈10s) — rodado 2× consecutivas, estável
```

## CI

Job `e2e` em `.github/workflows/ci.yml`: sobe `docker-compose.e2e.yml`,
instala chromium e roda `npx playwright test` (1 worker). Relatório HTML é
anexado como artifact em caso de falha.

## Fora de Escopo (documentado)

- **Deliveries/Realtime/WhatsApp**: exigem segunda identidade logada
  (motorista) e/ou instância real de WhatsApp — cobertos por testes
  unitários de integração (backend 1176) e pela validação live do WS
  (RT-01). Não há tela que dispare `delivery.*` no frontend admin.
- **Firefox/WebKit**: apenas chromium é baixado/executado para manter CI
  rápido; basta adicionar projetos no `playwright.config.ts`.
