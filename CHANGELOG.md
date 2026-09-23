# Changelog

Todas as mudanças relevantes do GasFlow, agrupadas por release.

## [Unreleased]

### 📲 App do entregador — ações de entrega na auth principal

- **Aceitar/iniciar/concluir/falhar respondiam 401:** o app loga em
  `/auth/login` (JWT principal), mas as ações existiam só em
  `/api/v1/driver/*`, que aceita sessão de driver no banco ou JWT de escopo
  `mobile` — nenhum dos dois o app tem. As mesmas ações agora existem em
  `/driver/deliveries/{id}/{accept|start|arrive|complete|fail}`, atrás de
  `require_driver`, escopadas por `tenant_id` + `driver_id`, reaproveitando os
  handlers compartilhados (transição de estado, idempotência e realtime
  idênticos). `POST /driver/location` (singular) entrou na mesma leva — alias
  do ingest legado com a mesma janela LGPD e throttle de 10 s; o app migrou
  para o namespace novo e os testes de rastreio acompanham.

### 🌐 Painel web — o que faltava operar

- **Cancelar pagamento e despesa:** os endpoints `/payments/{id}/cancel` e
  `/finance/expenses/{id}/cancel` existiam sem tela. A `FinancePage` ganhou o
  botão (só em itens ativos), confirmação citando valor/origem, trava por item
  contra duplo clique e mensagens por status (404 recarrega a lista, 409
  explica que há regra de negócio, 403 diz que falta permissão).
- **Cancelar execução pendente de automação WhatsApp:**
  `/automation/whatsapp/executions/{id}/cancel` também não tinha tela — a aba
  Execuções listava envios pendentes sem deixar parar nenhum. Mesmo padrão de
  confirmação e erro; a regra continua ativa para os próximos clientes.
- **Revogar links de rastreio:** `POST /public/tracking/revoke/{driver_id}`
  (incrementa `tracking_epoch` → links antigos respondem **410**) ganhou botão
  na `DriversPage`, com confirmação que cita o nome do entregador.
- **Página de Integrações** (`settings/integrations`, guard
  `integration.read`) para a gestão de revendas.
- **Página de Automações** (`/automation`, `WorkflowsPage`) — o motor interno
  de workflows e aprovações, separado das regras de WhatsApp do menu próprio.

### 🔁 Diversos

- **`GET /mobile/version` com override:** o caminho do `mobile_version.json`
  passou a resolver a cada request (não no import) e respeita a env
  `MOBILE_VERSION_FILE` — funciona em runtime e nos testes.
- **Audit de integridade enxerga WebSocket:** o OpenAPI não expõe rotas `ws`,
  então o guard acusava endpoint inexistente para `ws://host/ws`, que o app
  abre. A coleta desce a árvore de routers incluídos e junta as rotas
  WebSocket às HTTP.

### 🧑‍🔧 CRUD de entregadores — editar, excluir e uma criação só

- **Editar não salvava:** a tela chamava `PUT /delivery-drivers/{codigo}`, que
  não existia (405). A rota agora existe, é admin-only, escopada por tenant
  (entregador de outro tenant → 404) e rejeita `codigo` no corpo com **422** —
  ele é a identidade gravada em entregas, posições e histórico. Grava todos os
  campos editáveis (`nome`, `telefone`, `placa`, `document`, `vehicle_id`,
  `status`). O `GET /{codigo}` passou a devolver o mesmo contrato, então a tela
  de edição não perde mais `document`/`vehicle_id`/`status` ao abrir.
- **Botão de excluir:** a `DriversPage` ganhou "Excluir" com confirmação que cita
  o **nome** do entregador. O endpoint já existia e não tinha tela — a exclusão
  de usuário tinha botão, a de entregador não.
- **Excluir é soft delete com um só efeito:** `ativo=false` (cadastro) +
  `status=DISABLED` (operacional) + `User` desativado + sessões revogadas +
  `tracking_epoch` incrementado (links públicos de rastreio já emitidos passam a
  responder **410**) + registro em `auth_audit_log`. Entrega em rota
  (`ASSIGNED`/`DISPATCHED`/`EN_ROUTE`) → **409** e o entregador continua ativo.
  `PATCH /delivery-drivers/{codigo}/disable` virou alias do mesmo use case —
  antes só derrubava `ativo`, ou seja, dois "excluir" com efeitos diferentes.
- **Criação consolidada em `POST /admin/drivers`:** é o caminho canônico, único
  que cria a entidade **e** a credencial de login. A `DriverFormPage` migrou para
  ele e agora mostra a senha temporária antes de sair da tela — antes ela criava
  entregador **sem login**, que não conseguia abrir o app. O helper morto
  `api.drivers` saiu do client do frontend.
- **`POST /delivery/drivers` virou alias do canônico:** antes criava só a
  entidade, então o entregador cadastrado por essa URL não tinha como logar. Os
  dois entrypoints agora passam pelo `CreateDriverWithCredentialUseCase` (camada
  de aplicação) — mesmo efeito, mesmo contrato de resposta
  (`driver_id`/`username`/`temporary_password`) e auditoria uma vez por criação.
  Não existe mais caminho público que crie entregador sem credencial.
- **Campo fantasma removido:** a tela enviava e lia `vehicle_type`, que não existe
  no request nem na resposta (o Pydantic descartava em silêncio e o formulário
  voltava para MOTORCYCLE). Virou "CNH / Documento", que é o `document` real.

### 📱 App do entregador — debug × release

- **Release embute o bundle:** o APK de release carrega
  `assets/index.android.bundle` (conferido dentro do próprio APK); o de debug
  baixa do Metro em `localhost:8081` e só abre com Metro acessível — por isso não
  vai para o celular do entregador.
- **Rótulos distintos:** o debug instala como “GasFlow Entregador (dev)” (overlay
  `android/app/src/debug/res/values/`), para não confundir os dois ícones na
  gaveta.
- **Docs e atalho:** `mobile/README.md` ganhou as seções “Desenvolvimento
  (debug × release)” e “Erros comuns” — o “Could not connect to development
  server” é instalação de debug por engano — e o script `npm run android:release`.
- **Cleartext no release:** o manifest principal passa a declarar
  `android:usesCleartextTraffic="true"`. O modo LAN é `http://{ip}:{port}` e o
  `targetSdk 34` bloqueia cleartext desde o Android 9 — o flag só existia no
  manifest de debug, então só o debug logava na rede do depósito.

### 🔧 Correções do rastreio (Parte 1)

Seis correções em bugs reais de produção, sem mudar a API:

- **Cooldown de alertas (Fix 1):** `TrackingAlertsService` agora mantém cooldown
  de 15 min por `(tenant, driver, kind)` — evita que o alerta pisque o dia
  inteiro. Estado persistido em `tracking_alert_state` (sobrevive a restart).
- **Reset por movimento (Fix 2):** cooldown reseta quando o entregador volta a
  andar (> 200 m).
- **Gate do DEVIATED (Fix 2):** `DEVIATED` só aciona com `status == "EN_ROUTE"`
  **e** a menos de 3 km do destino — evita falso positivo na volta ao depósito.
- **TTL máximo do link público (Fix 3):** `MAX_TTL_S = 86400` (24 h); request
  acima disso → **422**. Token embute `e` (epoch do driver).
- **Revogação por epoch (Fix 4):** `POST /public/tracking/revoke/{driver_id}`
  incrementa `tracking_epoch` → link antigo retorna **410 Gone**.
- **Origem da linha de ETA (Fix 5):** `DriverMap` usa a **última** posição como
  origem da polyline tracejada (antes saía de um ponto de 30 min atrás).
- **Rótulo honesto (Fix 5):** quando `speed_source == "default"`, o rótulo ganha
  `~` (ex.: `~12 min`) para não vender precisão que não existe.
- **Migration `f3a9c1e7d204`:** adiciona `delivery_drivers.tracking_epoch` e
  cria tabela `tracking_alert_state`.

### 🚀 Entrega inteligente (Fases 8–10, Opção D)

Sistema completo de roteamento e despacho inteligente, tudo open source e gratuito.

#### Fase 8 — Sequenciamento de rota (OR-Tools)
- **`RoutingProvider` (ABC):** contrato de roteamento por matriz NxN em
  `app/domain/routing/provider.py`. Duas implementações:
  `HaversineRoutingProvider` (default, zero infra) e `OsrmRoutingProvider`
  (opt-in, malha viária real).
- **`DeliveryRouteOptimizer`:** resolve TSP/caminho aberto com OR-Tools
  (Apache-2.0). Ganho < 5% mantém a ordem original. Sem OR-Tools instalado,
  fallback transparente (`provider="fallback"`).
- **`POST /delivery/route/optimize`:** endpoint escopado por tenant. 409 quando a
  flag `DELIVERY_SMART_ROUTING_ENABLED` está desligada.
- **Gatilho automático:** função na camada de aplicação chamada best-effort
  após `PATCH /deliveries/{id}/assign`. Publica `route.optimized` no barramento.
- **App do entregador:** ao receber `route.optimized`, reordena ids conhecidos e
  dispara refetch para completar (decisão 13).

#### Fase 9 — Melhor entregador (DispatchScorer)
- **`DispatchScorer`:** módulo testável que pontua entregadores por proximidade
  (posição do histórico), carga, prazo e fairness. Pesos configuráveis por env.
- **Integração:** com a flag `DELIVERY_SMART_DISPATCH_ENABLED` ligada,
  `/delivery/dispatch/suggest` delega ao scorer mantendo o gate de elegibilidade.
- **`GET /delivery/dispatch/candidates/{delivery_id}`:** preview read-only do
  score para o operador. 409 quando a flag está desligada.
- **`dispatch.scored`:** evento publicado para auditoria quando o scorer decide.

#### Fase 10 — OSRM self-hosted
- **`OsrmRoutingProvider`:** chama OSRM via HTTP (`/table` para matrizes,
  `/route` para geometria). Timeout curto (2 s) + circuit breaker.
- **Fallback transparente:** OSRM offline/timeout → haversine. `provider`
  no payload denuncia a fonte.
- **`docker-compose.osrm.yml`:** arquivo opt-in para documentação do deploy.
- **`docs/routing/osrm.md`:** pipeline completo (extract → partition → customize
  → routed), requisitos de hardware, troubleshooting.

### 🧭 Rastreio: ETA, link público, alertas e replay (Fase 7)

A camada de rastreio ganhou o que faltava para operar de verdade — tudo em cima
do histórico (Fase 3) e do barramento/Mapa já existentes. Nada de serviço pago,
API key ou tabela nova.

- **ETA (7.1):** `GET /delivery/deliveries/{id}/eta` devolve `eta_seconds`,
  `distance_km` e `speed_source` (`history` quando há amostra; `default` quando
  não há). A velocidade vem da média dos últimos 15 min do histórico; o ETA
  mínimo é 60 s. **422** quando o endereço não tem coordenadas (não inventamos
  geocoding) e **404** quando falta entregador ou posição. No painel, o mapa
  desenha a **linha tracejada** até o destino com o rótulo do ETA.
- **Link público (7.2):** `POST /public/tracking/link` (admin/operador) emite um
  token HMAC **stateless** (escopo `public_tracking`, tenant + driver + expiração,
  máx. 24 h). `GET /public/tracking/{token}` é lido **sem autenticação** e devolve
  só `driver_id`, coordenadas e horário — **sem PII**. Segredo dedicado ao escopo
  (`PUBLIC_TRACKING_SECRET`), nunca a chave do operador. No painel, a rota
  pública `/track/:token` mostra só o mapa, sem menu e sem login.
- **Alertas (7.3):** `TrackingAlertsService` marca **STALLED** (parado: < 60 m em
  10 min com entrega em rota) e **DEVIATED** (posição além de 1,2 km do endereço
  da entrega), e publica `driver.alert` no barramento existente. A avaliação roda
  **uma vez por lote** de ingestão, não por ponto. O painel mostra um banner com
  opção de dispensar.
- **Replay do dia (7.4):** o painel reproduz o trajeto a partir do próprio
  `GET /driver/locations/history` — sem backend novo.
- **`today_distance_km` visível (7.5):** agora aparece no popup do mapa do painel
  e num card no topo da tela de rota do app.

### 📱 App do entregador: sessão segura, fila de rastreio e APK assinado

O app do entregador (React Native bare em `mobile/`) passou a usar a auth
principal e ganhou empacotamento de release.

- **Sessão no keystore**: access/refresh em `react-native-keychain`
  (Keystore/Keychain), nunca em `AsyncStorage` puro; logout e `401` limpam.
- **Gate de senha pendente no app**: `403` + `X-GasFlow-Password-Change-Required:
  1` e WS fechando `4003` levam à tela de troca de senha como **estado de app**.
- **Fila offline de rastreio**: posições passam a ser deduplicadas por
  `recorded_at` (replay do background não empilha o mesmo ponto) e têm
  retenção local de **7 dias**.
- **Adaptador de GPS em segundo plano** (`src/logic/backgroundTracking.ts`):
  config pronta (`distanceFilter` ~20 m, precisão HIGH, foreground service,
  lote 50, retenção 7 dias), geofencing (~150 m, apenas SUGERE "marcar como
  chegou") e **fallback** para o rastreio de primeiro plano — com testes
  usando um fake da lib.
- **APK release assinado**: `build.gradle` lê `android/keystore.properties`
  (gitignored) e cai na chave de debug quando ela não existe. Keystore própria
  gerada (SHA-256 `47:10:07:…:0C`) e custódia documentada em `mobile/README.md`
  junto de build, ambientes, distribuição e teste manual E2E.

**Bloqueio reportado:** `@ikolvi/tracelet@0.1.0-alpha.1` **não compila** no
Android — o pacote publicado omite o submódulo `core`
(`Unresolved reference: core`), traz um `<service>` fora do `<application>` no
manifest (AAPT rejeita) e exige `minSdk 26`. A lib foi removida e o rastreio
segue em primeiro plano, atrás da costura do adaptador (passo a passo para
religar em `mobile/README.md`).

### 🗺️ Localização, mapa e rastreador (Fases 3, 4 e 6)

O rastreio só guardava a **última** posição (upsert em `driver_locations`) e o
painel a lia por **polling de 30s**. Sem histórico não havia distância, replay,
geofencing nem ETA; e o mapa só se movia a cada meio minuto.

**Histórico append-only (Fase 3)**

- Nova tabela **`driver_location_history`** (migration `e7b1c3d5f9a2`, reversível):
  `tenant_id`, `driver_id`, `latitude`, `longitude`, `accuracy_m`, `speed_kmh`,
  `heading_deg`, `recorded_at`, `received_at`, com índices compostos
  `(driver_id, recorded_at)` e `(tenant_id, recorded_at)`.
- `driver_locations` **continua** sendo a "última posição" — nada que já lia dela
  mudou. O histórico é o log imutável, base para distância/replay/geofencing.
- Repositório: `bulk_insert_history` (lote até 500), `get_history` (paginado),
  `distance_km_between` (haversine entre pontos consecutivos) e
  `purge_history_older_than` (retenção LGPD de 90 dias). Escopo **sempre** por
  `tenant_id` + `driver_id`.
- **`today_distance_km`** deixou de ser um campo morto (= 0): agora é calculado
  do histórico do dia no fuso `America/Sao_Paulo`, exposto em `GET /driver/me` e
  na listagem de posições do operador.
- `driver_id` guarda `delivery_drivers.codigo` (String), a mesma identidade de
  `driver_locations` e do canal WS `driver:{id}` — não o `id` serial.

**Ingestão + realtime (Fase 4)**

- **`POST /driver/locations`** (auth `require_driver`): lote de até 500 pontos,
  grava o histórico, atualiza a última posição e **publica no barramento
  existente** (evento `driver.location_updated`) — que já roteia para
  `tenant:{id}` / `driver:{id}` / `operations:{id}`. Nenhum `/ws/tracking` novo.
- **`GET /driver/locations/history`** (admin/operador), escopado por tenant.
- Work-hours (LGPD) valem para a ingestão em lote, com audit em caso de recusa.

**Painel web (Fase 6)**

- **Polling de 30s removido**: `useDriverLocations` passou a ser só a carga
  inicial/fallback e **`useTrackingSocket`** assina `tenant:{id}` pelo mesmo
  `/ws` (mesma reconexão com backoff), acumulando o trajeto por entregador.
- `DriverMap` ganhou **polyline do trajeto** (`trails`), atualizada de forma
  incremental; a posição do WS sobrepõe a do fetch inicial (mais recente vence).
- O painel já usava **Leaflet + tiles OpenStreetMap** (BSD-2, sem API key).
  Mantido em vez de trocar por MapLibre: mesma restrição (open source, sem
  serviço pago) sem descartar um componente já testado nem introduzir um mapa
  paralelo.
- Lib pura e testável `lib/tracking.ts` (`parseDriverLocationEvent`,
  `mergeTrackingState`): dedupe por `recorded_at`, ordenação, janela de tempo e
  teto de pontos.


### 🚚 Cadastro de entregador com credencial própria

Antes o entregador era só uma entidade de negócio (`delivery_drivers`) com um
subsistema de login paralelo (`driver_sessions` + JWT mobile). Agora ele ganha
credencial na auth principal — sem um segundo sistema de identidade.

- **`POST /admin/drivers`** cria a entidade de negócio **e** a credencial
  (`User(role=DRIVER, driver_id=..., must_change_password=True)`) na mesma
  transação e devolve `{driver_id, username, temporary_password}` — a senha
  aparece **uma única vez** (nunca em log, audit ou listagem).
- **`POST /admin/drivers/{id}/reset-password`**, **`DELETE /admin/drivers/{id}`**
  (desativa driver + usuário e **revoga as sessões**) e **`GET /admin/drivers`**.
- **Login pela auth principal**: o entregador autentica em `POST /auth/login` e
  herda, de graça, o gate de `must_change_password` no HTTP e no WebSocket.
  Novo `require_driver` (403 para quem não é `DRIVER`) e namespace **`/driver/*`**
  escopado por `tenant_id` + `driver_id` (ex.: `GET /driver/deliveries`).
- O `driver_id` guarda `delivery_drivers.codigo` — a identidade usada em todo o
  grafo (`delivery_records.driver_id`, `driver_stock`, canal WS `driver:{id}`),
  não o `id` serial. A invariante é validada no serviço; o banco garante apenas
  que `driver_id`, quando presente, não é vazio (o role vive em `auth_roles`,
  fora do alcance de um `CHECK`).
- Migration `c2d8e4f6a1b3`: `auth_users.driver_id` (+ índice e check) e
  `delivery_drivers.document`/`updated_at`.
- O login antigo do app (`driver_api.py`) fica marcado `# LEGACY` — não
  estenda; ele existe só para não quebrar clientes antigos.

### 🔐 Sessão do operador em JWT (B5)

O console usava só uma sessão opaca no banco: sem token de curta duração, sem
renovação e sem escopo por plataforma — qualquer sessão desktop+mobile dependia
de manter o mesmo token vivo para sempre.

- **Access JWT (HS256, 15 min) + refresh opaco rotativo (7 dias)**, com o mesmo
  desenho já aprovado no app do entregador. O JWT carrega o `sid` da sessão, e
  a validação continua lendo a linha da sessão: **revogar sessão corta o acesso
  na hora**, sem esperar o token expirar.
- **Segredo dedicado** (`OPERATOR_JWT_SECRET` → settings → arquivo gerado 1x),
  separado do segredo do entregador: um token de um escopo nunca vale no outro.
- **Rotação com detecção de reuso**: refresh já trocado que reaparece revoga a
  sessão inteira (é o sinal de token vazado).
- **`POST /auth/refresh`** novo; `/auth/login` passa a devolver
  `access_token` + `refresh_token` (o campo `token` continua, para não quebrar
  cliente antigo) e aceita `platform`.
- **Frontend renova sozinho** quando o access expira, com *single-flight*: sem
  isso, requests paralelas trocariam o mesmo refresh e o backend leria reuso —
  ou seja, o app deslogaria o próprio usuário.
- **Bug corrigido no caminho**: `POST /auth/logout` chamava `revoke()` num
  modelo ORM que não tem esse método — em modo DB o endpoint respondia 500 e a
  sessão continuava viva. Agora revoga pelo repositório, a partir do token do
  header.

### 🎬 Entrada do app e tela de login

- **Login com entrada em cascata**: marca → título → campos, com o brilho de
  fundo derivando devagar. Usa os componentes de marca e os tokens de movimento
  do design system (acompanha o tema do cliente, respeita
  `prefers-reduced-motion`) — antes eram um `<h1>GasFlow</h1>` fixo e um cartão
  sem identidade.
- O splash estático do boot dissolve no mesmo instante em que o login monta, então
  a abertura do app termina numa transição em vez de num corte.

### 🚀 Abertura do app e experiência de atualização

O auto-update existia só como um retângulo no canto: baixava em silêncio,
sem progresso e sem explicar que aplicar exigia reiniciar. E o app abria em
tela em branco até o bundle carregar.

- **Splash de entrada** (`index.html` + `src/lib/boot/splash.ts`): o splash
  com a marca pinta no primeiro frame — antes do bundle, que é o momento da
  tela branca — e o React o dissolve quando monta. Rede de segurança remove o
  splash se o bundle não carregar, para não parecer travamento.
- **Tela de atualização** (`components/UpdateScreen.tsx`): banner com
  progresso real que **não** bloqueia o trabalho nos estados
  "disponível/baixando"; overlay com anel pulsante, versão e "Reiniciar e
  instalar agora" quando a versão está pronta. "Depois" e `Esc` rebaixam o
  overlay para o banner — o aviso nunca some, e nada é aplicado sem o usuário
  saber.
- **Repartição de estados** para não duplicar aviso: `UpdateScreen` cuida de
  progresso e decisão; `UpdateNotifier` (canto) só de "verificando/erro".
- **"Tentar novamente"** no erro de verificação: a ponte `update:check` era
  exposta pelo preload sem nenhum consumidor — quem via "falha ao verificar"
  não tinha saída nenhuma.
- Os dois montados na **raiz do `App`**, valendo em qualquer rota (antes o
  aviso de update só existia dentro do layout logado).
- **Tokens de movimento** no design system (keyframes + utilitários
  `gf-anim-*`), todos neutralizados por `prefers-reduced-motion`.
- **Release**: a verificação pós-publicação agora exige release **publicado**
  (não rascunho) e publica a URL no resumo do run. Rascunho é pior que
  release ausente: o `gh` autenticado o enxerga, mas o updater e o cliente
  não.

### 🔒 Troca de senha pendente agora bloqueia no backend

O `must_change_password` só existia como aviso: o login devolvia a flag e o
frontend mostrava o gate, mas nenhuma rota do backend era de fato recusada —
um cliente que ignorasse a flag (script, token reaproveitado) seguia operando
normalmente.

- **O middleware passou a recusar** qualquer rota fora de `/auth` enquanto a
  troca está pendente, com `403` e o header
  `X-GasFlow-Password-Change-Required: 1`. A allowlist mantém acessíveis
  apenas `/auth/me`, `/auth/change-password` e `/auth/logout`. O canal de
  **WebSocket de realtime** segue a mesma regra — a conexão fecha com
  `4003 / "Password change required"`.
- A allowlist é comparada **sem o prefixo de montagem**, porque os mesmos
  routers são servidos em `/auth/...` e em `/api/auth/...`.
- **Cobertura nova**: um teste garante o 403 (com o marcador) numa rota
  protegida e que a troca correta libera o acesso sem novo login. Os helpers
  de teste que criavam operador passaram a trocar a senha antes, para que os
  testes de permissão continuem provando **permissão**, e não o bloqueio.
- **No frontend**, um `403` de senha pendente em pleno uso emite um evento que
  o `AuthProvider` ouve e levanta o gate — antes esse caso viraria um erro
  mudo, sem tela para resolver.
- **Auditoria das migrations no SQLite** documentada em
  `docs/migrations/2026-09-sqlite-batch-audit.md` — nenhuma operação do
  caminho de upgrade ficou fora de batch sem suporte nativo.

### 🧪 Testes e limpeza de dívida

- **Reversão de entrega coberta.** O caminho de volta da decisão B3(a) v3
  (`reverse_delivery_stock_atomic`) não era exercitado por teste nenhum — o
  `min()` do clamp de vazios podia sumir sem fazer assert algum falhar. Agora
  são cinco casos: round-trip da entrega + reversão, idempotência por
  referência, clamp com a base sem vazios para receber, entrega sem estoque e
  não-vazamento entre produtos. O clamp é conferido por mutação
  (`backend/tests/test_delivery_stock_reversal.py`).
- **Schema fantasma `security_*` removido (dívida D5).** O segundo modelo de
  RBAC — que nenhum módulo da aplicação importava e que nenhum banco real
  continha — saiu junto de seus testes. O canônico segue `auth_model.py` +
  `rbac_model.py`, eliminando a armadilha de editar o arquivo errado.

## [1.1.7] - 2026-09-21

### 🛡️ Integridade do app — auditoria, correções e release

Antes de publicar, o app inteiro passou por uma varredura que cruza o que
cada camada expõe com quem consome: tela ↔ endpoint, botão ↔ handler, canal
IPC ↔ ponte, evento ↔ emissor, rota ↔ consumidor, tabela ↔ superfície,
módulo ↔ rota. O guard mora dentro da suíte (`backend/tests/`) e roda no CI
em PR e push — deixa de ser varredura de um dia e passa a ser regra do
repositório.

- **Guard de integridade** (`tests/integrity_audit.py` +
  `test_app_integrity.py`): 11 checagens entre frontend, backend, desktop
  (Electron), serviço WhatsApp, app do entregador (React Native) e banco.
  Os findings conhecidos ficam em `tests/integrity_allowlist.json`, versionado
  e com o motivo escrito ao lado — o teste **falha** tanto se aparecer algo
  fora da lista quanto se um item da lista deixar de existir (allowlist
  apodrecida também é quebra). Relatório gerado em
  `docs/auditoria/integridade/` (`python -m tests.integrity_audit --report`).
- **Dois bugs reais encontrados e corrigidos** — os dois eram 404 silencioso
  numa tela viva, do tipo que não aparece em log nenhum:
  - `ContactsCrmPage` chamava `/clients/contacts*`, mas quem serve contatos é
    o módulo unificado do WhatsApp (`/whatsapp/contacts*`): listar, importar
    VCF, exportar VCF e reativar contato falhavam.
  - O app do entregador chamava `/driver/deliveries/:id/:action`, formato que
    o backend não expõe (ele serve `/api/v1/driver/deliveries/:id/:verbo`) —
    o caminho agora é explícito por ação, sem segmento adivinhado.
- **Superfície morta removida**: 44 métodos do preload sem consumidor, 5
  handlers IPC órfãos no main e o renderer legado `desktop/dist/renderer/`,
  que era **empacotado no instalador e nunca carregado** (o Electron abre o
  frontend com `loadURL(backendUrl())`). A ponte IPC viva ficou com 19
  métodos, todos com uso comprovado no renderer que roda de fato.
- **Dívida declarada em vez de apagada**: as 10 rotas do serviço WhatsApp sem
  consumidor no repo (`/lists/*/contacts`, `/customers/sync`,
  `/campaigns/*/preview` …) continuam existindo — são API de produto do
  serviço, que o proxy do backend simplesmente não expõe; removê-las seria
  decisão de produto, não de auditoria. Ficam na allowlist com o motivo.
- **`tzdata` declarado** (`requirements.txt` + spec do PyInstaller): o exe só
  carregava a base de fusos porque a máquina de build tinha o pacote por
  acaso, e a falta dele derrubava as 15 falhas locais da suíte no Windows
  (`ZoneInfo("America/Sao_Paulo")` sem fallback disponível).

### 📦 Dependabot — as 22 atualizações fechadas por área

Consolidadas em 4 commits (uma área por commit) em vez de mergear as 22
branches soltas, que conflitavam entre si — três delas mexiam no mesmo bloco
de dependências do `react`.

- **GitHub Actions + pip**: checkout/setup-node/setup-python para v7,
  setup-qemu-action v4, PyInstaller 6.22.3, python-multipart 0.0.32 e
  ruff 0.16.8 nos dois requirements.
- **Frontend**: React 19.3, Vite 8.3, Vitest 5, ESLint 10, lucide-react 1.47,
  react-hook-form, react-router-dom e `@types/react*`. Dois ajustes foram
  necessários, ambos por mudança de contrato das próprias ferramentas:
  o ESLint 10 deixou de trazer `@eslint/js` de forma transitiva (virou
  dependência explícita) e a nova config recomendada liga
  `preserve-caught-error`, que exige `cause` no erro relançado — o
  `AuthProvider` preserva o erro original ao traduzir a mensagem de login.
  Já o Vitest 5 mudou `Assertion` para **dois** parâmetros de tipo, o que faz
  a augmentation do `@testing-library/jest-dom` 7.x (que declara um) não
  mesclar mais e some com os matchers do `expect`: daí o shim
  `src/test/jest-dom-vitest.d.ts`, que redeclara a augmentation com a
  assinatura nova. Remover quando o jest-dom publicar suporte ao Vitest 5.
- **Serviço WhatsApp + E2E**: `@hapi/boom` 10, dotenv 17, `@types/node` 26.6,
  ESLint 10 e Playwright 1.63. O ESLint 10 **removeu** o formato `.eslintrc`:
  o arquivo legado virou `eslint.config.js` (flat), na mesma convenção do
  frontend, e as duas dependências avulsas do typescript-eslint deram lugar
  ao pacote meta.
- **Um bump ficou de fora, e o motivo não é preferência**: TypeScript 7 no
  serviço WhatsApp. O `typescript-eslint` 8.70.0 — último publicado — declara
  peer `>=4.8.4 <6.1.0`, ou seja, **nenhuma versão lançada do lint entende o
  TS 7**. Subir trocaria um typecheck funcionando por um lint que não roda;
  fica como bloqueio upstream até o lint acompanhar.
- **Dívida herdada (não introduzida aqui)**: 5 alertas HIGH do `extract-zip`
  chegando por `whatsapp-web.js` → puppeteer. A 2.0.1 é a última versão
  publicada e é exatamente a que o `overrides` do projeto já fixa — não há
  correção upstream para aplicar hoje.

#### Suítes locais na v1.1.7

| Suíte | Resultado |
|---|---|
| Backend (ruff · mypy · pytest) | **1662 passed**, 27 skipped, 0 failed |
| Guard de integridade | 20 findings, **0 pendentes** |
| Frontend (build · lint · vitest) | 299 testes |
| WhatsApp (typecheck · build · lint · test) | 94 testes |
| Agent (typecheck · build · test) | 27 testes |
| Desktop (typecheck · test) | 71 testes |
| Mobile (typecheck · test) | 33 testes |
| E2E (Playwright 1.63) | config válida, 11 specs coletados (run completo no CI) |

### 🔧 CI/E2E — o stack voltou a subir (e o Postgres a migrar)

O workflow **E2E estava vermelho desde pelo menos 15/09** e o **Trivy nunca
havia rodado** (ele depende do job do backend, que falhava antes). As duas
causas eram reais e silenciosas:

- **Query só de SQLite quebrava o PostgreSQL** — `INSERT OR IGNORE`
  (`rbac_seed.py`, usado pela migration RBAC, e `admin.py`) é sintaxe
  exclusiva do SQLite. No Postgres dá `syntax error at or near "OR"`, o
  `alembic upgrade head` morre, o container do backend entra em loop de
  restart (`restart: unless-stopped`) e o `docker compose up -d` aborta com
  *"container gasflow-e2e-backend is unhealthy"* — o Playwright nunca
  chegava a rodar. Agora é `ON CONFLICT (code) DO NOTHING` / `ON CONFLICT DO
  NOTHING`, portável para os dois bancos (SQLite ≥ 3.24, PostgreSQL ≥ 9.5).
  Ninguém tinha visto porque a suíte inteira roda em SQLite.
- **Janela de saúde apertada demais** — o healthcheck do backend não tinha
  `start_period`: a cadeia de migrations roda **antes** do uvicorn e, em
  banco zerado frio, passa de 100s (`retries` × `interval`), marcando
  unhealthy durante o boot legítimo. `start_period: 180s` no E2E e `120s` no
  prod (era 20s).
- **Contexto de build de 266MB → 54kB** (`backend/.dockerignore`):
  `.venv-ci/`, `.mypy_cache/`, `*.db.backups`, os diretórios `$(mktemp -u)*`
  e logs entravam na imagem (o `transferring context` levava ~7min). O mesmo
  ajuste no frontend (`*.tsbuildinfo`, `*.log`).
- **Trivy verde nas 4 imagens** — a base Debian/Alpine era um snapshot
  atrasado e reprovava com 14 HIGH/CRITICAL **sem CVE nenhum no código**
  (perl-base, gzip, libsqlite3, libpcre2, libssh2…). Os Dockerfiles agora
  fazem `apt-get upgrade` / `apk upgrade` no build, o que torna o scan
  determinístico. Sobrou o que não tinha correção upstream: o pip vendoriza
  `msgpack==1.1.2` (GHSA-6v7p-g79w-8964) e `setuptools==70.3.0`
  (CVE-2025-47273) em `pip/_vendor/vendor.txt` — o runtime não usa pip
  (entrypoints são `alembic`/`uvicorn`), então o pip e o `ensurepip` saem da
  imagem final. Resultado: **as 4 imagens com 0 findings**.
- **Agente sem `.dockerignore`** — o `COPY . .` do `agent/Dockerfile` levava
  o `node_modules` da máquina (binários de Windows e versões antigas de
  `tar`/`brace-expansion`/`ip-address`) para dentro da imagem, **sobrepondo**
  o que o `npm ci` tinha acabado de instalar. Além do CVE, isso tornava o
  build dependente da máquina de quem buildava.
- **Agent em `node:26-slim`** (era `24`): o `node:24-slim` traz **npm
  11.19.0** e as dependências vendorizadas do próprio npm aparecem no Trivy
  sem correção possível pelo projeto (`tar 7.5.19`, `brace-expansion 5.0.7`,
  `ip-address 10.2.0`). O `node:26-slim` traz npm 11.19.1 com as três
  corrigidas — mesma base que o serviço whatsapp já usava.
- **Specs E2E atualizados para a UI atual** (nunca tinham rodado por causa do
  boot): o módulo WhatsApp virou rotas aninhadas (`/whatsapp` é Conversas;
  "Serviço Indisponível" vive em `/whatsapp/accounts`) e a navegação passou
  de links planos para grupos colapsáveis — "Pedidos & Entregas" substituiu
  o link "Pedidos". Suíte: 10 passam, 1 pulado (requer sessão pareada).
- **Fail-fast legível**: quando o stack não sobe, o CI agora imprime
  `docker compose ps` + `logs --tail=200` (antes só saía "dependency failed
  to start", sem causa).
- **Novo job `Migrations (PostgreSQL, banco zerado)`**: roda `alembic upgrade
  head` num Postgres de serviço em segundos. O E2E cobre o caso, mas só
  quando o stack sobe — este é o guard barato que teria pego o
  `INSERT OR IGNORE` na primeira execução.

### 🌐 F10 — Cadastro público por convite (site) + orquestrador de serviços

Mudança de canal pedida pelo dono: o cliente indicado **não se cadastra
pela conversa** — recebe o link e se cadastra numa **página pública**
ligada à API central. É o fallback **(b) do §5** do spec de Entregas &
Cupons, agora o caminho principal; o canal IA (a) continua e os dois usam
o mesmo `ReferralService`.

- **F10.1 — Endpoint público** (`app/presentation/api/public_signup.py`,
  `POST /public/referral/signup`, sem auth): rate limit duplo — 3/hora por
  telefone e 5/hora por **IP** — via `WhatsAppLimitStore` (Redis quando
  `RATE_LIMIT_MODE=redis`). Como a requisição vem do navegador e não do
  webhook, o limite por IP enfim funciona de verdade (resolve o R1 da
  F4.5). Consentimento LGPD obrigatório validado no backend; a resposta
  traz só o cupom do próprio indicado (nunca lista dados de terceiros).
  Montado também em `/api/v1` (e em `/api` no modo FRONTEND_DIST).
- **F10.2 — Página pública** (rota `/cadastro` no frontend, fora do login):
  formulário + tela de sucesso com o cupom e mensagens específicas para
  convite já usado (409), inválido (404) e excesso de tentativas (429).
  `POST /coupons/generate-invite-token` passa a devolver `signup_url`
  quando a setting `referral.signup_base_url` está configurada (sem ela, o
  link `wa.me` legado continua).
- **F10.3 — Orquestrador** (`desktop/src/main/orchestrator.ts`):
  desired-state loop com health check periódico (15s), restart com
  **backoff exponencial** (2s → teto de 60s) e pausa após 5 falhas
  seguidas — substitui o antigo `startWithRetry` (3 tentativas no boot e
  desistia). Backend, serviço WhatsApp e agente ficam supervisionados;
  estado de saúde persistido em `userData/health-state.json` e IPC
  `orchestrator:status` / `orchestrator:resume`.
- **F10.4 — Deploy** (`frontend/vercel.json` +
  `docs/cadastro-publico-vercel.md`): SPA na Vercel com rewrites de rota e
  `VITE_API_URL` apontando para a API exposta por túnel.
  **Correção de CORS**: `PUBLIC_SIGNUP_ORIGINS` era lida mas nunca entrava
  no middleware — a origem da página pública agora é somada a
  `CORS_ORIGINS` (`main.py`). **Bugfix de build**: a página importava
  `ui/button` / `ui/input` em minúsculas, o que quebra o `tsc -b` (e o
  build no Linux da Vercel) — passava apenas no Windows.
- **F10.5 — Reenvio automático do cadastro**: se a API não responde (rede
  fora, túnel caído, 5xx ou excesso de requisições), o formulário é gravado
  no aparelho do cliente e reenviado sozinho — backoff 3s → 60s, ao voltar a
  internet e ao reabrir o link (`features/public-signup/pendingSignup.ts`).
  Para isso o backend ficou **idempotente por (token + telefone)**: reenvio do
  mesmo telefone devolve o cupom original (`status: "replayed"`, mesmo
  `coupon_code`, sem cliente/cupom duplicado) em vez de 409 — outro telefone
  continua 409 (single-use preservado).
- **F10.6 — Consulta do convite antes do formulário**: novo
  `GET /public/referral/invite/{token}` responde 200 com
  `{valid, reason, coupon_value, …}` (consulta, não ação — "já usado" é
  resposta esperada), sem PII de quem indicou e com limite de 60 consultas
  por IP/hora. A página avisa **antes** de pedir qualquer dado e, para quem já
  se cadastrou e não anotou o cupom, oferece o atalho "já preenchi meus dados"
  — o envio cai no replay idempotente e devolve o cupom original. Com cadastro
  pendente na fila local a consulta é **pulada**: o token pode ter sido
  consumido pelo próprio reenvio, e "já usado" esconderia a recuperação.
- **Flake de horário no CI**: `test_driver_location_relay.py` (3 testes) só
  passava dentro da janela de trabalho LGPD — default **06:00–22:00 UTC** — e
  depois das 22h UTC o handler respondia 403, deixando a suíte vermelha sem
  nenhuma mudança de código. O arquivo agora abre a janela (`00:00`–`24:00`),
  como `test_driver_mobile.py` já fazia.
- **F10.7 — Impressão de verdade** (`print_jobs` + agente no desktop): a fila
  saiu de um `dict` de processo para uma tabela (`PrintQueueService`) e o cupom
  passou a ser montado do **pedido real** (`receipt_data.py`) — antes ia
  `client_name="Cliente"`, `items=[]`, `total=0`, ou seja, papel em branco útil.
  O agente é o app desktop (tem o USB): poll em `GET /printer/agent/next`,
  bytes ESC/POS direto no spooler do Windows em modo RAW (PowerShell/P-Invoke,
  sem dependência nativa de npm), resultado em `POST .../result` e estado em
  `POST .../status`. Endpoints do agente exigem a chave de serviço
  (fail-closed, sem fallback para JWT). Tela em Configurações › Impressora
  (fila, reenvio, teste de impressão) e botão Imprimir na tela de Pedidos.
- **F10.8 — Relatório por período** (`GET /finance/reports/period`): totais,
  série diária e comparação com o período anterior de mesma duração, cache de
  5 min por (tenant, período), sempre filtrado por tenant.
- **F10.9 — Relatórios na tela**: filtro Hoje/7/30/90, gráfico
  barras+linha, detalhe dia a dia com rodapé de total, saldo em caixa,
  comparação em cada card, **exportar CSV** (separador `;`, vírgula decimal e
  BOM — Excel pt-BR abre certo) e **imprimir/PDF** preservando a view renderizada
  (ponte do Electron quando existe, diálogo do sistema fora dele).
- Testes: backend +15 (`test_public_signup.py`: sucesso, token repetido 409,
  reenvio do mesmo telefone devolvendo o mesmo cupom, consulta do convite
  (ok/já usado/inexistente/malformado + limite por IP), validações 422,
  limites por telefone e por IP); frontend +24 (`InviteSignupPage` 16 +
  `pendingSignup` 8 — fila local, classificação de falha, backoff, reenvio e
  consulta prévia); desktop +5 (`orchestrator`: saúde, restart com backoff,
  pausa por excesso de falhas, resume, persistência).

### 🖨️ Impressão — revisão de ponta a ponta (idempotência e reconexão)

Revisão do caminho pedido pago → fila → agente → spooler. Nove furos
encontrados e fechados, três deles garantindo **um cupom por pedido** de fato:

- **Cupom vencido não fica em silêncio**: o poll do agente passou a devolver
  `expired_jobs` e o app desktop **notifica** ("N cupom(ns) de dia anterior não
  saíram — reimprima os que ainda precisar"), uma vez por aumento do total (o
  poll é a cada 3s). Sem isso o pedido ficava sem cupom sem nada aparecer como
  erro: não sai papel, logo não existe falha para a tela mostrar. Na tela, os
  vencidos ganharam card próprio nos números, badge de atenção e alerta com o
  caminho da reimpressão.
- **Cupom de ontem não é reimpresso** (decisão do dono): o que ficou na fila
  desde antes da meia-noite **local** (setting `timezone`, default
  `America/Sao_Paulo` — `created_at` é UTC) **não sai sozinho** ao reabrir o
  app; vira `EXPIRED`, visível na tela com o motivo e com **Reimprimir**. Antes,
  abrir o app de manhã despejava no spooler a fila inteira do dia anterior —
  cupom de pedido já entregue, papel e atenção do operador jogados fora. A regra
  é o dia local (e não uma janela de horas) para casar com o dia que o operador
  enxerga; "impressos hoje" na tela passou a contar pelo mesmo dia. Reimprimir
  cria job novo, com carimbo de agora, então passa pelo corte.

- **Cupom duplicado quando o relato do resultado se perde**: o backend devolvia
  o job à fila depois do timeout de claim e o agente imprimia de novo. Agora o
  desktop mantém um **ledger local** (`userData/printed-jobs.json`) do que já
  foi para o spooler: job de volta à fila é re-reportado como sucesso, sem
  soltar papel (`replayed` na UI; reimpressão real continua criando job novo).
- **Idempotência do auto-print virou garantia do banco**: era check-then-insert
  em Python com um lock de processo — inútil com `BACKEND_WORKERS=2` (default
  de prod). Novo **índice único parcial** `uq_print_jobs_auto_order`
  (`WHERE requested_by='auto_print'`), com `IntegrityError` tratado no
  `enqueue` devolvendo o job do vencedor. Parcial de propósito: impressão
  manual e reimpressão continuam livres.
- **Claim atômico**: `claim_next` fazia SELECT e depois UPDATE (dois agentes
  imprimiam o mesmo cupom). Agora quem leva a linha é o UPDATE condicional
  (`status='PENDING'`); o perdedor recebe `None`.
- **Status do agente deixou de ser memória de um worker**
  (`app/core/printer_status.py`, padrão Redis com fallback in-memory de
  `whatsapp_limits.py`): com 2 workers o POST caía em um e o GET era atendido
  por outro — a tela oscilava entre "Pronta" e "Não configurada".
- **Sem sinal não é "Pronta"**: `stale` no `/printer/status` (30s sem relato,
  TTL de 5 min no store) e a tela avisa "Sem sinal do app de impressão — N
  cupom(ns) na fila" em vez de prometer impressão.
- **Relato de status perdido não fica perdido**: o worker cacheava o estado
  *antes* do POST; uma falha única (backend reiniciando) fazia aquele estado
  nunca mais ser enviado. Agora só cacheia o que o backend confirmou.
- **Diagnóstico separado por causa**: 401 na chave de serviço virou "chave
  rejeitada" (antes aparecia para sempre como "backend fora"), 5xx aparece com
  o código, e o `only_auto` do auto-print passou a filtrar por
  `requested_by='auto_print'` — imprimir manualmente um pedido novo não suprime
  mais o cupom automático quando ele for pago.
- Docstring do `/printer/agent/next` corrigida (fila vazia é 200 com
  `job: null`, não 204 — o agente lê o corpo para distinguir de erro).
- Testes: backend +23 (`test_printer_api.py`: unicidade do auto-print, manual
  não bloqueada, INSERT duplicado recusado pelo banco, corrida de claim com dois
  agentes, teto de tentativas, vencimento do dia anterior (não imprimível, o de
  hoje imprimível, só PENDING vence), reimpressão do vencido e o poll que
  denuncia o vencimento; `stale`; `test_printer_status.py` novo com 11:
  staleness, TTL, compartilhamento entre workers via Redis e fallback; índice do
  auto-print conferido na migration); desktop +7 (ledger contra duplicata, ledger
  sobrevivendo a restart, relato perdido reenviado, 401 e 5xx com diagnóstico
  próprio, aviso de vencido uma única vez por aumento); frontend +4 (aviso de app
  sem sinal em Pedidos e em Configurações › Impressora, vencido com reimpressão
  em um clique e card de vencidos).

### 🔧 CI verde no backend (F9.1) — mypy + bugfix do convite de comunidade

Fecha a parte do item "CI quebrado" da tabela de riscos do spec
(critério: corrigir antes da release que fecha as fases).

- **mypy `app` verde (0 erros em 288 arquivos; eram 37)**, sem engordar o
  baseline: modelos F7/F4 (`driver_stock_model.py`, `coupon_model.py`)
  modernizados para SQLAlchemy 2.0 tipado (`Mapped[...]`) — mesmos schemas,
  atributos instanciados deixam de tipar como `Column[X]`.
- **Bugfix real (F5)**: `community/service.py` chamava
  `bridge.send_text()`, método que nunca existiu — a exceção era engolida e
  o convite do Community **nunca partia**. Agora usa `send_message()`
  (async): `asyncio.run` no caminho comum (endpoints `def` em threadpool)
  ou task fire-and-forget com callback de erro dentro de loop rodando.
- Correções pontuais: narrowing de `created_at` em `orders.py`;
  conversão explícita `RelayLocationPayload` → `LocationUpdate` em
  `driver_relay.py` (handler compartilhado app/relay).
- Testes: +1 `test_community_invite.py` (convite chama `send_message` com
  telefone normalizado e link na mensagem; mocks migrados p/ `AsyncMock`).
  Suíte: backend 1595 ✅.
- Pendente (não bloqueia o job de testes): E2E (boot do stack docker no
  CI) e Trivy (CVEs CRITICAL/HIGH nas imagens) — reprodução local exige
  Docker daemon; rastreados à parte.

### 📊 F9 — Relatórios com Gráficos + Export PDF

Implementação da F9 do `docs/entregas-cupons-spec.md` (§3.9, decisões
F1–F3) — fecha todas as fases do spec de Entregas & Cupons.

- **Recharts 3.10.1 instalado** (decisão F1: biblioteca de gráficos
  padrão React, tree-shakeable).
- **Agregados backend** (`application/reports/delivery_metrics.py` +
  `GET /reports/deliveries?days=7|30|90`): série diária (criadas/
  entregues/falhas), por entregador (atribuídas/entregues/falhas +
  tempo médio atribuição→DELIVERED em minutos via `func.julianday`) e
  por bairro. Agregação SQL direta (mesmo padrão da F8), sempre por
  tenant; janela inválida → 400.
- **Gráficos** (`DeliveryCharts` na ReportsPage): linha de entregas por
  dia, barras comparativas por entregador, barras de tempo médio por
  entregador e barras por bairro — estados de vazio por gráfico, filtro
  de período e **refresh manual** (F2: sem auto-refresh no MVP).
- **Export PDF**: IPC `reports:export-pdf` (gate `finance.export_pdf` —
  permissão existente; `reports.read` não está no seed RBAC) faz
  `printToPDF` paisagem da view atual — os gráficos já renderizados — e
  abre o arquivo salvo no tmp (padrão das notas de compra). Fallback
  `window.print()` fora do Electron (dev/navegador).
- Testes: backend +10 (`test_delivery_report.py`: séries, tempo médio,
  ranking, tenant, endpoint) · frontend +7 (`DeliveryCharts.test.tsx`:
  render dos 4 gráficos, período, refresh, export via bridge + fallback,
  vazio/erro). Totais: backend 1581 · frontend 255.

### 🗺️ F8 — Mapa de Calor de Entregas por Bairro

Implementação da F8 do `docs/entregas-cupons-spec.md` (§3.8, decisões
E1–E3): densidade de entregas por bairro, só visualização.

- **Agregação SQL** (`application/reports/heatmap.py`): entregas
  DELIVERED por `address_neighborhood` (group by nativo, sem postgis),
  centroide aproximado por bairro (bounding box min/max de lat/lng) e
  contagem; sem bairro informado agrupa como "(sem bairro)".
- **Cache de 5 min** por (tenant, período) em memória com TTL — segunda
  chamada dentro da janela retorna `cached: true` sem reconsultar.
- **Endpoint** `GET /reports/heatmap?days=7|30|90` (default 30, E1);
  período inválido → 400; sempre filtrado por tenant.
- **UI**: `HeatmapPage` em `/reports/heatmap` (item "Mapa de Calor" no
  grupo Financeiro & Relatórios) — `DeliveryHeatmap` (Leaflet/OSM, mesma
  base do DriverMap, zero dependência nova) com círculos cujo raio e cor
  (verde→amarelo→vermelho) escalam pela contagem, popup por bairro,
  legenda, filtro 7/30/90 e ranking de bairros em barras. Bairros sem
  coordenadas ficam de fora do mapa mas seguem no ranking (avisado).
- Testes: backend +12 (`test_delivery_heatmap.py`: contagens vs SQL
  direto — critério do prompt, períodos, cache, tenant, endpoint) ·
  frontend +4 (`HeatmapPage.test.tsx`). Totais: backend 1571 ·
  frontend 248.

### 🚚 F7 — Entrega Inteligente + Estoque do Entregador

Implementação da F7 do `docs/entregas-cupons-spec.md` (§3.3 + §3.3.1,
decisões C1/C3): controle do estoque carregado pelo entregador e
sugestão inteligente com confirmação do operador.

- **`driver_stock` + `driver_stock_events`** (migration
  `c3f8a1d7e9b2`): saldos por entregador/produto —
  `full_tanks_loaded` (empréstimo, NÃO debita a base),
  `empty_tanks_returned`, bloqueio por divergência; eventos append-only
  (LOADING/DELIVERY/DAMAGE/RETURN/RECONCILE) com saldos pós-evento.
- **Carga (C1, manual)**: operador confirma N cheios; bloqueada quando o
  entregador tem divergência pendente. Débito da base continua sendo
  exclusivo do `deliver_stock_atomic` — conta dupla é bug (testado).
- **Espelho na entrega**: `DELIVERED` decrementa o entregador e credita
  os vazios (mesma transição que debita a base); `CANCELLED` pós
  `DELIVERED` reverte ambos; idempotente por evento (DELIVERY/RETURN
  com reference_id da entrega); best-effort — nunca derruba a transição.
- **Avaria**: motivo OBRIGATÓRIO; debita entregador + base
  (`deliver_stock_atomic` com reference `DRIVER_DAMAGE`), audit completo.
- **Reconciliação**: carga − entregas − avarias = cheios restantes +
  vazios devolvidos; divergência > tolerância (setting
  `driver.stock.tolerance`, default 2) → alerta + **bloqueio de novas
  cargas** até reconciliação aceita ou desbloqueio admin.
- **Sugestão no despacho (C3)**: `POST /delivery/dispatch/suggest` —
  elegibilidade = cheios disponíveis (não bloqueado) + disponibilidade;
  ranking = proximidade GPS + folga de capacidade (reaproveita
  `DispatchEngine`/haversine; nada duplicado). O OPERADOR confirma via
  assign existente.
- **UI**: `DriverStockCard` (carga/avaria/reconciliação + badge de
  bloqueio) na página de Motoristas; botão "Sugerir" no fluxo de
  atribuição de Entregas com explicação textual da recomendação.
- Testes: backend +15 (`test_driver_stock.py`: consistência
  base+entregador, idempotência, avaria, bloqueio, elegibilidade;
  migrations alignment ✅) · frontend +5 (`DriverStockCard.test.tsx`).
  Totais: backend 1559 · frontend 244. Critério de campo (>90% em 50
  pedidos reais) fica pós-implantação, conforme o spec.

### 📇 F6 — Organizador + Renomeador de Contatos

Implementação da F6 do `docs/entregas-cupons-spec.md` (§3.7, decisões
I1–I3): base de contatos limpa antes dos blocos dependentes.

- **Renomeador em lote com preview obrigatório** (I3): regras configuráveis
  (trim, remoção de prefixos `WA-`/`WPP-`/`+`, capitalização Title Case
  preservando conectores, padrão "Nome — Bairro") aplicadas em
  `organizer.py` — funções puras testáveis. Preview calcula sem gravar;
  apply só aceita os códigos que o operador viu no preview e re-verifica
  o nome no banco (sem corrida com o sync do WhatsApp).
- **Backfill de códigos sequenciais** (I1): contato sem código recebe o
  próximo da sequência global do tenant (`proximo_codigo`); buracos
  pré-existentes não são renumerados. Idempotente.
- **Lista "Revisar"**: conflitos detectados e apenas sinalizados — nome
  duplicado (avaliado no nome normalizado sem prefixos, que é o que o
  renomeador produziria) e telefone fora do padrão BR. Contato em
  conflito é **preservado e excluído do rename em lote**;
  correção é sempre manual.
- **Audit** (padrão P0 3.3): `contact.rename` e `contact.backfill_code`
  com before/after em `auth_audit_log`, best-effort (nunca derruba a
  operação).
- **Endpoints** (sob `/whatsapp/contacts/organizer`, permissão
  `customer.update`): `POST rename-preview` · `POST rename-apply` ·
  `POST backfill-codes` · `GET conflicts`.
- **Frontend**: `ContactsOrganizerPage` em `/whatsapp/contacts/organizer`
  (item "Organizador" no grupo WhatsApp) — regras → preview com seleção
  individual/lote → aplicar; backfill no header; lista Revisar com badges.
- Testes: backend +28 (`test_contacts_organizer.py`: regras puras,
  preview/apply, backfill, conflitos, audit via API HTTP) · frontend +5
  (`ContactsOrganizerPage.test.tsx`). Totais: backend 1544 · frontend 239.

### 📱 F2.5.1 — Build nativo Android do app do entregador

Fecha o item "build nativo (APK)" pendente da F2.5: shell Android criado,
autolink do geolocation validado e **APK debug gerado com sucesso**
(`android/app/build/outputs/apk/debug/app-debug.apk`, universal, ~107MB).

- **Shell `mobile/android/`**: template RN 0.76 (Gradle 8.10.2, AGP via
  react-native-gradle-plugin, `com.gasflowdriver`, Hermes ON),
  `MainActivity`/`MainApplication` padrão, manifest com
  `ACCESS_COARSE/FINE_LOCATION` (sem background location — decisão B2).
- **Configs RN**: `index.js` (registro do App), `babel.config.js`,
  `metro.config.js`, `react-native.config.js`, `app.json`.
- **`wired.tsx`**: troca `require()` opcional por **import direto** de
  `@react-native-community/geolocation` — lib autolinkada no build nativo.
- **`react-native-screens` fixada em 4.4.0** (exact): a 4.28 derruba o
  codegen do RN 0.76 (`Unknown prop type "accessibilityContainerViewIsModal"`).
- **`newArchEnabled=false`**: CMake/ninja do NDK corrompem paths não-ASCII
  (repo vive em "…\\automação zap\\"); Fabric volta quando o repo migrar
  para caminho ASCII.
- **Limitação de ambiente (documentada em `mobile/android/BUILD.md`)**:
  buildar exige caminho ASCII + JDK 17 (`JAVA_HOME` do sistema aponta pro
  8). Receita: copiar `mobile/` para um caminho ASCII (ex.: `C:\gflow\mobile`),
  `npm ci` e `gradlew assembleDebug`.

### 🛰️ F2.5 — Rastreamento no App do Entregador (mobile)

Fecha a captura GPS da cadeia do rastreador (mobile → relay → desktop →
backend → mapa do operador), complementando o Fix #1 (ingestão via relay)
e o Fix #2 (gate EM_ROTA no desktop):

- **`logic/tracking.ts`** (novo, módulo puro): gate B2 idêntico ao desktop
  (auto on/off por `ASSIGNED/DISPATCHED/EN_ROUTE`, override manual
  respeitado e limpo ao fim da rota), work-hours LGPD fail-closed no
  cliente (fora da janela não captura — nem com override), cadência pelo
  intervalo do servidor (`driver.tracking.interval_seconds`, default 120s,
  min 15) e roteamento de envio: **lan** → `POST /api/v1/driver/location`
  (JWT) · **cloud** → `POST {relay}/driver/location` (`X-Relay-Token`) ·
  **offline** → fila (`kind: "location"`) com replay no flush.
- **`TrackingController`**: captura só quando deve (watch injetado;
  zero captura fora de rota — bateria + LGPD); falha de rede enfileira.
- **`api.ts`**: `fetchDriverMe` (intervalo + `work_hours`),
  `postDriverLocation` (LAN), `postDriverLocationRelay` (nuvem).
- **`wired.tsx`**: cola nativa com `@react-native-community/geolocation`
  (watch injetável; ausente ⇒ rastreio indisponível, sem crash);
  `useTrackingGate` liga o gate às entregas visíveis; `makeTransport`
  roteia posições da fila pelo canal ativo; botão "Iniciar rota" antecipa
  o rastreio (`setOverride(true)`).
- **Backend**: `/driver/me` agora expõe `work_hours` ("HH:MM-HH:MM") — o app
  respeita no cliente a mesma janela que o backend reforça no ingest.
- **`logic/config.ts`** (novo): alvos LAN/relay + relayToken (defaults de
  dev, override pelo desktop via `setConnectionConfig`).
- Testes: mobile +14 (gate, cadência, roteamento, controller) · backend +1
  (`/driver/me` expõe intervalo e janela).
- Pendente para produção: `npm i @react-native-community/geolocation` no
  build nativo (APK), deploy do relay (Fly.io) e smoke em campo.

### 👥 Comunidade WhatsApp (F5)

- Setting `whatsapp.community_invite_link` (link do Community)
- Envio automático do convite pós-cadastro (event-driven, idempotente)
- Filtro de audiência por status de comunidade nas Campanhas
- Frontend: campo de config + indicador de status no perfil do cliente
- Requer WhatsApp módulo v1.1.6+ e link configurado (vazio = desabilitado)

### 🖨️ F3 — Impressão em tempo real + zap do entregador (16/09/2026)

Implementação da F3 do `docs/entregas-cupons-spec.md` (§3.4):

- **Filtro de status no auto-print** (setting `printer.auto_print.min_status`,
  default `PAID,CONFIRMED`): o auto-print só cria job quando o pedido entra
  em um dos status configurados — sem filtro, todo pedido novo viraria
  impressão. Idempotente por pedido (evento repetido não reimprime; falha
  do agente libera a marca para nova tentativa). Gatilho plugado no
  `PATCH /orders/{codigo}/status` via `_safe_auto_print` (nunca falha a
  requisição). Impressão manual (botão/reprint) nunca é bloqueada.
- **Zap do entregador na atribuição** (`driver_notification.py`): ao atribuir
  uma entrega (`AssignmentService.assign`), enfileira uma execução no
  executor de automações existente (sem fila paralela; envio pelo fluxo
  `process-pending`/poller com pacing/anti-ban). Idempotente por
  (delivery_id, driver_id): mesma dupla não reenvia; reatribuição para
  outro entregador cria nova execução. Sem telefone cadastrado ou com erro
  de infraestrutura, a atribuição segue intacta (log + skip).
  Template default configurável via setting
  `driver.assignment_notification_template`.
- **Botão "Imprimir" na página de Pedidos**: chama `POST /printer/print`,
  com toast de sucesso/erro e estado de carregamento por pedido.
- Testes: backend +11 (filtro/idempotência do auto-print; dedup e hook da
  notificação) · frontend +2 (botão chama API; toast de erro/sucesso).
  `renderWithProviders` agora inclui `ToastProvider`.

### 🎟️ Cupons + Indicação + IA (F4)

- **Tabela `referrals` + `invite_token` em cupons**: modelo de indicação com
  convite via link WhatsApp. Migration incluída.
- **Limite 10 indicações/mês** (config `referral.max_per_month`) + validade
  90 dias (`referral.coupon_validity_days`). Bloqueio da 11ª indicação com
  erro claro.
- **Tool `register_referral`**: auto-cadastro via IA na conversa (decisão §5
  do spec). Registra cliente + gera cupons para indicador e indicado.
- **Tool `list_client_coupons`**: IA consulta cupons ativos antes de fechar
  pedido e oferece automaticamente (cap 1 ofertas/conversa).
- **Endpoints** `GET /coupons/by-client/{id}` e
  `GET /coupons/by-client/{id}/referrals`: perfil do cliente com cupons e
  histórico de indicações. Endpoint `POST /coupons/generate-invite-token`
  para gerar token de convite.
- **Frontend**: abas "Cupons" e "Indicações" no perfil do cliente; botão
  "Gerar link de convite" na página de Promoções com cópia para clipboard.
- **Rate limit** no auto-cadastro: 3 tentativas/telefone/hora, 5/IP/hora
  (MVP em memória).

### 🧪 F4.5 — Refinamento e testes (16/09/2026)

- **Bugfix**: código do cupom de indicação usava apenas 1 char aleatório
  (`INDICA-{token[:8]}`), causando colisão UNIQUE. Corrigido para 12 chars.
- **Bugfix**: código do cupom de indicado (`BEMVINDO-{codigo}`) colidia
  quando o mesmo telefone se cadastrava duas vezes. Adicionado sufixo UUID.
- **Testes backend**: +9 `test_referral_service.py` (service), +10
  `test_ai_referral_tools.py` (tools IA). Total suite: 1532→1551.
- **Testes frontend**: +5 `ClientCouponsTab.test.tsx`, +4
  `ClientReferralsTab.test.tsx`, +3 `CouponsPage.invite-link.test.tsx`.
- **Store TTL compartilhado (TODOs de produção resolvidos)**:
  `app/core/whatsapp_limits.py` — `WhatsAppLimitStore` com sliding window ZSET
  em Redis quando `RATE_LIMIT_MODE=redis` (reusa o singleton do core
  `rate_limit.py`; persiste entre reinícios e workers) e fallback in-memory
  fail-open por worker. Usado por `tools_impl.py` (rate limit do auto-cadastro:
  3/telefone/hora, 5/IP/hora) e por `gateway.py` (cap 1 oferta de cupom por
  conversa, TTL 2h). Testes: +12 `test_whatsapp_limits.py`, +2
  `test_coupon_offer_cap.py`.
- **R1 verificado**: rate limit IP (5/hora) não funciona em contexto WhatsApp
  porque o IP não é extraído do webhook. Apenas phone (3/hora) é efetivo;
  o parâmetro `ip` fica reservado ao futuro endpoint web público (§5).
- **R2 verificado**: prompt instrui corretamente sobre token GF-INV-,
  coleta de dados, register_referral e cap 1/conversa.
- **Cap 1/conversa**: in-memory dict com TTL 30min — não testável como
  unitário; documentado como integration-only.

### 📱 F2 — Mobile RN: navegação com gates + consentimento LGPD + fila offline ponta a ponta (16/09/2026)

Implementação da F2 do `docs/entregas-cupons-spec.md`:

- **RootNavigator com gates** (`src/navigation/`): login → consentimento →
  rota do dia → detalhe da entrega. Swipe desabilitado nos gates (não puláveis);
  splash mínimo enquanto o consentimento persistido carrega (sem flash).
- **ConsentScreen LGPD (B3)**: bloqueante no 1º login, texto sem jargão (o quê,
  quando, retenção 90 dias, quem vê), checkbox obrigatória. Registro com data +
  `CONSENT_VERSION` no store zustand (`logic/session.ts`) com storage injetável
  (memória nos testes; AsyncStorage entra na F2.5). Termo antigo ou storage
  quebrado = fail-closed (pede de novo).
- **Fila offline ponta a ponta (C4.3)**: contêineres wired (`src/containers/`)
  ligam as telas ao store + `OfflineQueue` + `POST /driver/deliveries/:id/:action`
  com `client_action_id` no corpo. Sem rede: ação fica `pending` e reenvia no
  flush ao reconectar; duplicata nunca chega ao servidor (1 POST por id).
- **API pura (`logic/api.ts`)**: login `/auth/mobile/login`, entregas e ações
  com baseUrl/fetch/token injetáveis — testável em node --test.
- Fix de dependências (`react-native-screens` 4.x, `react-native-permissions`
  5.x — versões nos package.json não existiam mais no registry) e do script de
  teste para glob (`node --test "tests/**/*.test.ts"` — Node 24/Windows não
  aceita diretório como alvo).
- Sem build nativo nesta fase (F2.5) — typecheck `tsc` cobre telas+navigator
  e suíte de lógica roda em CI.
- Testes: +7 mobile (5 consent gate fail-closed/versão do termo/persistência,
  2 replay offline→synced + não-duplicação). Suíte: mobile 16 ✅.

### 🗺️ F1b — Mapa do operador com posição dos entregadores (16/09/2026)

Implementação da F1b do `docs/entregas-cupons-spec.md`:

- **`DriverMap` (Leaflet + tiles OSM, sem API key)**: componente único
  reutilizável — marcadores circulares verdes (posição fresca) ou cinza
  (`is_stale`, >5min no backend), popup com nome e idade da posição,
  fitBounds automático, estado vazio instrutivo.
- **Páginas Entregas e Motoristas** (decisão do dono): mesmo componente nas
  duas telas; nomes dos motoristas juntados às posições no cliente.
- **Hook `useDriverLocations`**: consome o `GET /delivery/locations` (que já
  existia) com **polling de 30s** (padrão do repo — posição não vai por WS
  para evitar refetch storms, ver `lib/realtime.ts`).
- Sem coordenadas em logs/telemetria (LGPD).
- Testes: +3 frontend (`DriverMap` com Leaflet mockado: vazio, render,
  cleanup). Suítes: frontend 196 ✅, backend 1448 ✅ (F1a).

### 🚀 F1a — Entregador desktop: sessão, notificação e rastreio configurável (16/09/2026)

Implementação da F1a do `docs/entregas-cupons-spec.md` (fase 1 de 9):

- **Notificação de atribuição em tempo real (<10s)**: dois fixes no roteamento
  do WebSocket — `delivery.assigned` (publicado com o motorista como actor
  `DRIVER`) agora roteia também para o canal `driver:{id}`; e o check de tenant
  do `/ws` não fecha mais conexões de motorista com 4003 (canal `driver:{id}`
  não contém o tenant; permitido apenas para o próprio `driver_id` da sessão).
- **Guard de sessão no desktop**: com `driver_token` ativo e sem token de
  operador, `DashboardLayout` renderiza só o app do motorista (sem sidebar,
  header, RealtimeBridge de operador ou IA flutuante). Operador visitando
  `/driver` (os dois tokens presentes) mantém o layout admin intacto.
- **Intervalo de rastreio configurável**: nova setting
  `driver.tracking.interval_seconds` (default **120s**, min 15, categoria
  operations) exposta em `GET /driver/me`; o app do motorista throttleia o
  envio de GPS pelo intervalo (watchPosition continua capturando a melhor
  posição, o envio é que respeita a bateria).
- Testes: +2 backend (roteamento assignment → driver channel; sem actor
  DRIVER não roteia). Suítes: backend 1448 ✅, frontend 193 ✅, desktop 41 ✅.

### 🏗️ Reorganização Estrutural — v1.1.6 (16/09/2026)

Implementação completa do `docs/reorg-plan.md` (F1–F6):

- **Sidebar em 8 grupos** (era 18 itens chapados): Dashboard, WhatsApp
  (Conversas/Contatos/Campanhas/Automações/Contas & Conexão), Pedidos,
  Entregas (Entregas/Motoristas), Clientes (Lista/Segmentos/Recompra/Cupons),
  Produtos & Estoque (Produtos/Estoque/Notas de Compra), Financeiro &
  Relatórios, Configurações (Geral/Usuários/Auditoria/IA). Grupos colapsáveis
  que abrem sozinhos conforme a rota; fonte única em `nav.tsx` compartilhada
  entre desktop e mobile.
- **Módulo WhatsApp único**: rota `/contacts` removida — Contatos virou sub-rota
  `/whatsapp/contacts` (feature `contacts` absorvida pelo módulo whatsapp);
  `/whatsapp` agora é a home de Conversas; Campanhas em `/whatsapp/campaigns`;
  **Contas & Conexão** em `/whatsapp/accounts` (guard `whatsapp.read`) com a
  seção **WhatsApp Web** embutida (mesma flag `waWebPanel.enabled`) — rota
  `/whatsapp/web` removida.
- **IA como bolinha flutuante** (`FloatingCopilot`): FAB canto inferior-direito
  + slide-over com o chat do Copilot, persistência no localStorage, oculto em
  login/driver. Rota `/intelligence` e `IntelligencePage` **deletados**.
- **Backend em pastas por módulo** (`presentation/api/`): `whatsapp/`
  (accounts, gateway, automation, cloud_webhook, contacts), `catalog/`
  (products, inventory), `logistics/` (delivery*, dispatch, driver*),
  `finance/` (finance, payments, reports), `core/` (auth, health, settings,
  admin, dashboard). **Rotas de API preservadas** — única exceção:
  `/clients/contacts` → **`/whatsapp/contacts`** (consumidor único = nossa UI;
  serviço WhatsApp atualizado em `crm-sync.ts`).
- **POST /whatsapp/contacts/sync** movido para o namespace de contatos
  (mesma semântica de proxy ao serviço Node).
- **Limpeza total do banco (migration v4, `reorg_cleanup_v4`)**: clients,
  whatsapp_conversations/messages, ai_* e afins zerados no boot + catálogo
  real semeado — Água 20L R$10 e Gás P13 R$120 (cartão 1x R$125 / 2x R$130).
  `auth_*`, `system_settings` e RBAC intocados. Backup automático pré-migration.
- Suítes: backend 1446 ✅, frontend 193 ✅ (194 − 1 teste do
  IntelligencePage deletado com a rota; +3 novos do Copilot/WhatsApp),
  whatsapp 94 ✅, desktop 41 ✅,
  mobile 9 ✅.

### 🧪 Protótipo — Painel WhatsApp Web (14/09/2026)

- **Híbrido WhatsApp Web no desktop (F0–F5)**: WebContentsView com WhatsApp
  Web dentro da janela do GasFlow, para **apenas pairing, status e
  visibilidade operacional** — o envio continua 100% no Baileys. Uma view por
  conta (`persist:wa-web-<accountId>`), UA Chrome pinado, permissões negadas
  (câmera/mic/geo/notificações), healthcheck de presença (sem scraping).
- **Feature flag `waWebPanel.enabled` (default OFF)**: com a flag off,
  nenhum WebContentsView é instanciado e a página React mostra "desativado".
- Tela `/whatsapp/web` (guard `whatsapp.read`): abas por conta com badges de
  estado, botões abrir/re-parear/fechar, bounds sincronizados via
  ResizeObserver e push de status view → main → React (≤5s).
- Documentação em `docs/whatsapp-web-panel.md` (backup de `Partitions/`,
  expectativa de duas sessões independentes, riscos e plano de teste manual
  por fase). Suítes: desktop 29 → **41**, frontend 189 → **194**.

### 🔧 Correções — WhatsApp (14/09/2026)

- **Recuperação por caminho de desconexão** no provider: `logged_out` (401)
  agora apaga as credenciais (`baileys_auth/<id>/`) com guard de re-entrância,
  timeout de 10s e erro logado, antes do re-init (antes: `disconnect()`
  mantinha as creds → loop com sessão inválida); 428/440 limpam apenas a
  sessão Signal (preserva creds.json) com backoff e escalam para wipe após
  3 falhas; 515 tem restart único antes de tratar como 428.
- **Telemetria de diagnóstico**: evento `close` do Baileys propaga
  `statusCode`/texto do Boom (`account.connection_closed`), toda transição
  de estado emite `account.state_transition` e o contador
  `disconnectsByReason` é exposto nos endpoints de health.
- Runbook de re-pareamento (QR) em `docs/whatsapp-recovery-runbook.md` —
  diagnóstico do incidente de 06/09: o loop real era 408 com QR nunca
  pareado (nem 401, nem 428). Suíte: 86 → 94 testes.

### 🚀 Funcionalidades — App do Entregador, Fase 1 (14/09/2026)

- **Mobile auth** (`/auth/mobile/login|refresh|logout`): access token 15min
  (mini-JWT HS256 stdlib, escopo `mobile`) + refresh 7d com rotação e
  detecção de replay (reuso revoga a família), rate limit 10 login/min/IP.
  Sem dependência nova (sem PyJWT). `_authenticate_driver` aceita sessão DB
  ou JWT mobile — desktop continua isolado. Ver `docs/driver-app.md`.
- **LGPD no rastreamento**: location em lote com janela de trabalho
  (`driver.work_hours.start/end`, admin edita; fora → 403 + audit),
  retenção de 90 dias com purge idempotente no boot, audit de cada
  acesso/ingestão (sem coordenadas no log).
- **Delta sync** `GET /driver/sync?since=` com tabela `offline_sync_log`.
- **Relay na nuvem** (`relay/`): FastAPI + WS registry + cache de última
  posição; Dockerfile/fly.toml prontos — **deploy não executado** (decisão:
  código local; ver `relay/DEPLOY.md`).
- **Desktop relay-client**: WebSocket outbound com backoff 1s→60s,
  settings `relay*`, IPC `gasflow:driver-location`.
- **Scaffold mobile** (`mobile/`): lógica pura testada (fila offline com
  client_action_id/backoff/cap 5min, work-hours fail-closed, fallback
  LAN→nuvem→offline) + telas RN do MVP escritas.
- **Testes**: +11 backend (`test_driver_mobile.py`), +6 relay, +4 desktop,
  +9 mobile lógicos.

### 🚀 Funcionalidades — Item 3: IA no boot (14/09/2026)

- **IA pronta no primeiro boot**: `desktop/src/main/ai-setup.ts` detecta o
  Ollama em background (nunca bloqueia o app), pede consentimento antes de
  instalar (~800 MB, uma vez) e baixa o modelo com progresso via IPC
  (`ai:status-changed`, `ai:download-progress`). Retry 3x com backoff;
  qualquer falha vira estado `unavailable` — o boot jamais é afetado.
  Ver `docs/ai-setup.md`.
- **Factory de LLM com toggle admin**: `ai.enabled` (default ON) no quadro
  de configurações derruba toda a IA em runtime, sem restart. Health check
  do Ollama cacheado por 30s (timeout 2s); Ollama indisponível →
  `NullProvider` (degradação graciosa — cenário B da Fase 4.2: **sem**
  fallback externo, dados nunca saem da máquina). Provider desconhecido
  degrada em vez de cair no mock.
- **Tela Admin → Inteligência** (`/settings/ai`, permissão `ai.configure`):
  status sem jargão ("IA pronta" / "Preparando IA… 45%" / "IA local
  indisponível"), toggle "Ativar Inteligência", seção Avançado colapsada e
  teste rápido. Nenhum termo técnico fora do Avançado.
- **Endpoints `/ai/status`, `/ai/test`, `/ai/settings` (GET/PATCH),
  `/ai/model/download`(+progress)** com RBAC (`ai.use`/`ai.configure`) e
  auditoria (`ai.settings.changed` com before/after, `ai.test.prompt` com
  **hash** do prompt — nunca conteúdo).
- **RBAC**: permissão `ai.configure` nova (MANAGER); `ai.use` concedida a
  OPERATOR (catálogo + matriz + fallback de domínio).
- **Testes**: +9 backend (`test_ai_provider.py`), +6 desktop
  (`ai-setup.test.ts`), +5 frontend (`AISettings.test.tsx`). Suítes:
  backend 1434 ✓, frontend 189 ✓, desktop 25 ✓; mypy/ruff/tsc limpos.

### 🔄 Mudanças de negócio (14/09/2026)

- **Débito de estoque na entrega (Decisão B3a)**: o estoque só é debitado
  quando a entrega é finalizada (`DELIVERED`) — 1 cheio sai e 1 vazio entra
  (`deliver_stock_atomic`, commit único e idempotente). O pedido `CONFIRMED`
  não debita mais; `CANCELLED` do pedido é no-op; cancelamento da entrega
  após `DELIVERED` reverte o débito (`reverse_delivery_stock_atomic`).
  Migração v3 one-shot e idempotente no boot reverte débitos prematuros de
  pedidos antigos (movimento `RESERVATION_REVERSAL` + auditoria em
  `auth_audit_log`; marca em `system_settings`).
  Ver `docs/migrations/2026-09-delivery-debit.md`.

### 🚀 Funcionalidades

- **CRM ↔ WhatsApp (contatos)**: push automático de contatos do WhatsApp
  para o CRM (`crm-sync.ts`) — no boot, ao conectar a conta e manualmente.
  Upsert idempotente por telefone em `POST /clients/contacts/sync-batch`
  (lotes de `BATCH_SYNC_SIZE`, tolerante a falhas de rede).
- **Import/export VCF**: `POST /clients/contacts/import-vcf` e
  `GET /clients/contacts/export-vcf` (parser vCard próprio, sem dependência).
- **Enriquecimento por IA**: `POST /clients/contacts/{codigo}/enrich` extrai
  endereço embutido no nome do contato (LLM, no-op seguro em falha).
- **Reativação de inativos**: `POST /clients/contacts/reactivate` (com
  `dry_run`) cria executions para clientes OPTED_IN inativos há N dias
  (`whatsapp_reactivate_days`/`_template`/`_enabled` nas Configurações ›
  Sistema). Idempotente por cliente/dia; envio pelo executor de automações.
- **Executor em background (opt-in)**: `AUTOMATION_POLL_SECONDS>0` processa
  executions PENDING automaticamente; default desligado (cron externo
  chamando `POST /whatsapp-automation/process-pending` continua válido).
- **Tool `update_client_address`**: a IA pode atualizar o endereço do
  cliente na conversa (requer confirmação, permissão OPERATOR).
- **Última interação no CRM**: mensagens recebidas atualizam
  `last_interaction_at` (base da elegibilidade de reativação).
- **Configurações do sistema no frontend**: painéis de Sistema (quadro de
  configurações por categoria) e Usuários/Permissões (matriz RBAC).
- **Página de Promoções/Cupons** conectada à API de cupons.

### 🐛 Correções

- `sync-batch` agora é **service-key only** (`require_whatsapp_service`,
  `X-GasFlow-Key`): sem fallback JWT — token de usuário vazado não consegue
  sobrescrever o CRM em lote; fail-closed sem chave configurada.
- Contexto de serviço usava `tenant_id="1"` (contatos invisíveis no CRM);
  alinhado ao tenant do admin (`"default"`).
- `NameError` de `Tuple` em `contacts/service.py` (derrubava o boot).
- Reativação usava `was_recently_contacted(days=)` (assinatura errada) e
  duplicava a fila em re-execução no mesmo dia (PENDING não contava como
  contato) — substituído por checagem de REACTIVATION do dia.
- Botão "Sincronizar WhatsApp" não empurrava contatos ao CRM (chamava
  `sync-batch` vazio com JWT); agora dispara o push real via serviço.
- Boundary test de CRM tolera campos de sync na entidade Client (checa
  `import` real, não menção textual).

### 📦 Dependências e build (12/09/2026)

- **Merge de 21 PRs do Dependabot na main**: GitHub Actions (upload-artifact
  7, build-push 7, login 4, metadata 6, setup-buildx 4), imagens Docker
  (`python:3.14-slim`, `node:26-slim` no frontend e whatsapp), pip do backend
  (pytest ≥9.1.1, pytest-asyncio ≥1.4.0, pytest-timeout ≥2.4.0, ruff ≥0.16.5,
  prometheus-client), npm do frontend (React 19.2, Vite 8, zod 4.5,
  lucide-react 1.40) e do whatsapp (tsx 4.23.13, @types/node 26.5).
- **Express 4 → 5** no serviço WhatsApp: `app._router` (removido no v5)
  substituído por despacho direto pelo Router no alias `/send`; coerção
  `String()` nos 15 usos de `req.params` (tipagem `string | string[]` do
  express 5). tsc/eslint/build e 86 testes passando.
- **Desktop**: TypeScript 5.8 → 6.0.3 e `@types/node` 22 → 24 (Electron 44
  embute Node 24.20); `electron-builder.yml` corrigido para o schema do
  electron-builder 26 (`publisherName` migrou para `signtoolOptions`) —
  desbloqueia `npm run dist`. Instalador NSIS 1.1.2 gerado e validado
  (asar + extraResources: backend exe, agent, whatsapp, frontend).
- TypeScript mantido em **6.0.3** no frontend/whatsapp: `typescript-eslint`
  8.70 ainda exige `<6.1` (TS 7 volta quando houver suporte).

## [1.0.0-rc.4] - 2026-09-05

Resiliência do WhatsApp + integração com o app do entregador
(ver `docs/phase16/PHASE16_WHATSAPP_RESILIENCE_INTEGRATION.md`).

### 🐛 Correções

- **`--disable-dev-shm-usage` no arquivo errado (rc.3)**: o fix que destravou
  o QR em Docker estava em `wwebjs-provider.ts` (código morto); o runtime usa
  `provider-manager.ts`, que não tinha a flag. Movido para o caminho real.
- **Bridge de mensagens recebidas inexistente**: o serviço WhatsApp nunca
  enviava mensagens ao backend — o `POST /whatsapp/incoming` (IA + conversas)
  existia mas nada o chamava. Bot não funcionava ponta a ponta.

### 🚀 Funcionalidades

- **Heartbeat de presença** (`sendPresenceAvailable` a cada 5 min por padrão,
  `WA_HEARTBEAT_INTERVAL_MIN`) para manter a sessão ativa.
- **Reconexão endurecida**: 10 tentativas com backoff exponencial (5s→80s +
  jitter) e alerta webhook (`WA_CRITICAL_WEBHOOK_URL`) ao esgotar.
- **Envio de mídia**: `sendMedia` no contrato do provider + endpoint
  `POST /api/whatsapp/accounts/:id/media` (base64 ou mediaPath, idempotente).
- **Bridge de entrada whatsapp → backend**: mensagens recebidas são
  encaminhadas para `/whatsapp/incoming` (autenticadas via `X-GasFlow-Key`),
  e a resposta da IA é enviada de volta automaticamente (loop fechado).
- **Pacing humano de campanhas**: intervalo aleatório 2–10s entre envios
  (`WA_SEND_MIN/MAX_INTERVAL_MS`) no lugar do fixo de 2s.
- **Logs estruturados** (JSON lines) no serviço WhatsApp.
- **Auth service-to-service no backend**: `/whatsapp/incoming` aceita
  `X-GasFlow-Key` = `WHATSAPP_SERVICE_KEY`/`MARCOS_GAS_API_KEY`.
- **CI/CD do entregadorGasFlow**: workflow GitHub Actions (typecheck + build +
  testes) no repositório do app do entregador.

### 🧪 Testes

- WhatsApp: 38 → **53** (bridge de entrada + mídia).

### 🔐 Hardening anti-ban, canal oficial e motor Baileys (incluído na tag rc.4)

- **Anti-ban no serviço WhatsApp** (`src/anti-ban/`): caps por janela deslizante
  (20/min, 200/h, diário com warmup 50→1000 em 7 dias), cooldown por
  destinatário (60 min), quiet hours (22:00–07:00), pacing gaussiano (média 3s,
  σ 1s) — tudo persistido em SQLite (`send_history`, `send_counters`) e
  configurável por env (`WA_*`). Kill-switch `WA_BROADCAST_ENABLED`.
- **Canal oficial Cloud API (backend)**: `cloud_api_adapter.py` (texto, mídia,
  templates aprovados, E.164, erros mapeados, `list_message_templates`) +
  webhook assinado HMAC (`/api/v1/whatsapp/cloud-api/webhook`) + factory
  `WHATSAPP_PROVIDER=cloud_api`. Campanhas de massa devem migrar para cá.
- **Motor Baileys (dual-mode)**: `WA_ENGINE=baileys|wwebjs` (e
  `WA_ENGINE_PRIMARY/SECONDARY` por conta) — WebSocket puro, sem Chromium;
  pareamento por QR ou pairing code (`WA_PAIRING_CODE_PHONE`); rollback = 1
  env var. Dockerfile slim (`BUILD_WWEBJS=1` para build antigo).
- **Observabilidade**: `/metrics` Prometheus no serviço WhatsApp
  (`whatsapp_messages_sent_total`, `whatsapp_messages_failed_total`,
  `whatsapp_account_connected`, reconexões) e no backend
  (`gasflow_http_requests_total`, duração). Stack Prometheus + Grafana
  (provisionado) + Alertmanager no compose prod (`monitoring/`), com receiver
  `POST /api/v1/webhooks/alerts` no backend.
- **Segurança/CI**: Dependabot (npm/pip/docker/actions, semanal), job Trivy
  (CRITICAL+HIGH) no CI, pre-commit (ruff + ruff-format + higiene).
- **Testes**: WhatsApp 53 → **99** (anti-ban + engine Baileys + métricas);
  backend 1223 → **1244** (Cloud API, webhook, alerts); frontend 159 (devtools
  React Query em DEV).
- Backend: +4 testes HTTP de auth do `/whatsapp/incoming`.

## [1.0.0-rc.3] - 2026-09-04

Round de execução das pendências restantes (QR pareado ao vivo, GHCR
publicado, FE-02 completo).

### 🚀 Funcionalidades

- **WA-02 (pendência)**: pareamento real do WhatsApp concluído — QR escaneado
  e sessão `primary` conectada (número 559181689969) persistida no volume
  `gasflow_whatsapp_auth`.
- **WA-02 (pendência)**: harness live `test_provider_live_harness.py`
  **12/12 passando** contra o serviço real conectado (envio de mensagem,
  idempotência, contatos, sessão, health, QR, stop/restart, erros) —
  `LIVE_MODE=true WHATSAPP_TEST_PHONE=559181689969 WHATSAPP_SERVICE_URL=http://localhost:3001`.
- **FE-02 (pendência)**: testes para as 7 telas reais restantes
  (CampaignResultsPage, ConversationsPage, CopilotPage, IntelligencePage,
  ReorderPage, PaymentSettingsPage, LoginPage) — **29 testes novos**, frontend
  agora com **159 testes**.
- **E2E WhatsApp**: `e2e/tests/whatsapp.spec.ts` — renderização da página,
  estado de serviço indisponível (determinístico na stack E2E) e teste de
  sessão pareada gated por `E2E_WHATSAPP_CONNECTED=1` (CI-safe).
- **GHCR**: imagens publicadas — `git push origin main` + tag `v1.0.0-rc.2`
  enviados; workflow build-push disparado no remote.

### 🐛 Correções

- **whatsapp (`wwebjs-provider.ts`)**: adicionado `--disable-dev-shm-usage`
  aos args do Puppeteer — sem essa flag o Chromium não lançava em containers
  com `/dev/shm` de 64M (padrão Docker) e o QR nunca chegava ao estado
  `qr_pending`. Este é o fix que destravou o pareamento.
- **PaymentSettingsPage**: `fetchMethods`/`fetchConfigs` não limpavam o erro em
  sucesso — após um erro, o botão "Tentar novamente" nunca recuperava a tela
  (as demais páginas resetam o erro no refetch). Teste de regressão incluso.

## [1.0.0-rc.2] - 2026-09-04

Resolução de pendências levantadas nas fases anteriores (ver
`docs/phase15/PENDING_RESOLUTION.md`).

### 🚀 Funcionalidades

- **RT-01 (pendência)**: eventos `order.created`/`order.updated` publicados no
  Event Bus (criação, mudança de status e atribuição de motorista); bridge
  realtime assina `order.*`; frontend invalida lista de pedidos + dashboard.
- **Realtime multi-worker (pendência RT-01)**: Redis pub/sub opcional
  (`REALTIME_BACKEND=redis`) — eventos publicados em um worker uvicorn agora
  chegam aos WebSocket clients dos demais workers (prod roda `BACKEND_WORKERS=2`
  com um ConnectionManager por processo). Listener ignora eventos próprios
  (sem duplicatas) e roteia eventos remotos sem loops.
- **PIX PSP (pendência PIX-01)**: gateway de provedor (`mock` default +
  adapters HTTP p/ gerencianet/pagseguro/mercadopago) e webhook de confirmação
  `POST /payments/webhook/pix` (HMAC-SHA256) que encontra o payment por txid e
  confirma automaticamente.
- **FE-02 (pendência)**: testes para SegmentsPage, WhatsAppPage e
  AutomationsPage (loading/empty/error/list/interação) — total do frontend
  agora 130 testes.

### 🐛 Correções

- Nenhuma regressão; fixes de concorrência/sessão e do rate limiter Redis já
  estavam no rc.1 (GOLDEN).

### ⚠️ Limitações Conhecidas

- PSP real (Gerencianet/PagSeguro/Mercado Pago) aguarda credenciais para
  validação ao vivo (mock cobre o fluxo completo).
- WA-02 (live WhatsApp): 15 testes executados contra o serviço Node real
  (15/15 ✓, contas desconectadas — sem pareamento); a suíte completa
  (enviar/receber mensagens, 13 testes do harness) continua dependendo de
  telefone real pareado via QR.
- GHCR/E2E WhatsApp: aguardam push autenticado / pareamento (workflows e
  specs prontos).

## [1.0.0-rc.1] - 2026-09-04

Release Candidate 1 — primeira versão candidata a produção, cobrindo as fases
DB-01 → E2E + validação GOLDEN.

### 🚀 Funcionalidades

- **DB-01**: Migrations Alembic com baseline de 39 tabelas + drift guard.
- **DM-01**: Dashboard operacional com dados reais e KPIs.
- **API-01**: Contrato FE↔BE completo (0 divergências).
- **FE-01**: Inventário tela-a-tela (`docs/phase15/FE01_SCREEN_INVENTORY.md`).
- **DP-01**: CI/CD + Deploy (GitHub Actions + GHCR + `docker-compose.prod.yml`).
- **IA/Ollama**: Providers reais de LLM/STT/TTS (Ollama, Whisper, Piper) com
  fallback determinístico por ambiente (`MARCOS_GAS_*`).
- **SC-01**: Rate limiting com Redis compartilhado e fail-open in-memory;
  endpoints `/health` e `/ready`.
- **PIX-01**: Geração de PIX estático com BR Code (copia-e-cola) e QR Code
  (PNG base64), chave aleatória ou por tenant (`PixConfigRecord`).
- **FE-02**: Testes nas 11 telas sem cobertura (loading/sucesso/vazio/erro);
  cobertura do frontend subiu para ~57%.
- **RT-01**: Frontend conectado ao WebSocket por tenant já existente no backend
  (`useRealtime` + `RealtimeBridge` invalidando queries do React Query em
  eventos `delivery.*`/`driver.*`); proxies dev (`ws: true`) e prod (nginx
  `/ws` com Upgrade) configurados.
- **E2E**: Suíte Playwright contra o stack completo real em
  `docker-compose.e2e.yml` (8/8 estáveis): login/rotas protegidas, cliente,
  produto, motorista, pedido (criação + confirmação de status) e PIX.

### 🐛 Correções

- **AuthService: corrida de sessão DB** (E2E): o singleton de `AuthService`
  compartilhava UMA Session SQLAlchemy entre threads (threadpool + event loop
  do WS) — requests paralelas intercalavam `commit()`/queries e corrompiam a
  transação ("session is in 'prepared' state" → 500 para todo request
  autenticado). Fix: serialização com `RLock` + rollback em erro nos métodos
  que tocam DB + teste de regressão concorrente.
- **Rate limiter Redis ignorava `RATE_LIMIT_REDIS_URL`** (GOLDEN): o middleware
  construía `RedisSlidingWindowRateLimiter()` sem URL — o default
  `redis://localhost:6379/0` não alcança o Redis em container (host `redis`),
  então o circuit breaker degradava permanentemente para o fallback in-memory
  por processo (DBSIZE=0 em produção). Fix: passar `settings.rate_limit_redis_url`
  + testes de regressão do wiring.
- **ReportsPage**: estado de erro inalcançável (`Promise.allSettled`).
- **WhatsApp**: imagem migrada para `node:24` (node:sqlite).
- `bcrypt`/`reportlab` adicionados ao `requirements.txt`.
- `Optional[str, None]` → `Optional[str]` em agent_engine.
- **E2E**: specs idempotentes (telefones únicos por execução; login único via
  `storageState` para não estourar o rate limiter de login).
- **Nginx**: rota `/ws` com headers `Upgrade`/`Connection` + `proxy_http_version 1.1`.

### 📚 Documentação

- `DEPLOY.md` com arquitetura, passos, troubleshooting, escala e checklist de
  produção.
- `README.md` com badges de status, arquitetura e comandos.
- `docs/phase15/` com relatório de cada fase (DB-01 → E2E → GOLDEN).

### ⚠️ Limitações Conhecidas

- **WA-02 (live WhatsApp)**: testes ao vivo dependem de instância real pareada
  via QR — BLOCKED por ambiente; providers e testes com serviço real prontos.
- **RT-01**: `ConnectionManager` é in-process (1 worker/processo); Redis
  pub/sub para espalhar eventos entre workers é P2.
- **PIX-01**: status de pagamento é mock até integração com PSP/webhook
  (confirmação manual via `POST /payments/{id}/confirm`).
- Sessões de auth e de WhatsApp são em memória por worker/instância (1
  instância do whatsapp recomendada).
