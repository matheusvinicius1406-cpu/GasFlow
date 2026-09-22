# Spec — Correções do rastreio (6 fixes) + Entrega inteligente (Opção D)

**Status:** aprovado na entrevista, pronto para execução.
**Data:** 22/09/2026
**Repo:** `GasFlow/` (raiz do git). Último commit: `e50cd97` — `feat(drivers): login próprio do entregador, rastreio completo e APK assinado` (Fases 1–7).

---

## 0. Objetivo

Duas entregas na mesma passada, **na ordem** (a ordem é deliberada: os fixes são bugs de produção e a interface de roteamento destrava as três fases seguintes):

- **Parte 1** — 6 correções no rastreio já entregue (Fases 3–7): alerta repetindo o dia inteiro, link público sem teto/revogação, linha de ETA saindo do ponto errado.
- **Parte 2 (Opção D)** — entrega inteligente completa: sequenciamento de rota (Fase 8), melhor entregador (Fase 9) e roteamento real plugável (Fase 10).

**Restrições globais:** somente open source e gratuito (OR-Tools Apache-2.0, OSRM BSD-2-Clause, OSM ODbL); nenhuma API key comercial; nada de hub/identidade/cliente paralelo; preservar CRLF dos arquivos já CRLF; nomes de código em inglês, comentários/CHANGELOG em português; feature flags em tudo; cada fase liga/desliga sem quebrar o comportamento anterior.

---

## 1. Estado atual da árvore (verificado)

`git status --short` → **23 entradas**, nada commitado:

**Modificados (16)** — Parte 1 já implementada: `app/application/tracking/{__init__,alerts_service,public_tracking}.py`, `app/infrastructure/repositories/{delivery_model,delivery_persistence_model,delivery_persistence_repository,delivery_repository}.py`, `app/presentation/api/public_tracking.py`, `tests/test_{tracking_alerts,public_tracking}.py`, `frontend/src/components/map/DriverMap{,.test}.tsx`, `frontend/src/features/deliveries/DeliveriesPage.tsx`.
Parte 2 já iniciada: `app/core/config.py`, `app/domain/events/event_bus.py`, `app/presentation/api/logistics/delivery_ops.py`, `gasflow-backend.spec`, `requirements.txt`.

**Novos (5)** — `app/application/dispatch/`, `app/application/routing/`, `app/domain/routing/`, `app/infrastructure/routing/`, `migrations/versions/f3a9c1e7d204_tracking_alerts_state.py`.

**Falta:** validar a migration, testes da Parte 2, app (`route.optimized`), painel (polyline), `docs/routing/osrm.md`, `docker-compose.osrm.yml`, README/OPERATIONS, CHANGELOG, APK, commits.

---

## 2. Realidade do repo × enunciado (reconciliado)

Tudo abaixo foi conferido no código. Onde o enunciado supõe algo que não existe, vale o repo.

| Enunciado supõe | Realidade | Consequência |
|---|---|---|
| `app/application/dispatch/` com o motor | `app/domain/delivery/dispatch_engine.py` (domínio puro, sem DB) + `app/application/delivery/dispatch.py` | O `DispatchScorer` (Fase 9) é novo em `app/application/dispatch/scorer.py`; o motor antigo não é reescrito |
| `route_deviation` como função reusável | **Não existe** como módulo: é cálculo inline (`route_score` em `score_candidate`) | `TrackingAlertsService` (Fase 7) já implementou o limiar direto — não reusar o inline |
| `RoutingProvider` a criar | **Já existe** em `app/domain/delivery/routing.py` (FASE 14: `geocode`/`calculate_route`/`estimate_eta` + `MockRoutingProvider`), vivo em `app/application/delivery/use_cases.py` e coberto por `tests/test_delivery.py` | **Decisão travada:** dois homônimos, em módulos distintos, com docstring cruzada. O ABC legado não é tocado |
| `dispatch_engine` delega ao scorer | O endpoint é `PATCH /delivery/deliveries/{delivery_id}/assign` (`delivery_ops.py:158`, `assign_delivery` em `:177`); a sugestão é `POST /delivery/dispatch/suggest` (`DispatchEngine.recommend` em `delivery_ops.py:882`, e também em `dispatch.py:90` com candidatos vindos da request) | A delegação entra no **endpoint de sugestão** (onde há DB/tenant/estoque), com o gate de elegibilidade preservado |
| `today_distance_km` sempre 0 | Já corrigido na Fase 3.3 | Fora de escopo agora |
| OR-Tools em `pyproject.toml` | **Não existe `pyproject.toml`**; deps em `backend/requirements.txt` (CRLF) | OR-Tools entra em `requirements.txt` |
| Router `/delivery` | Router registrado em `app/main.py:285`; as rotas aparecem **duas vezes** (`/delivery/...` e `/api/v1/delivery/...`) — 536 paths no OpenAPI | Nada a fazer; só não se assustar com a duplicação |

**Nota de introspecção:** `app.routes` lista `_IncludedRouter` (include lazy), não `APIRoute`. Para conferir rotas, usar `app.openapi()["paths"]` ou o `TestClient` — nunca `app.routes`.

**Modelo já disponível e não aproveitado:** `RouteStopRecord` (`app/infrastructure/repositories/route_model.py:36`) com coluna `sequence` e `RouteRepository.add_stop/get_stops` (`route_repository.py:83`, `:102`), ligado por `DeliveryRecord.route_id`. **Decisão travada:** a ordem otimizada é **efêmera** (só evento) — não usar esse modelo nesta tarefa.

---

## 3. Decisões travadas na entrevista

| # | Assunto | Decisão |
|---|---|---|
| 1 | Nome `RoutingProvider` | **Dois homônimos** (como o prompt): novo ABC em `app/domain/routing/provider.py`, docstring cruzada com o da FASE 14 |
| 2 | Ordem otimizada | **Efêmera** — só `route.optimized` no barramento, nada persistido em `route_id`/`RouteStopRecord` |
| 3 | Permissão do `/route/optimize` | **Operador + admin** (`get_tenant_context`), coerente com `/dispatch/suggest` |
| 4 | APK | **Reconstruir o release assinado** no final |
| 5 | Packaging do OR-Tools | **`requirements.txt` + `excludes=["ortools"]` no `gasflow-backend.spec`** — "não deixar nada quebrado": CI/backend web otimiza de verdade, exe desktop não arrasta protobuf/pandas (~200 MB) e cai no fallback |
| 6 | `dispatch.scored` | **Publicar**, mas só onde há decisão real (fluxo de sugestão com a flag ligada) — **não** no `GET /dispatch/candidates` (diagnóstico read-only) |
| 7 | Denominador do `load` | **Não misturar unidades**: entregas concorrentes (`DISPATCH_LOAD_FULL_DELIVERIES`, default 4), configurável por env |
| 8 | `vehicle_fit` | **Fora do score** — o encaixe de carga já é gate de elegibilidade (`filter_candidate` + estoque); pontuar de novo contaria a mesma coisa duas vezes |
| 9 | Commits | **Por bloco**: Parte 1 / Fase 8 / Fase 9 / Fase 10 (4 commits) |
| 10 | Gatilho da otimização | **Automático na atribuição**, **best-effort** e não bloqueante |
| 11 | Onde vive o gatilho | Função na **camada de aplicação** (`app/application/routing/`), chamada pelo endpoint de assign (o HTTP não conhece a regra) |
| 12 | Evento sem ganho | **Publicar sempre** que o fluxo roda com ≥1 entrega (payload traz `improvement_km` e `changed`), alinhado ao teste do prompt |
| 13 | App ao receber o evento | **Reordenar os ids conhecidos + refetch** do resto |
| 14 | Polyline da sequência | No **`DriverMap` do `DeliveriesPage`** (mapa que já existe) |
| 15 | Docs das flags | **README.md + backend/docs/OPERATIONS.md + CHANGELOG** |
| 16 | `docker-compose.osrm.yml` | **Entra no repo** como arquivo opt-in documentado (não roda no CI) |
| 17 | Subir OSRM aqui | **Nunca** — Fase 10 é deploy: testes mockam o HTTP, deploy documentado |
| 18 | Bugs fora do escopo encontrados | **Corrigir e reportar** no fim (com teste, se for bloqueante ou bug real de produção) |
| 19 | Verificação final | **Suítes completas** backend + frontend + mobile antes do último commit |
| 20 | Relatório final | **Tabela de verificação por fase + evidências** (`arquivo:linha` onde fizer diferença) |

---

## 4. Parte 1 — Os 6 fixes (implementados, faltam as verificações)

### 4.1 Fix 1 + 4 — Migration `f3a9c1e7d204` (`down_revision = e7b1c3d5f9a2`)
- `delivery_drivers.tracking_epoch` (Integer, not null, server_default `"0"`).
- Tabela `tracking_alert_state` (`id`, `tenant_id`, `driver_id`, `kind`, `last_sent_at`) com `UniqueConstraint uq_tracking_alert_state` sobre tenant+driver+kind.
- ORM `TrackingAlertStateRecord` em `delivery_persistence_model.py`.
- **Pendente:** aplicar e reverter a migration (up/down) — SQLite é o alvo dos testes do repo.

### 4.2 Fix 1 + 2 — `TrackingAlertsService` com cooldown e gate
- Cooldown `(tenant_id, driver_id, kind)` de 15 min (`ALERT_COOLDOWN_MINUTES`); reset quando o entregador volta a andar (> 200 m, `STALLED_RESET_MOVE_M`).
- `STALLED` só com entrega ativa; `DEVIATED` só com `status == "EN_ROUTE"` **E** a menos de 3 km do destino (`DEVIATION_PROXIMITY_KM`) **E** acima de 1,2 km (`DEVIATION_KM`).
- Estado persistido em `tracking_alert_state` (sobrevive a restart); publica `EventType.DRIVER_ALERT` uma vez por lote.
- Testes em `tests/test_tracking_alerts.py` (reescrito): não realerta no cooldown, realerta depois, reset ao voltar a andar, não acusa desvio fora de `EN_ROUTE`, não acusa desvio longe do destino, sem entrega ativa → nenhum alerta.

### 4.3 Fix 3 + 4 — Link público com teto de TTL e revogação por epoch
- `MAX_TTL_S = 86400`; `Query(6*3600, gt=0, le=MAX_TTL_S)` → **422** acima do teto.
- `issue_public_tracking_token` embute `e` (epoch do driver); `verify_public_tracking_token` devolve o `e`.
- `public_snapshot` compara `e` com `delivery_drivers.tracking_epoch` → **410 Gone** ("link revogado").
- `POST /public/tracking/revoke/{driver_id}` (ADMIN) incrementa `tracking_epoch` → `{revoked: True, epoch: N}`.
- Testes: TTL acima do teto → 422; revogação invalida (200 → 410); link de outro tenant nunca vaza posição.

### 4.4 Fix 5 + 6 — `DriverMap`: origem da linha e rótulo honesto
- Origem da linha tracejada = **última** posição da janela (`valid[valid.length - 1]`), não a primeira.
- `MapDestination` propaga `speed_source`; quando `"default"`, o rótulo ganha `~` (ex.: `~12 min`).
- **Pendente:** varredura final para garantir que nenhum outro ponto usa `valid[0]`.

---

## 5. Parte 2 — Arquitetura

### 5.1 Contrato de roteamento (implementado)

`app/domain/routing/provider.py`:
- `Point = tuple[float, float]` (lat, lng).
- `RouteLeg(distance_km, duration_s, geometry: list[Point] | None)`.
- `RoutingProvider` (ABC) com `name`, `distance_matrix`, `duration_matrix`, `route(origin, destination, waypoints=())`.
- **Contrato forte:** toda implementação é *total* — nunca levanta exceção para o chamador. Provedor é otimização, não caminho crítico.

Derivação: `__init__.py` exporta `Point`, `RouteLeg`, `RoutingProvider`.

### 5.2 Implementações

`app/infrastructure/routing/haversine_provider.py` — **default, zero infra**:
- `HaversineRoutingProvider(speed_kmh=None)`; velocidade default de `settings.routing_default_speed_kmh` (28 km/h, mesmo valor do fallback do ETA).
- Distância **linha reta** via `_haversine_km` (`app/domain/delivery/driver.py`). **Sem** fator de sinuosidade inventado: a docstring diz que é otimista em relação à malha viária, e é exatamente por isso que o OSRM existe.
- `route()` devolve `geometry` só quando há waypoints (a própria sequência); sem waypoints, `None`.

`app/infrastructure/routing/circuit_breaker.py` — `CircuitBreaker(failure_threshold, cooldown_s, clock=time.monotonic)`, thread-safe, estados closed/open/half-open:
- `allow()` deixa passar **uma** sondagem depois do cooldown;
- `record_success()` fecha; `record_failure()` durante a sondagem **reabre sem esperar o limiar** (evita martelar o serviço caído a cada request).

`app/infrastructure/routing/osrm_provider.py` — **opt-in**:
- `/table/v1/driving/...?annotations=distances|durations` (metros → km; segundos) e `/route/v1/driving/...?overview=full&geometries=geojson&steps=false` (GeoJSON `[lng,lat]` → `(lat,lng)` do domínio).
- Timeout curto (`settings.osrm_timeout_seconds`, 2 s); **fallback transparente** para haversine em qualquer falha, timeout ou breaker aberto; `logger.warning` na primeira falha que abre o breaker, `debug` depois; cliente HTTP injetável para os testes (sem rede).
- Uma tabela por chamada de matriz; o otimizador chama as duas matrizes **uma vez** cada (2 requests por otimização, não 5).

`app/infrastructure/routing/factory.py` — `get_routing_provider()`:
- `osrm` **e** `osrm_base_url` → `OsrmRoutingProvider`; senão haversine.
- Env `ROUTING_PROVIDER=osrm` sem URL → log `WARNING` e haversine (env incompleta não derruba o boot).

### 5.3 Fase 8 — `app/application/routing/optimizer.py`

- `OptimizedRoute(ordered_delivery_ids, total_distance_km, total_duration_s, geometry, improvement_km, provider)`.
- `DeliveryRouteOptimizer(provider).optimize(*, origin, deliveries, return_to_origin=False)`.
- OR-Tools `RoutingModel` (1 veículo), custo em **metros inteiros**, `PATH_CHEAPEST_ARC` + `GUIDED_LOCAL_SEARCH`, `time_limit` de 1 s.
- Rota **aberta** modelada com **nó final fictício de custo zero** (jeito padrão de "terminar em qualquer lugar" no OR-Tools); `return_to_origin=True` usa início=fim na origem.
- Regras:
  - 0 entregas → resultado vazio; 1 entrega → devolve como está, `improvement_km = 0`;
  - **sem OR-Tools** → ordem original, `provider = "fallback"` (solução parcial do solver também cai aqui: ordem parcial não é ordem);
  - ganho ≤ 0 ou < **5%** (`MIN_IMPROVEMENT_RATIO`) → mantém a ordem de atribuição e `improvement_km = 0`;
  - `improvement_km` **nunca** negativo.
- `geometry` = polyline da sequência final (`[origem, ...pontos]` + origem se fechada).

### 5.4 Fase 8 — endpoint, evento e gatilho

`POST /delivery/route/optimize` (`delivery_ops.py`, `get_tenant_context`):

| Caso | Resposta |
|---|---|
| flag `DELIVERY_SMART_ROUTING_ENABLED=false` | **409** (não silenciar) |
| entregador inexistente/inativo no tenant | **404** |
| entrega inexistente ou de outro tenant | **404** (o filtro de tenant é do repositório — não vaza existência) |
| entregador sem posição conhecida | **422** |
| entrega sem coordenadas | **422** |
| lista vazia | **422** |
| sucesso | **200** `{driver_id, ordered_delivery_ids, total_distance_km, total_duration_s, improvement_km, provider, geometry}` |

Origem da rota = última posição do **histórico**; se não houver, o upsert de `driver_locations`.

Evento: `EventType.ROUTE_OPTIMIZED = "route.optimized"` no barramento existente, via `publish_driver_event` com `data.driver_id` — o `_route_event` (`app/infrastructure/realtime/websocket.py:124`) entrega em `tenant:{id}` (regra 1) e `driver:{id}` (regra 3, por `data.driver_id`). **Nenhuma mudança no roteador de eventos é necessária**; publicar com `data.driver_id` já basta.

**Gatilho automático (decisão 10–12):** função na camada de aplicação (ex.: `optimize_driver_route_after_assignment(db, tenant_id, driver_id)`) chamada **best-effort** logo depois de `del_repo.assign_delivery(...)` no endpoint de assign (`delivery_ops.py:177`), com `try/except` + `logger.debug` — no padrão de `_evaluate_alerts` (`app/application/delivery/driver_location_service.py`). Nunca atrasa nem derruba a confirmação da atribuição. Publica o evento quando o fluxo roda com ≥1 entrega (payload com `improvement_km` e `changed`).

### 5.5 Fase 9 — `app/application/dispatch/scorer.py`

`DispatchScorer(db, tenant_id, provider=None, now=None)`; `score(*, delivery_id, candidate_driver_ids=None) -> list[DispatchScore]` (melhor primeiro, desempate determinístico por `driver_id`).

`DispatchScore(driver_id, driver_name, total, breakdown, reasons, distance_km, active_deliveries, position_age_s, has_recent_position)`.

Componentes e constantes:
| Componente | Cálculo | Constante |
|---|---|---|
| `proximity` | `max(0, 100 − km × 20)` via `RoutingProvider`; posição velha → `× 0,85`; sem posição → 0 | `PROXIMITY_KM_SATURATION = 20`, `STALE_POSITION_MINUTES = 15`, `STALE_POSITION_FACTOR = 0.85` |
| `load` | `max(0, 100 × (1 − ativas / 4))` | `DISPATCH_LOAD_FULL_DELIVERIES` (env, default 4) |
| `deadline` | sem `scheduled_at` → 100 (neutro); senão `slack = (scheduled_at − now) − ETA`; atraso zera a 10 min | `DEADLINE_PENALTY_PER_MINUTE = 10` |
| `fairness` | `max(0, 100 − atribuídas_na_janela × 20)` | `FAIRNESS_WINDOW_HOURS = 4`, `FAIRNESS_PENALTY_PER_DELIVERY = 20` |

- Pesos por env (`DISPATCH_WEIGHT_*`), **rebalanceados** na hora do score (soma 0 → default + `logger.warning`). Defaults: proximidade 0,45 / load 0,25 / prazo 0,20 / fairness 0,10.
- `total` calculado sobre os componentes **já arredondados** → o breakdown bate com o total por construção.
- Posição: **última do histórico** (`SQLAlchemyDriverLocationRepository.latest_history_point`, nova), com queda para o upsert de `driver_locations`; dado velho penaliza a proximidade (documentado).
- Entregador inativo ou inexistente no tenant é **ausente do resultado** (inelegível ≠ pior colocado).
- `vehicle_fit` **fora** (decisão 8).

Integração (`delivery_ops.py`, em `/dispatch/suggest`): com a flag ligada, o ranking vem do `DispatchScorer`, mas o **gate continua o mesmo** — `filter_candidate` decide quem pode receber (capacidade física não se negocia por ponto). A resposta mantém o formato atual (`success`, `order_id`, `total_candidates`, `eligible`, `rejected_count`, `rejected`, `recommendations[{driver_id, driver_name, vehicle_id, vehicle_plate, score, distance_km, capacity_fit, explanation}]`) + `source: "dispatch-scorer"`. Flag desligada → código de hoje, **linha por linha inalterado**.

Novo `GET /delivery/dispatch/candidates/{delivery_id}` (`get_tenant_context`): **409** com a flag desligada; **404** entrega inexistente; 200 `{candidates: [{driver_id, driver_name, total, breakdown, reasons, distance_km, active_deliveries, has_recent_position}]}`. Read-only, **sem** publicar evento (decisão 6).

Insumo novo no repositório: `count_assigned_since(driver_id, since)` (conta por `assigned_at`, não `created_at`).

### 5.6 Fase 10 — documentação e compose

- `docs/routing/osrm.md`: OSRM (BSD-2-Clause) via Docker; extrato do Geofabrik (OSM, ODbL); pipeline `osrm-extract` → `osrm-partition` → `osrm-customize` → `osrm-routed`; perfil `car.lua` (moto usa o mesmo, ajustando velocidade média); recursos (~50 GB disco, ~16 GB RAM, horas de pré-processamento); endpoints esperados; ativação por env.
- `docker-compose.osrm.yml` no repo, **opt-in, não roda no CI**, como documentação executável do deploy.
- Sem OSRM, tudo continua em haversine — nenhuma fase anterior depende dele.

---

## 6. App do entregador (`mobile/`)

- `attachDriverSocket({ onEvent })` (`src/logic/realtime.ts:40`) já entrega eventos; a lista vive em estado em `src/containers/wired.tsx` (`deliveries` em `:395`, carregada em `:407`).
- Ao receber `route.optimized`: aplicar a ordem aos ids **conhecidos**, manter os desconhecidos no fim e **disparar refetch** de `/driver/deliveries` para completar (decisão 13). Nunca perder entrega da tela por causa de evento.
- Não abrir um segundo socket; não mexer no gate de `must_change_password`.
- APK: `versionCode`/`versionName` **subindo** (decisão 4 + resposta da rodada 4), reconstruir o release assinado ao final.

## 7. Painel web (`frontend/`)

- `DeliveriesPage` já tem `DriverMap`, `useTrackingSocket` (canal `tenant:{id}`) e `useDeliveryEta` (`src/features/deliveries/DeliveriesPage.tsx:108`, `:145`, `:329`).
- Desenhar no mesmo mapa a **polyline da sequência otimizada** do entregador selecionado, numerada (decisão 14). Leaflet + OSM (BSD-2, sem API key) — manter; **não** trocar por MapLibre.
- Sem botão de otimizar: o gatilho é automático no backend (decisão 10).
- Reaproveitar a dedupe/ordenação já existente em `frontend/src/lib/tracking.ts`.

---

## 8. Flags e defaults (documentar em README.md + OPERATIONS.md)

| Env | Default | Efeito |
|---|---|---|
| `DELIVERY_SMART_ROUTING_ENABLED` | `false` | Liga Fase 8 (endpoint + gatilho automático na atribuição) |
| `DELIVERY_SMART_DISPATCH_ENABLED` | `false` | Liga Fase 9 (scorer no `/dispatch/suggest` + preview) |
| `ROUTING_PROVIDER` | `haversine` | `haversine` \| `osrm` |
| `OSRM_BASE_URL` | `""` | Ex.: `http://osrm:5000` |
| `OSRM_TIMEOUT_SECONDS` | `2` | Timeout curto por request |
| `OSRM_BREAKER_FAILURES` | `3` | Falhas seguidas para abrir o breaker |
| `OSRM_BREAKER_COOLDOWN_S` | `60` | Janela do breaker antes da sondagem |
| `ROUTING_DEFAULT_SPEED_KMH` | `28` | Velocidade assumida sem provedor real |
| `DISPATCH_WEIGHT_PROXIMITY` | `0.45` | Peso do componente |
| `DISPATCH_WEIGHT_LOAD` | `0.25` | Peso do componente |
| `DISPATCH_WEIGHT_DEADLINE` | `0.20` | Peso do componente |
| `DISPATCH_WEIGHT_FAIRNESS` | `0.10` | Peso do componente |
| `DISPATCH_LOAD_FULL_DELIVERIES` | `4` | **A adicionar** — entregas concorrentes que "enchem" o entregador |

## 9. Dependências e empacotamento

- `ortools` em `backend/requirements.txt` (Apache-2.0, self-hosted, sem conta/limite) com comentário explicando o import opcional.
- `gasflow-backend.spec`: `excludes=["ortools"]` com comentário — o exe desktop serve um PC único e o import opcional cai na ordem de atribuição. **Não quebrar o `release.yml`.**
- Import do OR-Tools sempre dentro de `try/except ImportError`.
- Nenhuma dependência paga. Sem Docker/OSRM no CI.

---

## 10. Testes a escrever

**Fase 8** (`tests/` novos): reordena com ganho real (4 pontos em zigue-zague); mantém a ordem sem ganho (`improvement_km == 0`); fallback sem OR-Tools (mock de `ImportError` → ordem original + `provider="fallback"`); fallback de provider (OSRM offline → haversine); escopo de tenant (entregas de outro tenant → 404, nunca vazam); flag desligada → 409; evento publicado com `ordered_delivery_ids` (assinante fake); `improvement_km >= 0`; rota fechada vs. aberta.

**Fase 9**: perto ganha de longe (demais fatores iguais); sobrecarregado perde para livre mesmo sendo mais perto; prazo apertado penaliza; fairness penaliza quem recebeu muito na janela; sem histórico recente → penalidade pequena e documentada; breakdown bate com o total; **regressão com a flag desligada** (mesma saída do motor atual); flag desligada → 409 no preview.

**Fase 10**: mock do OSRM (HTTP fake) → matrizes no formato esperado e `provider="osrm"`; OSRM offline → fallback transparente com resposta 200 e `provider="haversine"`; timeout → mesmo comportamento; breaker abre e fecha (incluindo sondagem half-open que falha reabre); consistência de ordem de magnitude entre OSRM mockado e haversine.

**Parte 1**: suite de alertas e link público (já escritas) + migration up/down.

Nenhum teste depende de rede, device ou tile real.

## 11. Verificação final (antes do último commit)

1. Migration `f3a9c1e7d204`: aplicar e reverter.
2. **Suítes completas**: backend (pytest), frontend (`vitest run`, `tsc -b`, ESLint), mobile (`npm test`, typecheck).
3. `ruff check`, `ruff format --check`, `mypy` nos arquivos tocados.
4. Conferir rotas via `app.openapi()["paths"]` (não `app.routes`).
5. APK release assinado reconstruído + assinatura conferida (`apksigner`), cópia no repo (gitignored).
6. `git diff --cached --name-only | grep -iE "keystore|\.apk$|secret"` → vazio antes de commitar.

## 12. Commits (4, por bloco)

1. `fix(tracking)` — Parte 1: cooldown/gate dos alertas, teto de TTL + revogação por epoch, origem e rótulo do ETA no mapa (migration `f3a9c1e7d204` inclusa).
2. `feat(routing)` — Fase 8: interface de roteamento, otimizador OR-Tools, endpoint, evento, gatilho na atribuição, reordenação no app, polyline no painel.
3. `feat(dispatch)` — Fase 9: `DispatchScorer`, integração atrás da flag, endpoint de preview, `dispatch.scored`.
4. `feat(routing): OSRM opt-in` — Fase 10: provider OSRM + breaker, `docs/routing/osrm.md`, `docker-compose.osrm.yml`, flags no README/OPERATIONS, CHANGELOG, APK.

Cada commit com o rodapé `Generated with Codebuff 🤖` + `Co-Authored-By: Codebuff <noreply@codebuff.com>`. Nada de `git push` sem pedido explícito.

## 13. Fora de escopo

- Persistir a ordem otimizada (`RouteStopRecord.sequence`) — decisão 2.
- Migrar ações de entrega para novos namespaces.
- Recriar identidade/hub/cliente paralelo; alterar o gate `must_change_password`.
- Publicar na Play Store; hospedar/subir OSRM; rodar OSRM no CI.
- Reescrever o `DispatchEngine` legado (só delegação atrás de flag).
- Trocar Leaflet por MapLibre.

## 14. Riscos e como são contidos

| Risco | Contenção |
|---|---|
| OR-Tools indisponível no ambiente de build | Import opcional + fallback `provider="fallback"` (testado com mock de `ImportError`) |
| OR-Tools engordar/quebrar o exe desktop | `excludes` no spec; CI e backend web intactos |
| Duas classes `RoutingProvider` confundirem leitura | Docstrings cruzadas nos dois módulos + registro no CHANGELOG |
| Scorer com o flag ligado mudar o contrato do `/dispatch/suggest` | Mesmo formato de resposta (`recommendations[...]`) + `source` |
| Gatilho automático atrasar/derrubar a atribuição | Best-effort, `try/except`, teto de 1 s no solver, depois do `assign_delivery` |
| Blast radius do `excludes`/flags em produção | Todas as flags default `false`/`haversine` = comportamento pré-fase |
