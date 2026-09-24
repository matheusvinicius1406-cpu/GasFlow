# Rastreio em segundo plano no Android — mapa, decisões e operação

> Documento vivo da missão "destravar o rastreio em segundo plano no app do
> entregador" (módulo nativo Kotlin atrás da costura `backgroundTracking.ts`).
> Cada item da ordem de execução acrescenta uma parte:
>
> | Item | Parte | Estado |
> |---|---|---|
> | 1. Mapear contrato + costura | Parte 1 | ✅ (2026-09-24) |
> | 2. ADR + minSdk | Parte 2 | ⛔ bloqueado (ver §7) |
> | 3. Módulo Kotlin + adapter `native` | Parte 3 | — |
> | 4. Permissões + degradação | Parte 4 | — |
> | 5. Validação em aparelho real (8 h) | Parte 5 | — |
> | 6. CI, docs, release em duas etapas | Parte 6 | — |

---

## Parte 1 — Mapa do contrato atual (item 1, 2026-09-24)

Levantamento **sem código novo**: só leitura de `mobile/src/**`, do backend e
dos testes que guardam o contrato.

### 1.1 Interface da costura (o que não pode mudar)

`mobile/src/logic/backgroundTracking.ts` exporta:

| Símbolo | Papel |
|---|---|
| `DEFAULT_BACKGROUND_CONFIG` | `distanceFilterM 20`, `intervalSeconds 120`, `maxBatchSize 50`, `retentionDays 7`, título/texto/canal da notificação, `geofenceRadiusM 150` |
| `buildTraceletConfig(config, syncUrl?)` | função **pura** que monta o config da lib |
| `toGpsPosition(location)` | converte o evento da lib em `GpsPosition` (o tipo do controller) |
| `deliveryGeofence(delivery, radiusM?)` | fence `delivery:{id}`, `notifyOnEntry` só (nunca conclui entrega) |
| `createBackgroundTracking(deps)` | o adaptador |
| tipos `TraceletLike`/`TraceletLocationLike`/… | forma esperada da lib de background |

`createBackgroundTracking(deps: BackgroundTrackingDeps): BackgroundTrackingHandle`
— `deps = { tracelet?, fallback, config?, syncUrl?, log? }`;
`handle = { watch, isBackground, addDeliveryGeofence(delivery), stop() }`.

**`watch` é a peça costurada:** `TrackingController` recebe a captura por injeção
e `wired.tsx:159` passa `backgroundTracking.watch`; sem lib nativa o mesmo
`watch` delega para o geolocation de primeiro plano. É esse contrato que o
módulo Kotlin precisa satisfazer — nada acima dele muda.

### 1.2 Os três caminhos de escrita que existem hoje

| Caminho | Chamada | Corpo | Autenticação | O que grava |
|---|---|---|---|---|
| **LAN (vivo)** | `POST {baseUrl}/driver/location` — `api.ts:233`, usado por `tracking.ts:125` e pela fila (`wired.tsx:251`) | `{latitude, longitude, accuracy?, speed?, bearing?}` — `LocationUpdate` (`driver_api.py:153`), **sem `recorded_at`** | `Authorization: Bearer <JWT do entregador>` | **só a última posição** (`upsert_location`) + evento realtime |
| **LAN (lote)** | `POST {baseUrl}/driver/locations` — `driver_self.py:219` | `{points:[{latitude, longitude, accuracy_m?, speed_kmh?, heading_deg?, recorded_at?}]}`, máx. **500** (`driver_self.py:41`) | idem | **histórico append-only** (`bulk_insert_history`) + upsert do mais recente + realtime + alertas |
| **Nuvem** | `POST {relay}/driver/location` — `api.ts:261`, `tracking.ts:135` | `{driver_id, tenant_id, positions:[{lat,lng,speed,heading,accuracy,recorded_at}]}` | `X-Relay-Token` | relay → desktop → `POST /api/v1/internal/driver/location/relay` (chave de serviço), que **reusa `handle_update_location` por posição** ⇒ também só upsert; `recorded_at` "não é consumido a jusante" (`driver_relay.py`) |

Regras aplicadas a **toda** origem (handler compartilhado
`handle_update_location`, `driver_api.py:830`):

- **work-hours LGPD** (`driver.work_hours.start/end`, seed 06:00–22:00): fora da
  janela → **403** e nada persistido; config inválida → fail-open;
- **throttle de 10 s** por driver: dentro da janela o request responde
  **200 `{success: true, throttled: true}`** (não é erro — o app ignora);
- o lote repete a mesma janela em `DriverLocationService.ingest_batch`
  (`driver_location_service.py`) e audita rejeição.

### 1.3 Fila offline (a fonte da verdade da persistência hoje)

`mobile/src/logic/offlineQueue.ts`:

- kinds reais: `start | complete | fail | location` (`offlineQueue.ts:18`);
- **dedupe de posição por `payload.recorded_at`** (`offlineQueue.ts:66-95`) —
  `enqueue("location", …)` com o mesmo `recorded_at` devolve o item existente;
- retenção local de **7 dias** (`LOCATION_RETENTION_DAYS`), poda de sincronizadas
  ou vencidas;
- backoff exponencial 2 s → cap 5 min, `pending()` ordenado por `createdAt`;
- ações levam `client_action_id` (UUID) no corpo; **posições não** — a
  identidade de uma posição, hoje, é o `recorded_at` que o JS carimba em
  `tracking.ts:324`;
- o transporte da fila roteia por modo de conexão (`makeTransport`,
  `wired.tsx:249`): `lan` → singular, `cloud` → relay, `offline` → lança e
  mantém pending.

### 1.4 Fatos do projeto Android

| Fato | Valor | Onde |
|---|---|---|
| RN | `react-native 0.76.0` (bare, Android-only) | `mobile/package.json` |
| **Arquitetura** | `newArchEnabled=false` — "CMake do NDK falha com o caminho do repo (`automação zap`)" | `mobile/android/gradle.properties` |
| Kotlin | `1.9.24` | `mobile/android/build.gradle` |
| minSdk / target | `24` / (targetSdk 34 declarado no README) | `mobile/android/build.gradle` |
| App id / versão | `com.gasflowdriver`, `versionCode 3`, `versionName 1.2.0` | `mobile/android/app/build.gradle` |
| Permissões hoje | `INTERNET`, `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION` — **sem** background/foreground service (comentário explícito: "sem foreground service no MVP") | `AndroidManifest.xml` |
| Permissões runtime | `permissions.ts` pede só `ACCESS_FINE_LOCATION` via `PermissionsAndroid`; `react-native-permissions ^5.6.2` está no `package.json` **sem uso** | `mobile/src/logic/permissions.ts` |
| `android.overridePathCheck=true` | já ligado (ajuda no caminho não-ASCII) | `gradle.properties` |
| NDK | `ndkVersion` é declarado (`app/build.gradle:93`), mas **não há `externalNativeBuild`** no app ⇒ um módulo Kotlin puro não precisa de CMake/NDK | `mobile/android/app/build.gradle` |

### 1.5 Guardas que já protegem este contrato

- backend: `tests/test_driver_location_ingest.py` (9 casos: exige driver,
  batch, **500 aceito / 501 rejeitado**, evento realtime, fora de hora = 403,
  canal por tenant, histórico escopado, `today_distance_km` no `/driver/me`) e
  `tests/test_driver_location_history.py` (13: insert/leitura/ordem/malformados/
  **"upsert não escreve no histórico"**/haversine/distância/tenant/purge);
- backend: `tests/test_driver_location_relay.py` (9) para o caminho do relay;
- mobile: `tests/tracking.test.ts`, `tests/offlineQueueLocation.test.ts` e
  `tests/backgroundTracking.test.ts` (o "fake" é um `TraceletLike` injetado).

### 1.6 Divergências entre o brief da missão e o código

1. **A interface da costura não é a que o brief descreve.** Não existe
   `start()`, nem `isRunning`, nem "eventos" próprios: existe
   `createBackgroundTracking(deps) → { watch, isBackground, addDeliveryGeofence, stop }`.
   Também **não há adapter `fake` como arquivo** — o fake é o duplo injetado em
   `tests/backgroundTracking.test.ts`, e a produção injeta `tracelet: null`
   (`wired.tsx:127`). Decisão: preservar a interface **real**; trocar por
   `start/stop/isRunning` seria mudança de contrato (proibida pelo próprio brief).
2. **O endpoint "que o app já usa hoje" não grava trilha.** O singular
   `/driver/location` só faz upsert da última posição. Quem escreve histórico é
   o lote `/driver/locations` (500), que o app **não** usa hoje. Um flush nativo
   pelo singular não produziria "trilha sem lacunas" — e o plural, embora seja
   rota existente e testada, seria rota nova para o app.
3. **Não existe idempotência de posição no servidor.** `driver_location_history`
   só tem índices (`delivery_persistence_model.py:176`), sem `UNIQUE`;
   `bulk_insert_history` insere o que receber (`delivery_persistence_repository.py:534`);
   o singular nem aceita `recorded_at`. A única dedupe é **no cliente**
   (`OfflineQueue`). Logo, "duas rotas de escrita, um só contrato" produz
   duplicata por construção — e o critério 4 ("sem perda e sem duplicata") é
   inalcançável hoje sem decisão sobre dedupe no servidor ou sem proibir a
   escrita direta do nativo.
4. **`recorded_at` só existe no caminho do lote** (e no relay, ignorado a
   jusante). Se a chave de idempotência for `recorded_at`, ela só vale no lote.
5. **A fila não tem `arrive`.** Os kinds reais são `start | complete | fail |
   location`; a rota `/driver/deliveries/{id}/arrive` existe no backend
   (`driver_self.py:173`) mas pertence ao item separado (chegada + prova).
6. **Achado fora do escopo, mas no caminho:** o transporte da fila manda
   `tenantId: "default"` **hardcoded** no modo nuvem (`wired.tsx:263`), enquanto
   o envio direto usa o tenant do snapshot (`tracking.ts:135`). Vale decidir se
   corrige junto ou em item próprio.
7. **Dependências que o brief implica não existem no projeto:**
   `FusedLocationProviderClient` (Play Services) e Room (+KSP). Alternativas sem
   dependência: `LocationManager` do Android e `SQLiteOpenHelper`.

### 1.7 Bloqueios que travam o item 2 (ADR)

O ADR precisa de decisão humana em quatro pontos; nenhum deles é inferível do
repositório:

| # | Bloqueio | Por que não dá para decidir sozinho |
|---|---|---|
| B1 | **Endpoint do flush nativo**: plural (trilha, 500/lote) ou singular (rota atual, sem trilha)? | as duas opções contrariam uma parte do brief (ver §1.6.2) |
| B2 | **Dedupe**: índice único aditivo em `(tenant_id, driver_id, recorded_at)` **no backend** (mudança de backend — o brief exige aprovação explícita) ou nativo **sem** escrita direta (só Room, entrega ao JS quando a bridge volta)? | decide o critério de aceite 4 |
| B3 | **minSdk 24 → 26**: quantos aparelhos da frota ficam de fora? | dado de campo, não está no repo |
| B4 | **Flag de rollback "sem novo build"**: de onde vem o interruptor (resposta do backend no `/driver/me`, toggle no app, ou só constante no build)? | "flag local" com rollback sem rebuild é ambíguo |

Decisões secundárias (também para o ADR): Play Services + Room **ou** APIs
nativas; teste instrumentado no CI (emulador) **ou** só em aparelho (item 5);
o job `mobile` entra também no `ci_gate` do release (hoje a allowlist tem 4 jobs).
