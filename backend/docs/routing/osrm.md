# OSRM Self-Hosted (Fase 10)

Provedor de roteamento real em malha viária, plugável ao GasFlow via env.

## Ativação

```bash
ROUTING_PROVIDER=osrm
OSRM_BASE_URL=http://osrm:5000
```

Sem essas envs, o sistema usa **haversine** (zero infra, em memória).

## O que muda

| Com haversine | Com OSRM |
|---|---|
| Distância em linha reta | Distância real em malha viária |
| Duração por velocidade média (28 km/h) | Duração baseada na malha |
| Sem polyline | Polyline com geometria real |
| Zero dependência | Requer container Docker |

**Nenhuma fase anterior depende de OSRM.** O sistema funciona 100% sem ele.

## Requisitos

| Recurso | Mínimo | Recomendado |
|---|---|---|
| Disco | 20 GB | 50 GB |
| RAM | 8 GB | 16 GB |
| CPU | 2 cores | 4+ cores |
| Tempo de pré-processamento | 1-2 horas | 4-8 horas |

## Pipeline de dados

1. **Extrair** dados do OpenStreetMap (Geofabrik, ODbL):
   ```bash
   # Download do extrato do Brasil
   wget https://download.geofabrik.de/south-america/brazil-latest.osm.pbf

   # Extrair com perfil de carro
   osrm-extract -p /opt/car.lua brazil-latest.osm.pbf
   ```

2. **Particionar** para uso eficiente de memória:
   ```bash
   osrm-partition brazil-latest.osrm
   ```

3. **Customizar** as partições:
   ```bash
   osrm-customize brazil-latest.osrm
   ```

4. **Executar** o servidor:
   ```bash
   osrm-routed --algorithm mld brazil-latest.osrm
   ```

## Perfis

- **car.lua**: perfil padrão para veículos motorizados. Moto usa o mesmo perfil com ajuste de velocidade média no código.
- Perfis customizados podem ser criados em `/opt/osrm-profiles/`.

## Endpoints utilizados

| Endpoint | Uso no GasFlow |
|---|---|
| `GET /table/v1/driving/{coords}?annotations=distances,durations` | Matriz NxN de distância/duração |
| `GET /route/v1/driving/{coords}?overview=full&geometries=geojson` | Rota com geometria |

## Comportamento de fallback

O `OsrmRoutingProvider` é **total**: nunca levanta exceção para o chamador.

- **Timeout** (2s por request): fallback transparente para haversine.
- **Circuit breaker**: após 3 falhas seguidas, fica de fora por 60s (configurável).
- **OSRM offline**: mesma resposta, `provider="haversine"` no payload.

## Docker Comploy

O arquivo `docker-compose.osrm.yml` na raiz do repo documenta o deploy:

```bash
# Só para documentação — não roda no CI
docker compose -f docker-compose.osrm.yml up -d
```

## Segurança

- O OSRM é **self-hosted**, sem conta, sem API key, sem limite de requisição.
- Dados do OpenStreetMap são ODbL (Open Database License).
- OSRM é BSD-2-Clause.
- Nenhum dado sai do servidor.

## Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| `provider="haversine"` no payload | OSRM offline ou breaker aberto | Verificar container: `docker ps` |
| Timeout nos requests | Dados muito grandes ou pouca RAM | Reduzir área coberta ou aumentar RAM |
| `routing.osrm_sem_base_url` no log | `OSRM_BASE_URL` não definida | Adicionar env: `OSRM_BASE_URL=http://osrm:5000` |
