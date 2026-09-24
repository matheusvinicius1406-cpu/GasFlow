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
