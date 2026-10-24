# GasFlow — Checklist de Aceite

Três níveis **independentes**. Não promover item de nível por analogia: nível A
não prova nível B; nível B não prova nível C.

| Nível | Pergunta que responde | Ambiente | Quem assina |
|---|---|---|---|
| **A — Demo** | “Dá para mostrar hoje?” | GasFlow Desktop + dados fictícios | Time técnico |
| **B — Homologação** | “Funciona na stack real?” | Docker + Nginx + Postgres + restore + smoke | Time técnico + empresa |
| **C — Produção** | “Pode atender cliente real?” | Stack + campo + backup/rollback + aprovação | Empresa |

Legenda: `[x]` comprovado nesta frente · `[ ]` pendente · `[~]` comprovado com
ressalva (plano B documentado).

---

## Nível A — Demo (pode ser demonstrado com dados fictícios)

Ambiente: GasFlow Desktop (`127.0.0.1:8000`), SQLite do desktop, prefixo `DEMO`.

- [x] Login e gate de troca de senha — testes de frontend/backend citados em
      `STATUS_DE_ENTREGA.md` §2.
- [x] Dashboard responde com dados fictícios — `DashboardPage.tsx` + teste.
- [x] Criar cliente com endereço único — `ClientCreate` (`rua`, `numero`,
      `bairro`); sem múltiplos endereços (declarar limitação).
- [x] Criar produto — `ProductsPage` + `e2e/tests/products.spec.ts` (spec não
      executado nesta sessão).
- [x] Criar pedido com cliente + produto — `OrderFormPage` + `orders.spec.ts`.
- [x] Atribuir entregador — `PATCH /orders/{codigo}/assign-driver`.
- [x] Transições de status até `ARRIVED` — `PATCH /orders/{codigo}/status` +
      domínio `DELIVERY_TRANSITIONS`.
- [x] Rastreio público por link (`/track/{token}`) — `/public/tracking/{token}`
      sem PII (teste de readiness).
- [x] Concluir entrega no desktop (prova manual) — `complete` exige `ARRIVED` e
      aceita `MANUAL_CONFIRMATION`.
- [x] Financeiro/histórico coerentes — `test_finance_period_report.py`.
- [~] WhatsApp **somente leitura** — sem disparo; pareamento real fora da demo.
- [~] App do entregador — só com aparelho preparado; conclusão exige operador.
- [x] Backup do SQLite feito **antes** da demo (cópia local).
- [ ] Roteiro ensaiado de ponta a ponta pelo apresentador.
- [ ] Registro da demo (quem, quando, o que funcionou/plano B).

**Critério de aceite A:** todos os passos do `ROTEIRO_DEMO.md` executados ou com
plano B declarado; nenhuma mensagem de WhatsApp enviada; nenhum dado real
exposto.

Evidência de apoio: `backend/tests/test_delivery_readiness_mobile_contracts.py`
(10 testes), `STATUS_DE_ENTREGA.md` §8.

---

## Nível B — Homologação (exige stack real)

Ambiente: `docker-compose.prod.yml` + `docker-compose.homeserver.yml`
(+ `.lab` para laboratório isolado), Nginx, Postgres. **Nada disto foi executado
nesta frente** (proibido subir Docker aqui).

Infra:

- [ ] `docker compose config -q` verde nos 4 modos (real/lab × com/sem
      `--profile observability`).
- [ ] `deploy/home-server/verify-static.sh` verde no host do servidor.
- [ ] 5 serviços do core `healthy` (`docker compose ps`).
- [ ] `./scripts/smoke-test.sh http://<host>` verde (rotas M1/O2).
- [ ] `/metrics` → 404 na borda e 401 sem Bearer na origem.
- [ ] Observabilidade opcional coletando (sem 401 no Prometheus).
- [ ] Cada serviço abaixo do limite de RAM (`docker stats`).
- [ ] Reinício do host → stack volta sozinha (`unless-stopped`).
- [ ] GasFlow Desktop continua funcionando em `127.0.0.1:8000` durante o lab.

Dados e integração:

- [ ] Postgres criado do zero por `alembic upgrade head`.
- [ ] Restore de um dump de teste em banco limpo (**DEPENDÊNCIA OPENCODE**).
- [ ] Migração SQLite → Postgres ensaiada em cópia (**DEPENDÊNCIA OPENCODE**).
- [ ] Contagem de pedidos/clientes antiga × novo banco confere.
- [ ] E2E Playwright (8 specs) contra a stack.
- [ ] App na LAN: login por `http://<ip>` (**sem `:8000`**), `/driver/*`, `/ws`.
- [ ] Update OTA: `/api/v1/mobile/version` com `download_url` acessível.
- [ ] WhatsApp: pareamento com **número de teste** e envio para número de teste.
- [ ] Backup manual + cópia off-host do ambiente de homologação.

**Critério de aceite B:** smoke + E2E verdes; restore e migração reproduzíveis;
nenhuma porta pública além da borda; app falando com a stack pela porta 80.

---

## Nível C — Produção

Só depois de B fechado e com aprovação formal.

- [ ] Backup automático diário do Postgres + retenção definida + cópia off-host.
- [ ] **Restore validado** (banco restaurado, smoke verde, dados conferidos).
- [ ] Migração de produção ensaiada e aprovada, com janela e responsável.
- [ ] Rollback ensaiado (`ROLLBACK_OPERACIONAL.md`) com critério de abortar.
- [ ] Android físico: login, lista, start, GPS em movimento, offline real,
      matar/reabrir o app, conclusão do fluxo.
- [ ] GPS em segundo plano decidido: aceitar primeiro plano ou trocar a lib
      (hoje **BLOQUEADO** — `mobile/README.md`).
- [ ] Fila offline persistente (hoje em memória — **P1**).
- [ ] WhatsApp real com número dedicado, anti-ban configurado e monitoramento.
- [ ] Domínio/URL fixa + túnel (pendência de orçamento).
- [ ] HDD → SSD e plano de energia/suspensão do servidor.
- [ ] Segurança do host: firewall explícito, conta não-admin, disco cifrado.
- [ ] Plano de comunicação com clientes e treinamento dos entregadores.
- [ ] Aprovação por escrito da empresa.

**Critério de aceite C:** nenhum P0/P1 aberto em
`PENDENCIAS_BLOQUEANTES.md`; restore e rollback comprovados; campo validado.

---

## O que **não** vale como aceite

- Tela existente sem teste nem execução.
- “Compilou”, “subiu o container” ou “o teste de unidade passou” como prova de
  fluxo completo.
- Suíte histórica verde (2.310 casos em 20/10) sem execução na versão atual.
- Smoke verde com fallback em plano B (ex.: conclusão feita pelo operador).
