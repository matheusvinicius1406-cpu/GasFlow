# GasFlow — Status de Entrega (QA / readiness)

| | |
|---|---|
| **Data** | 2026-10-24 |
| **Base auditada** | branch `parallel/freebuff-infra`, HEAD `28c7ff3` (OPS-01B) sobre `213c187` (OPS-01A) |
| **Checkpoints anteriores** | SEC-02 `544dca6` · SEC-01C `656d2de` · SEC-01/01B `d135caf` |
| **Escopo desta frente** | QA, readiness e documentação de entrega. **Sem** novas features, **sem** alterar código de produção |
| **O que NÃO foi executado** | Docker (`up`), Postgres, Nginx real, migração/backup (OpenCode), WhatsApp real, Android físico, deploy, push/merge |
| **Veredito** | **PRONTO PARA DEMONSTRAÇÃO** (dados fictícios, no GasFlow Desktop). **NÃO** pronto para homologação completa nem para produção — ver §6/§7 |

> Este documento descreve **o que existe e o que está comprovado**, não o que se
> pretende entregar. Uma tela existente não é prova de funcionamento: cada linha
> cita teste, rota, serviço ou ausência de cobertura.

---

## 1. Classificações usadas

| Classe | Significado |
|---|---|
| **VALIDADO AUTOMATICAMENTE** | Há teste automatizado que cobre o caminho principal **e** ele foi executado nesta sessão (ou está no CI); sem dependência física |
| **IMPLEMENTADO / NÃO VALIDADO FISICAMENTE** | Código + testes de lógica, mas o comportamento depende de aparelho, sessão real ou stack Docker que não foi exercitada |
| **PARCIAL** | Existe caminho funcional, mas falta uma parte do contrato, da persistência ou da interface |
| **BLOQUEADO** | Dependência externa declarada impede o fluxo (ex.: lib nativa, permissão Android, hardware) |
| **NÃO IMPLEMENTADO** | Não existe no código |

---

## 2. Inventário funcional (web/desktop + backend)

| Área | Estado | Evidência | Limitação | Próxima ação |
|---|---|---|---|---|
| **Login / sessão** | VALIDADO AUTOMATICAMENTE | `frontend/.../LoginPage.test.tsx`, `ChangePasswordGate.test.tsx`, `backend/tests/test_auth_negative_matrix.py`, `test_auth_persistence.py`; gate de senha no HTTP (403) e no WS (4003) | E2E `e2e/tests/auth.spec.ts` não executado hoje (exige stack Docker) | Rodar E2E no nível B |
| **Multi-tenant / RBAC** | VALIDADO AUTOMATICAMENTE | `test_cross_tenant_isolation.py` e `test_auth_negative_matrix.py` executados hoje (265 testes verdes no bloco) | — | Manter no gate de CI |
| **Dashboard** | VALIDADO AUTOMATICAMENTE (backend) / PARCIAL (UI) | `DashboardPage.test.tsx`; router `dashboard`; 2 arquivos de teste citam `/dashboard` | Testes de frontend não executados hoje (sem `node_modules`) | Rodar `npm test` no nível B |
| **Clientes** | VALIDADO AUTOMATICAMENTE | `CustomerFormPage`/`CustomerDetailPage` + testes; `e2e/tests/customers.spec.ts`; 9 arquivos de teste backend citam `/clients` | E2E não executado hoje | Nível B |
| **Múltiplos endereços** | **NÃO IMPLEMENTADO** | `ClientCreate` em `presentation/schemas/client.py` tem **um** endereço (`rua`, `numero`, `complemento`, `referencia`, `bairro`); não existe entidade `ClientAddress` nem endpoints de endereço | Cliente com 2+ endereços (casa/trabalho) não é representável; o pedido herda o endereço do cadastro | Decidir se entra no escopo comercial antes de prometer |
| **Produtos** | VALIDADO AUTOMATICAMENTE | `ProductsPage`/`ProductFormPage` + testes; `e2e/tests/products.spec.ts`; 7 arquivos citam `/products` | E2E não executado hoje | Nível B |
| **Pedidos / criação** | VALIDADO AUTOMATICAMENTE | `OrderFormPage` + testes; `e2e/tests/orders.spec.ts`; 11 arquivos citam `/orders`; `PATCH /orders/{codigo}/status` | E2E não executado hoje | Nível B |
| **Atualização de status do pedido** | VALIDADO (web) / PARCIAL (app) | `PATCH /orders/{codigo}/status` e transições de domínio em `domain/delivery/delivery.py`; testes `test_delivery.py` (executado) | O app do entregador **não** tem ação de “cheguei” (ver §3) | Alinhar app ⇄ domínio |
| **Entregadores (cadastro)** | VALIDADO AUTOMATICAMENTE | `DriversPage`/`DriverFormPage` + testes; `e2e/tests/drivers.spec.ts`; `test_driver_crud.py` | E2E não executado hoje | Nível B |
| **Atribuição / roteirização** | PARCIAL | `dispatch` router, `DispatchScorer`, plano de rota persistido; flags `DELIVERY_SMART_ROUTING_ENABLED` **default false** (ver `docs/STATUS_E_PLANO.md`) | Rota “inteligente” desligada por padrão; demo usa ordem manual | Ligar flag só em homologação |
| **Pagamentos / PIX** | VALIDADO AUTOMATICAMENTE (contrato) | `test_payment_contract.py` (executado), `test_payment_persistence.py`; `e2e/tests/pix.spec.ts`; BR Code local (`qrcode`+`Pillow`, sem `pypix`) | Sem PSP real; PIX é estático/QR local | Validar cobrança real é decisão de negócio |
| **Financeiro** | VALIDADO AUTOMATICAMENTE | `test_finance_period_report.py` (executado), `test_finance_*`; `CentralFinanceiraPage` + testes; `e2e/tests/central-financeira.spec.ts` | E2E não executado hoje | Nível B |
| **Relatórios** | VALIDADO AUTOMATICAMENTE (backend) | `test_delivery_report.py` (executado), `test_report_fixes.py`, `test_finance_reports_p2.py` | Exportações/planilhas UI não validadas nesta sessão | Nível B |
| **WebSocket / realtime** | VALIDADO AUTOMATICAMENTE (backend) | `test_realtime.py` + `test_realtime_pubsub.py` (executados); `/ws` exige token (fechamento 4001 sem credencial válida — coberto no teste de readiness) | Não validado com 2 dispositivos reais simultâneos | Teste de campo |
| **Rastreamento (ingest + LGPD)** | PARCIAL | `test_driver_location_ingest.py` (executado), `test_driver_location_history.py`, janela de trabalho com 403 fora dela; app envia `/driver/location` a cada `tracking_interval_seconds` | **Sem GPS físico**; app só captura em primeiro plano (ver §2.1) | Aparelho + caminhada de teste |
| **Rastreio público (link)** | VALIDADO AUTOMATICAMENTE | `/public/tracking/{token}` devolve só `driver_id`, `latitude`, `longitude`, `updated_at` (teste de readiness garante ausência de PII); `PublicTracking.tsx` + `trackingPages.test.tsx` | Token/expiração não testados com link real compartilhado | Nível B |
| **WhatsApp (gateway)** | PARCIAL | 13 arquivos de teste backend citam `/whatsapp`; `test_whatsapp_gateway.py` executado; SEC-02 (auth fail-closed, exposição restrita) | **Sessão real nunca foi exercitada** nesta máquina; gateway não rodou nesta sessão | Pareamento supervisionado em homologação |
| **Campanhas** | PARCIAL | Rotas de campanha + `CampaignWizardPage`/`CampaignHistoryPage`; testes de limites/automation (`test_whatsapp_limits.py`, `test_whatsapp_automation.py`) | Envio real nunca validado; caps dependem de configuração do tenant | Teste com número de teste |
| **App do entregador (APK)** | **PARCIAL / BLOQUEADO fisicamente** | Código + testes de lógica + `mobile/android` com receita de build (`android/BUILD.md`); pendência herdada da v1.2.1 (aparelho fora do `adb`) | Nenhuma execução em aparelho real nesta ou nas últimas frentes | Instalar APK em aparelho de teste |
| **GPS** | PARCIAL | `logic/tracking.ts` + `permissions.ts` (ACCESS_FINE/COARSE); testes de gate/cadência executados (35 verdes) | Primeiro plano apenas; background **BLOQUEADO** (§2.1) | Trocar lib / elevar minSdk |
| **Offline** | PARCIAL | `OfflineQueue` testada (`offlineQueueLocation.test.ts`, `logic.test.ts` — 9 verdes) | Fila no app é **em memória** (`wired.tsx`: `queueItems` array) → morre ao fechar o app | Persistir fila (MMKV/SQLite) |
| **Prova de entrega** | PARCIAL | Backend: `ProofType` (`PHOTO`, `SIGNATURE`, `OTP`, `MANUAL_CONFIRMATION`) + `POST /api/v1/driver/proofs` (metadata); app envia `proof_type: "NONE"` | Sem foto, assinatura ou código no app; “NONE” não é valor do enum (fica gravado como texto) | Definir requisito comercial |
| **Notificações** | **NÃO IMPLEMENTADO (push)** | Nenhuma dependência FCM/Notifee no `mobile/package.json` nem no manifest; comunicação é WS + polling | Sem aviso com app fechado/tela bloqueada | Backlog |
| **Campanhas/CRM/contatos** | VALIDADO AUTOMATICAMENTE (backend) | `test_contacts_*`, `test_crm.py`, `test_whatsapp_automation.py` | UI não exercitada hoje | Nível B |

### 2.1 Bloqueio conhecido do rastreamento em segundo plano

`mobile/README.md` documenta o bloqueio: `@ikolvi/tracelet@0.1.0-alpha.1` não
compila (`Unresolved reference: core`), traz `<service>` fora de `<application>`
(AAPT rejeita) e exige `minSdk 26` (app usa 24). Hoje:

- manifest tem `ACCESS_FINE_LOCATION`/`ACCESS_COARSE_LOCATION`, **sem**
  `ACCESS_BACKGROUND_LOCATION` e **sem** foreground service;
- captura é `@react-native-community/geolocation` em **primeiro plano**, atrás
  da costura `logic/backgroundTracking.ts` (adaptador já testado com fake);
- consequência prática: tela do app precisa ficar aberta durante a rota.

---

## 3. Contratos mobile ↔ Home Server

Fontes: `mobile/src/logic/api.ts` (URLs), `frontend/nginx.conf` (borda),
`docker-compose.homeserver.yml` (única porta 80). O app usa **sempre a raiz** da
URL digitada (não `/api`).

| Cliente | URL usada | Esperada no Home Server | Compatível? | Ação |
|---|---|---|---|---|
| App — default de dev | `http://10.0.2.2:8000` (só emulador, mantido de propósito) | `http://<ip>` (porta 80) | **Não em campo** | Orientar digitar `http://<ip>`; default de emulador não vale em celular real |
| App — placeholder da tela de login | `http://IP_DO_SERVIDOR` + hint da porta 80 (frente MOBILE-P0) | `http://<ip>` (porta 80) | **Sim** | — |
| App — `/auth/login`, `/auth/me`, `/auth/change-password` | raiz | nginx `location /auth/` → backend sem strip (OPS-01A) | **Sim** | Validar no laboratório OPS-01B |
| App — `/driver/*` (deliveries, me, start, arrive, complete, fail, location) | raiz | nginx `location /driver/` → backend sem strip | **Sim** | Validar no laboratório |
| App — `/ws?token=…` | raiz | nginx `location /ws` com Upgrade (3600 s) | **Sim** | Teste com app aberto na LAN |
| App — update OTA | `<base>/api/v1/mobile/version` | nginx `/api/v1/` **sem strip** | **Sim** | Apontar `download_url` para o host do servidor |
| Web/console | `/api/*` | nginx `/api` com strip | **Sim** | — |
| Web — rastreio público | `/api/public/tracking/{token}` | strip → backend `/public/tracking/{token}` | **Sim** | — |
| Pareamento WhatsApp | `:3001` (dev) | rede interna apenas (prod) | n/a | Pareamento por túnel/administrativo |
| Relay/nuvem | `cloudBaseUrl` (configurável) | túnel HTTPS (Cloudflare) | Sim (config) | Definir domínio (OPS-01C) |

**Regra de ouro:** no Home Server, o app deve apontar para `http://<ip>` **sem
`:8000`**. O `docker-compose.prod.yml` + `docker-compose.homeserver.yml` publicam
somente a porta do frontend.

### 3.1 Lacunas de contrato encontradas (não corrigidas — código congelado)

| # | Achado | Evidência | Impacto |
|---|---|---|---|
| C1 | App envia `client_action_id`; backend usa `idempotency_key` (`ActionRequest`) → o id do app é ignorado | `mobile/src/logic/api.ts` × `driver_api.py:147` | Replay offline não tem dedupe no servidor; retry pode receber 400/409 em vez de replay |
| C2 | App **nunca** chamava `/driver/deliveries/{id}/arrive`; backend exige `ARRIVED` para concluir | `grep arrive mobile/src` vazio; `driver_api.handle_complete_delivery` | **CORRIGIDO (frente MOBILE-P0):** ação “Cheguei ao destino” no app + `deliveryFlow.ts` espelhando as regras `can_*` |
| C3 | App envia `{ reason }` para falha; backend lê `failure_reason` | `wired.tsx` `onFail` × `ActionRequest` | Motivo da falha cai em `OTHER` |
| C4 | `DeliveryRecord.to_dict()` não envia `phone`; app espera `phone` para o botão “Ligar” | `delivery_persistence_model.py:107` × `api.ts DeliveryDTO` | Botão de ligação sem número |
| C5 | App enviava `proof_type: "NONE"`; enum do domínio não tem `NONE` | `wired.tsx` × `domain/delivery/delivery.py ProofType` | **CORRIGIDO (frente MOBILE-P0):** conclusão envia `MANUAL_CONFIRMATION` (valor do enum) |

Cada item está classificado em `PENDENCIAS_BLOQUEANTES.md`.

---

## 4. Realidade de hoje × stack nova

| Item | Hoje (operacional) | Stack nova (preparada, não exercitada) |
|---|---|---|
| Backend | `gasflow-backend.exe` do Desktop em `127.0.0.1:8000` | container `backend` (rede interna) |
| Portal web | `FRONTEND_DIST` embutido no backend | nginx do container `frontend` |
| Banco | SQLite `%APPDATA%\gasflow-desktop\gasflow.db` | PostgreSQL + Alembic |
| WhatsApp | sessão no userData do Desktop | gateway container + volumes `*_auth` |
| URL do app | `http://<ip>:8000` funciona | `http://<ip>` (porta 80) |
| Migração de dados | **pendente (OpenCode)** | backup/restore/migração em outra frente |

O OPS-01B (commit `28c7ff3`) deixou o perfil Home Server configurado e
**isolado** (`gasflow-hs-lab`), mas **nada foi migrado**: continuar no Desktop é
o caminho seguro para a demo de hoje.

---

## 5. DEMONSTRÁVEL HOJE

Usando o **GasFlow Desktop** operacional, com dados fictícios, em 20–30 min:

1. Login e troca de senha (gate).
2. Dashboard e navegação por permissões.
3. Cliente novo com endereço único.
4. Produto novo.
5. Pedido novo (cliente + produto + quantidade).
6. Atribuição de entregador.
7. Transições de status até `ARRIVED`.
8. Rastreio público por link (`/track/{token}`).
9. Conclusão da entrega no desktop (prova `MANUAL_CONFIRMATION`).
10. Financeiro/histórico do pedido.
11. WhatsApp **somente** em modo seguro (ver roteiro, passo 12).

Passo a passo detalhado com pré-requisitos, resultados esperados e plano B:
`docs/delivery/ROTEIRO_DEMO.md`.

---

## 6. HOMOLOGAÇÃO PENDENTE

Depende de stack real (Docker + Nginx + Postgres + smoke) e/ou de aparelho:

- `docker compose` do perfil Home Server subindo com 5 serviços `healthy`.
- `scripts/smoke-test.sh` verde pela borda (`http://127.0.0.1:8088` no lab).
- E2E Playwright (8 specs) contra a stack.
- Login + rotas `/driver/*` do app passando pela nginx (porta 80).
- WebSocket do app conectando pela borda.
- Restore de backup e comparação de dados (**OpenCode**).
- APP em aparelho: login, lista de entregas, start, GPS em movimento, completar
  (com operador marcando `ARRIVED`), modo avião → fila → reconexão.
- WhatsApp: pareamento supervisionado e envio para número de teste.

---

## 7. PRODUÇÃO PENDENTE

Nada abaixo foi cumprido; **não declarar produção**:

- migração SQLite → PostgreSQL ensaiada **e** com restore validado (OpenCode);
- backup agendado + cópia off-host + teste de restore;
- rollback documentado e ensaiado (`ROLLBACK_OPERACIONAL.md` é só procedimento);
- Android físico validado (GPS, permissões, offline real, kill/restart);
- WhatsApp real validado com anti-ban e número dedicado;
- domínio/URL fixa (túnel nomeado) — pendência de orçamento;
- HDD → SSD e plano de energia (servidor doméstico);
- aprovação formal da empresa e janela de corte.

---

## 8. Evidências de teste desta sessão

| Comando | Resultado | Duração | Limitação |
|---|---|---|---|
| `pytest tests/test_delivery_readiness_mobile_contracts.py` | **10 passed** | ~18 s | 2 testes validam documentação (este pacote) |
| `pytest test_driver_self_actions test_driver_mobile test_driver_location_ingest test_driver_api test_mobile_version test_public_tracking` | **150 passed** | ~60 s | Banco SQLite efêmero; sem hardware |
| `pytest test_order_domain test_delivery test_delivery_report test_finance_period_report test_payment_contract test_realtime test_whatsapp_gateway test_auth_negative_matrix test_cross_tenant_isolation` | **265 passed** | ~37 s | Idem |
| `node --test` (mobile: backgroundTracking, tracking, offlineQueueLocation, config, logic) | **44 passed** | ~2 s | `auth.test.ts` e `session.test.ts` não rodam sem `node_modules` (`zustand` ausente) |
| `ruff check` / `ruff format --check` nos arquivos novos | OK | — | — |
| `git diff --check` | OK | — | — |
| Scan de segredo/PII nos arquivos novos | nenhum achado | — | — |
| `docker compose config` (perfil Home Server + lab) | OK (ver OPS-01B) | — | CLI sem daemon |
| Frontend `npm test` (90 arquivos) | **não executado** | — | `frontend/node_modules` ausente; instalar dependências grandes foi evitado |
| E2E Playwright (8 specs) | **não executado** | — | Exige stack Docker (`docker-compose.e2e.yml`) |
| Suíte backend completa (~2.310 casos em 20/10) | **não executada hoje** | — | Evitado rodar suíte gigante com o OpenCode usando CPU/disco |

Nenhum serviço externo, Docker, Postgres, WhatsApp ou aparelho foi acionado.

---

## 9. Depende de Android físico (não validável aqui)

Login no aparelho · persistência de sessão entre execuções · GPS real e
permissões de localização · comportamento com tela bloqueada/app em background ·
modo avião e reconexão · fila offline sobrevivendo a matar o app · Waze/Maps ·
câmera/assinatura (não implementadas) · rotação de tela/teclado · APK assinado.

---

## 10. Resumo executivo

- **O sistema web/desktop está funcional e testado** (415 testes backend
  executados hoje, sem falhas).
- **O app do entregador está implementado, mas nunca foi validado em aparelho**
  e ainda tem duas lacunas funcionais relevantes (fila offline volátil e GPS
  só em primeiro plano); a conclusão de entrega sem `arrive` foi corrigida
  pela frente MOBILE-P0.
- **A stack Home Server está configurada, não operada**: backup/restore/migração
  são da frente OpenCode e seguem pendentes.
- **A demo de hoje deve ser feita no Desktop**, com dados fictícios, e o
  WhatsApp em modo seguro.
