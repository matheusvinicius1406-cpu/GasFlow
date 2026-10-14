# OSRM self-hosted — roteamento por malha viária (Fase 10)

> **Status:** implementado e atrás de flag. **Opt-in** — o sistema inteiro
> funciona sem nenhuma infra extra. O OSRM só troca precisão; nenhum caminho
> de código pode *exigir* um provedor de malha viária.
>
> **Licenças:** OSRM backend **BSD-2-Clause** · dados OSM **ODbL** (Geofabrik)
> · perfil `car.lua` do próprio projeto. Nenhuma API key, nenhum serviço pago.

---

## 1. O que muda quando liga

| | `haversine` (default) | `osrm` (opt-in) |
|---|---|---|
| Distância | linha reta | malha viária real |
| Velocidade | `ROUTING_DEFAULT_SPEED_KMH` (28 km/h) | duração real do OSRM |
| Infra | nenhuma | container self-hosted |
| Fallback | — | **haversine**, transparente |

O haversine é **otimista** em relação à malha viária — é exatamente por isso
que o OSRM existe. Sem ele, o otimizador (Fase 8) e o scorer de despacho
(Fase 9) continuam funcionando; apenas ordenam pior.

---

## 2. Contrato

`app/domain/routing/provider.py` — dois homônimos no repo, não confundir:

- **Este** `RoutingProvider` (Fase 8–10) — matriz **NxN** para sequenciamento
  e score. Vivo em `app/application/routing/optimizer.py` e
  `app/application/dispatch/scorer.py`.
- O `RoutingProvider` de `app/domain/delivery/routing.py` (FASE 14) —
  point-to-point `geocode`/`calculate_route`/`estimate_eta` do fluxo de
  pedido. Não tem matriz e não é afetado por este doc.

Toda implementação é **total**: nunca levanta exceção para o chamador.

```python
Point = tuple[float, float]          # (latitude, longitude)
RouteLeg(distance_km, duration_s, geometry: list[Point] | None)
```

`geometry=None` é legítimo — devolver `None` é mais honesto que inventar uma
polyline de malha.

---

## 3. Deploy

### 3.1 Extrato do OSM

Baixar o recorte em <https://download.geofabrik.de> (ex.: `brazil-latest.osm.pbf`)
e colocar em `./data/` (raiz do repo, a mesma pasta que o compose monta em `/data`).

> **Recurso estimado (Brasil inteiro):** ~50 GB de disco para o `.pbf` + artefatos
> MLD, ~16 GB de RAM no `osrm-routed`, e **horas** de pré-processamento.
> Para desenvolvimento use um estado/cidade — o pipeline é o mesmo.

### 3.2 Pipeline MLD

O `docker-compose.osrm.yml` roda `--algorithm mld`, então o extrato precisa
passar pelas quatro etapas, na ordem:

```bash
docker run -v "$PWD/data:/data" ghcr.io/project-osrm/osrm-backend:latest \
  osrm-extract   -p /opt/car.lua /data/brazil-latest.osm.pbf

docker run -v "$PWD/data:/data" ghcr.io/project-osrm/osrm-backend:latest \
  osrm-partition /data/brazil-latest.osrm

docker run -v "$PWD/data:/data" ghcr.io/project-osrm/osrm-backend:latest \
  osrm-customize /data/brazil-latest.osrm
```

O perfil `car.lua` é o do projeto. Moto usa o **mesmo** perfil ajustando a
velocidade média — não criar perfil separado sem decisão registrada aqui.

### 3.3 Subir o serviço

```bash
docker compose -f docker-compose.osrm.yml up -d
```

| | |
|---|---|
| Imagem | `ghcr.io/project-osrm/osrm-backend:latest` |
| Porta | `5000` |
| Volume | `./data:/data` → `/data/brazil-latest.osrm` |
| Healthcheck | `GET /health/v1/status` a cada 30 s |
| Limites | 16 GB RAM, 4 CPUs |
| **CI** | **não roda** — opt-in, documentação executável de deploy |

### 3.4 Ativar no backend

```bash
ROUTING_PROVIDER=osrm
OSRM_BASE_URL=http://osrm:5000      # dentro do compose
# OSRM_BASE_URL=http://localhost:5000   # dev local
```

**Env incompleta não derruba o boot** (`app/infrastructure/routing/factory.py`):
`ROUTING_PROVIDER=osrm` sem `OSRM_BASE_URL` loga
`routing.osrm_sem_base_url` em WARNING e cai no haversine.

O import de `osrm_provider` é **tardio** — sem a env ligada o módulo (e o
`httpx`) nem é carregado.

---

## 4. Endpoints consumidos

| Chamada | Uso | Conversão |
|---|---|---|
| `GET /table/v1/driving/{coords}?annotations=distances` | `distance_matrix` | metros → **km** |
| `GET /table/v1/driving/{coords}?annotations=durations` | `duration_matrix` | segundos (int) |
| `GET /route/v1/driving/{coords}?overview=full&geometries=geojson&steps=false` | `route` | `[lng,lat]` → `(lat,lng)` do domínio |

**Coordenadas no OSRM são `longitude,latitude`** — o inverso do `Point` do
domínio (`lat, lng`). Toda a conversão está em `OsrmRoutingProvider._coords`
e no parser de `geometry`; não espalhar inversão por mais lugar nenhum.

O otimizador chama **uma vez** cada matriz por otimização: **2 requests**,
não N².

---

## 5. Sempre cai para o haversine

`OsrmRoutingProvider._guard` envolve toda chamada HTTP. Retorna `None`
(indisponível) e o método correspondente delega ao fallback quando:

- o **breaker** está aberto (nem tenta);
- HTTP falha, estoura timeout ou devolve status de erro;
- o payload vem fora do formato (`code != "Ok"`, `routes` vazio, sem a
  anotação pedida).

Nenhum desses caminhos propaga exceção para o chamador.

### Circuit breaker

`app/infrastructure/routing/circuit_breaker.py` — thread-safe, estados
`closed` → `open` → `half-open`:

1. `OSRM_BREAKER_FAILURES` falhas seguidas → **abre**.
2. Enquanto aberto, `allow()` é `False` → chamadas vão direto ao haversine,
   sem pagar timeout.
3. Depois de `OSRM_BREAKER_COOLDOWN_S`, `allow()` deixa passar **uma** sondagem.
4. Sondagem com sucesso → **fecha**. Sondagem com falha → **reabre na hora**,
   sem esperar o limiar (evita martelar o serviço caído a cada request).

Log: `WARNING` só na transição que abre o breaker
(`osrm.unavailable`); depois é `DEBUG`.

---

## 6. Variáveis

| Env | Default | Efeito |
|---|---|---|
| `ROUTING_PROVIDER` | `haversine` | `haversine` \| `osrm` |
| `OSRM_BASE_URL` | `""` | ex.: `http://osrm:5000` |
| `OSRM_TIMEOUT_SECONDS` | `2` | timeout por request (curto de propósito) |
| `OSRM_BREAKER_FAILURES` | `3` | falhas seguidas para abrir o breaker |
| `OSRM_BREAKER_COOLDOWN_S` | `60` | janela antes da sondagem |
| `ROUTING_DEFAULT_SPEED_KMH` | `28` | velocidade sem malha; mesmo valor do fallback do ETA (Fase 7.1) |
| `DELIVERY_SMART_ROUTING_ENABLED` | `false` | Fase 8 — `POST /delivery/route/optimize` + gatilho automático na atribuição |
| `DELIVERY_SMART_DISPATCH_ENABLED` | `false` | Fase 9 — `DispatchScorer` no `/dispatch/suggest` |
| `DISPATCH_WEIGHT_PROXIMITY` | `0.45` | peso do score |
| `DISPATCH_WEIGHT_LOAD` | `0.25` | idem |
| `DISPATCH_WEIGHT_DEADLINE` | `0.20` | idem |
| `DISPATCH_WEIGHT_FAIRNESS` | `0.10` | idem |
| `DISPATCH_LOAD_FULL_DELIVERIES` | `4` | entregas concorrentes que "enchem" o entregador |

As flags são **independentes**: ligar OSRM não liga a Fase 8 nem a 9. Cada uma
liga/desliga sem quebrar o comportamento anterior; desligada, o endpoint
responde **409** em vez de silenciar.

---

## 7. Testes

`tests/test_routing_optimizer.py`, `tests/test_osrm_provider.py` e
`tests/test_dispatch_scorer.py` mockam o HTTP — **nenhum teste depende de
rede, de container ou de tile real**:

- OSRM mockado → matrizes no formato esperado, `provider="osrm"`;
- OSRM offline / timeout / breaker aberto → resposta 200 com
  `provider="haversine"`, fallback transparente;
- breaker abre e fecha, incluindo a sondagem half-open que falha e reabre.

Para validar o deploy de verdade, suba o container e rode
`GET /table/v1/driving/-48.5,-1.45;-48.5,-1.46?annotations=distances`
— deve devolver `code: "Ok"` e uma matriz 2×2.

---

## 8. Fora de escopo

- Subir OSRM no CI ou no workflow de release.
- Hospedar OSRM como serviço gerenciado (contraria a regra travada em
  `catalogo-apis-externas.md`: sem chave comercial/trial).
- Trocar Leaflet por MapLibre no painel.
- Trocar o perfil `car.lua` por um específico de moto sem registro nesta página.
