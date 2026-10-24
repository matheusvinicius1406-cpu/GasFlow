# GasFlow — Pendências Bloqueantes

Classificação usada:

- **P0** — impede a demonstração ou a operação básica do fluxo que será mostrado.
- **P1** — impede produção segura (perda de dados, fluxo incompleto, validação
  física ausente).
- **P2** — pode ser entregue depois, sem bloquear demo nem produção mínima.

Nenhum item abaixo foi corrigido nesta frente: QA/readiness documenta, não
implementa. Arquivos de produção e de outras frentes estão congelados.

---

## P0

### P0-1 — App do entregador não consegue concluir a entrega

- **Fato:** o backend exige `ARRIVED` para concluir
  (`handle_complete_delivery`), mas o app **nunca** chama
  `/driver/deliveries/{id}/arrive` (não há ação “cheguei” na UI nem no
  `api.ts`).
- **Evidência:** `backend/app/presentation/api/logistics/driver_api.py`
  (`if record.status != "ARRIVED"`), `mobile/src/logic/api.ts` (sem `arrive`),
  teste de readiness `test_known_mobile_contract_gaps_are_documented`.
- **Impacto:** fluxo 100% pelo app termina em `400 INVALID_STATE`; alguém no
  operador precisa marcar “chegou” antes.
- **Escopo:** bloqueia **demo do app**; não bloqueia a demo no Desktop.
- **Ação:** adicionar ação `arrive` no app (ou relaxar a regra de domínio com
  decisão de produto) — fora desta frente.

### P0-2 — App aponta para `:8000`, Home Server publica só a porta 80

- **Fato:** default `lanBaseUrl = http://10.0.2.2:8000` e placeholder do login
  `http://ip:8000`. O perfil Home Server publica **somente** o frontend (80);
  `backend:8000` não é exposto.
- **Evidência:** `mobile/src/logic/config.ts`, `mobile/src/screens/LoginScreen.tsx`,
  `docker-compose.prod.yml` (só `ports` do frontend), teste de readiness
  `test_home_server_url_guidance_is_documented`.
- **Impacto:** entregador que seguir o placeholder não conecta na stack nova.
- **Escopo:** bloqueia demo do app **contra a stack Home Server**; no Desktop
  (`127.0.0.1:8000`) o valor atual está correto.
- **Ação:** orientar `http://<ip>` na demo (feito no `ROTEIRO_DEMO.md`) e, na
  próxima janela de código, ajustar placeholder/default para a porta 80.

> **Não existe P0 para a demo no Desktop.** Login, cadastros, pedido, status,
> rastreio público, conclusão e financeiro estão cobertos por testes.

---

## P1

### P1-1 — Fila offline do app é volátil

- **Fato:** `wired.tsx` usa `const queueItems: QueueItem[] = []` (memória). O
  módulo `OfflineQueue` aceita storage persistente, mas o app não injeta
  SQLite/MMKV; o consentimento LGPD também usa storage em memória
  (`App.tsx`).
- **Impacto:** matar/fechar o app descarta ações pendentes (iniciar, concluir,
  falhar, posições). Requisito explícito de “recuperação após matar o app” não é
  atendido.
- **Evidência:** `mobile/src/containers/wired.tsx` linhas 62–70, `mobile/App.tsx`
  `setConsentStorage(createMemoryConsentStorage())`.
- **Ação:** injetar storage nativo persistente no boot; teste de replay após
  reinício.

### P1-2 — GPS só em primeiro plano (background bloqueado)

- **Fato:** `@ikolvi/tracelet@0.1.0-alpha.1` não compila (submódulo `core`
  ausente, `<service>` fora do `<application>`, `minSdk 26` vs 24). O manifest
  não declara `ACCESS_BACKGROUND_LOCATION` nem foreground service.
- **Impacto:** rastreio para quando a tela do app é bloqueada/minimizada.
- **Evidência:** `mobile/README.md` (§ bloqueio), `AndroidManifest.xml`,
  `wired.tsx` (`tracelet: null`).
- **Ação:** trocar/atualizar a lib ou elevar `minSdk`; validar em aparelho.

### P1-3 — Testes e typecheck do app não rodam no CI

- **Fato:** `.github/workflows/ci.yml` tem jobs de backend, frontend, whatsapp,
  agent, desktop, migrations e trivy — **nenhum** job mobile. `mobile` tem 7
  arquivos de teste e script `typecheck`, nunca executados pelo pipeline.
- **Impacto:** regressões no app passam despercebidas; o gate que existe não é
  usado.
- **Evidência:** grep de “mobile” nos workflows não retorna job; `mobile/package.json`
  (`test`, `typecheck`).
- **Ação:** adicionar job `mobile` (node ≥ 22, `npm ci`, `npm test`,
  `npm run typecheck`).

### P1-4 — Validação física do app pendente desde a v1.2.1

- **Fato:** aparelho Android fora do `adb`/sem homologação; nenhuma execução em
  hardware nesta ou nas últimas frentes.
- **Impacto:** login, permissões, GPS real, offline, câmera/assinatura e
  comportamento com tela bloqueada não comprovados.
- **Evidência:** `docs/STATUS_E_PLANO.md` (pendência herdada) e ausência de
  evidência de execução.
- **Ação:** aparelho de teste com APK assinado; execução do roteiro de campo.

### P1-5 — WhatsApp real nunca exercitado nesta máquina

- **Fato:** gateway não subiu nesta sessão; sessão real/QR dependem de ação
  humana; campanhas dependem de número dedicado e anti-ban.
- **Impacto:** envio real pode falhar/banir sem aviso; risco reputacional.
- **Evidência:** SEC-02 `544dca6` (auth e exposição), testes
  `test_whatsapp_*`, ausência de execução.
- **Ação:** homologação supervisionada com número de teste (nível B).

### P1-6 — Backup, restore e migração SQLite→Postgres (frente OpenCode)

- **Fato:** em execução por outro agente; nada validado aqui.
- **Impacto:** sem restore comprovado não há produção segura; migração sem
  ensaio pode perder pedidos.
- **Ação:** ver “DEPENDÊNCIA OPENCODE” abaixo.

### P1-7 — Idempotência do app não chega ao servidor

- **Fato:** app envia `client_action_id`; backend lê `idempotency_key`
  (`ActionRequest`). O campo do app é ignorado.
- **Impacto:** retry de ação já aplicada (timeout antes da resposta) volta como
  `400 INVALID_STATE`/`409`, mantendo o item “pending” até o backoff máximo.
- **Evidência:** `api.ts` × `driver_api.py:147`; teste de readiness.
- **Ação:** enviar `idempotency_key` no app (ou aceitar `client_action_id` no
  backend, com compatibilidade).

### P1-8 — Migration automática no boot sem backup prévio

- **Fato:** `docker-compose.prod.yml` roda `alembic upgrade head` no boot do
  backend; não há wrapper `pg_dump → up -d → smoke`.
- **Impacto:** migration falhando a meio caminho deixa o banco em estado
  indeterminado sem snapshot.
- **Evidência:** OPS-01A/OPS-00 (achado O4); compose do backend.
- **Ação:** wrapper de deploy com backup antes do `up`.

### P1-9 — Servidor doméstico em HDD + notebook

- **Fato:** disco HDD 5400 rpm, máquina compartilhada com o GasFlow Desktop;
  suspensão/energia não configuradas.
- **Impacto:** I/O vira gargalo; sleep/queda desliga atendimento.
- **Evidência:** `docs/OPS_00_HOME_SERVER_READINESS.md` (H1/H2), OPS-01B
  (perfil reduzido de RAM).
- **Ação:** SSD, plano de energia, no-break/bateria e host dedicado (OPS-01E).

### P1-10 — URL fixa de produção depende de domínio pago

- **Fato:** túnel rápido tem URL efêmera; URL fixa exige domínio (~US$10/ano).
- **Impacto:** link do rastreio/app muda a cada restart; operação inviável.
- **Evidência:** `relay/DEPLOY.md`, OPS-00 (R1).
- **Ação:** decisão de orçamento e túnel nomeado (OPS-01C).

---

## P2

| # | Pendência | Evidência | Impacto | Ação |
|---|---|---|---|---|
| P2-1 | Consentimento LGPD em memória → pede de novo a cada abertura | `App.tsx` | Atrito na LGPD | storage persistente |
| P2-2 | Sem push notification (sem FCM/Notifee) | `mobile/package.json` | Entregador só vê com app aberto | backlog |
| P2-3 | `/driver/deliveries` não envia `phone` | `delivery_persistence_model.py` `to_dict()` | Botão “Ligar” sem número | incluir `phone` no DTO |
| P2-4 | App envia `proof_type: "NONE"` fora do enum | `wired.tsx` × `ProofType` | Prova registrada fora do padrão | usar `MANUAL_CONFIRMATION` |
| P2-5 | App envia `reason`; backend lê `failure_reason` | `wired.tsx` × `ActionRequest` | Motivo de falha cai em `OTHER` | alinhar campo |
| P2-6 | Múltiplos endereços não existem | `schemas/client.py` (endereço único) | Cliente com 2 endereços não representável | decisão de produto |
| P2-7 | Instalador do desktop sem assinatura (D3) | `docs/STATUS_E_PLANO.md` §1.2 | Aviso do Windows na instalação | certificado |
| P2-8 | Token JWT na query string do `/ws` | `driverWsUrl`, `websocket.py` | Token pode aparecer em log de proxy | header/subprotocolo no futuro |
| P2-9 | Redis 128 MB sem `maxmemory` no perfil doméstico | `docker-compose.homeserver.yml` | OOM-kill sob carga anômala (rate limit fail-open) | monitorar; ajustar política |
| P2-10 | Frontend/E2E não executados nesta sessão | `frontend/node_modules` ausente | Cobertura de UI não reexecutada hoje | rodar no nível B |

---

## DEPENDÊNCIA OPENCODE

Frente paralela responsável por backup, restore, SQLite→Postgres, migração
ensaiada, `scripts/home-server/data/` e `docs/data-migration/`. **Não alterei
nenhum desses arquivos nem executei esses fluxos.** Para o aceite (níveis B/C),
exigir do entregável:

1. `pg_dump` executável e documentado, com retenção e destino **fora** do disco
   do servidor (volume `backups_data` não é backup).
2. **Restore testado**: banco limpo → restore → smoke verde → contagens
   conferidas.
3. Migração SQLite→Postgres **idempotente** e com rollback (ou restore) escrito.
4. Scripts em `scripts/home-server/data/` versionados, sem segredo embutido e
   com `--dry-run`.
5. Relatório de contagem: clientes, pedidos, entregas, pagamentos antes × depois.
6. Evidência de que o SQLite de produção não é mutado durante o ensaio.

Enquanto isso não existir, `ROLLBACK_OPERACIONAL.md` é o único caminho seguro —
e o caminho é **não migrar**.

---

## Fora do escopo desta frente (defeitos encontrados, não corrigidos)

- Código do app mobile (C1–C5 em `STATUS_DE_ENTREGA.md` §3.1).
- CI sem job mobile (arquivo de workflow não é meu escopo nesta frente).
- `docker-compose*.yml`, `deploy/home-server/`, `.env*`, Nginx, Dockerfiles,
  monitoring: congelados pelo OPS-01B.
- `frontend/nginx.conf` e `DEPLOY.md`.
- Qualquer alteração em SQLite operacional, WhatsApp real, firewall ou rede.
