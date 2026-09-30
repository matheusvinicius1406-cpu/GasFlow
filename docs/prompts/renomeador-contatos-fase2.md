# PROMPT — Renomeador Automático de Contatos (.vcf) · Fase 2 · REV. 7

> Documento único, auto-contido e **executável**. Estado: **etapas 1–9 executadas**
> (gates §10 verdes; UI do renomeador entregue; fallback de CEP em vigor; E2E de
> 10 mil medido — números em §18).

---

## 0. Como usar e regras de ouro

Entregue este documento inteiro ao agente. Ele deve ler o repo, **verificar** cada referência (`arquivo:linha`), corrigir o plano se divergir, executar **na ordem do §0.1 → §8 → §9**, e **não commitar/push** sem pedido.

- **Proibido**: Google Maps, Mapbox, HERE, qualquer API paga/com chave.
- **Não invente.** Toda afirmação técnica cita `arquivo:linha`.
- **Sem dependência Python nova** — HTTP via `httpx` + stdlib.
- **Sem Celery/RQ/`BackgroundTasks`** — padrão `bounded-batch` do repo.
- **Não declare feito o que não gravou** nem gate que não rodou.
- Se um gate reprovar, **conserte o código — nunca a allowlist** (19/0 é critério).
- Rótulo de revisão: **o cabeçalho vale a última linha da tabela** (§16).

## 0.1 Verificação de abertura (rodar ANTES de qualquer código)

```
cd backend
python -m alembic heads          # esperado: d4e8b2c6f1a3 (head), único
python -m tests.integrity_audit  # esperado: findings=19 pendentes=0
python -m pytest tests/test_contacts_geocoding.py -q
```

Se qualquer um divergir do esperado, **pare e reporte** — não corrija "de passagem".

**Resultado da abertura (2026-09-25):** `d4e8b2c6f1a3 (head)` ·
`findings=19 pendentes=0` · `41 passed` — os três batem, sem parar.

## 1. Estado verificado

| Item | Onde / valor |
|---|---|
| Migrations | head `d4e8b2c6f1a3` (v7 = `geocode_cache`) |
| `clients` | cep, entre_ruas, geocode_status, lat, lng, cidade, uf, nome_importado |
| Parser | `app/application/contacts/vcf.py` (folding, QP, `\;`, multi-TEL, número solto) |
| Import/export `.vcf` | `app/presentation/api/whatsapp/contacts.py` |
| Organizer | `app/application/contacts/organizer.py` (preview paginado, apply por filtro) |
| `ContactService` | `app/application/contacts/service.py` (`sync_batch` em blocos de 500) |
| Geocoding | `app/application/contacts/geocoding.py` (`GeocodingService`) |
| Providers | `app/infrastructure/geocoding/` (nominatim, photon, viacep, axis, factory) |
| Contrato de geocoding | `app/domain/delivery/routing.py` (`GeocodeResult`, `GeocodingProvider`) |
| Breaker | reusa `CircuitBreaker` de `app/infrastructure/routing/` |
| Config | `app/core/config.py` (GEOCODING_*, VIACEP_*, ENTRE_RUAS_RADIUS_M=150, CONTACT_RENAMER_ENABLED=false) |
| Auditoria | `integrity_audit` = **19 findings / 0 pendentes** (`dado-invisivel`: 9 · `whatsapp-sem-consumidor`: 10) |
| Registrar models | imports `# noqa: F401` em `init_db.py` |
| `tenant_id` | `Column(String, default="default", index=True)` — string solta, sem FK |

**Regra do guard:** `_app_source_without_models()` **exclui `repositories/` e `init_db.py`**. Tabela nova exige consumidor em `application/` ou `presentation/`.

## 2. Decisões travadas

| # | Decisão |
|---|---|
| D1 | Código = CRM (global por tenant, imutável). Alfabético só na lista |
| D2 | CEP/"entre ruas" não bloqueiam: sem dado → vazio + triagem. **Nunca inventar** |
| D3 | `geocode_status` ∈ `OK` \| `NAO_ENCONTRADO` \| `PENDENTE`. Cadastro nunca é perdido |
| D4 | 10.000/arquivo normal · 20.000 pico |
| D5 | `{codigo}= {rua} Nº {numero} entre {A} e {B} - CEP {cep} ({nome})`, com fallbacks |
| D6 | `.vcf` não persistido (hash sha256 + contagem) |
| D7 | `CODIGO_PADDING=0` (`1=`); DB segue 6 dígitos |
| D8 | Geocoding default = Nominatim público + cache; Photon self-host na §4.2 |
| D9 | "Entre ruas" = Overpass-only na Fase 2; PostGIS na Fase 3 |
| D10 | Multi-TEL só no `import-vcf`; WhatsApp sync mantém 1 cliente/telefone |
| D11 | `contacts.default_city` / `contacts.default_uf` em `system_settings` |
| D12 | Cache **por rua**; "entre" derivado **por número** das interseções |
| D13 | `CONTACT_RENAMER_ENABLED=false` por default |
| **D14** | **Overpass FORA do geocode frio** (opção 2): passe próprio, job da etapa 8, UPDATE só de `intersecoes` |

## 3. Ferramentas open source

| Ferramenta | Função | Repositório | Licença |
|---|---|---|---|
| Nominatim | geocoding/reverse (default) | `github.com/osm-search/Nominatim` | GPLv2 |
| Photon | geocoding/reverse (self-host) | `github.com/komoot/photon` | Apache 2.0 |
| Overpass API | "entre ruas" | `github.com/drolbr/Overpass-API` | AGPL-3.0 |
| OSRM | rota/`nearest` (já no repo) | `github.com/Project-OSRM/osrm-backend` | BSD-2 |
| ViaCEP | CEP | `viacep.com.br` | MIT |
| Geofabrik | extrato OSM do Brasil | `download.geofabrik.de/.../brazil-latest.osm.pbf` | ODbL |
| PostGIS / osm2pgsql | geoespacial (Fase 3) | `github.com/postgis/postgis` · `github.com/osm2pgsql-dev/osm2pgsql` | GPLv2 |
| CNEFE/IBGE | endereços BR c/ coordenada (Fase 3) | `ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos...` | Público |
| vobject | referência (NÃO usar) | `github.com/py-vobject/vobject` | Apache 2.0 |

## 4. Escala — a aritmética correta

### 4.1 Geocode frio (D14: **sem** Overpass)

`frio ≈ nº de ruas distintas × 1 s` (+ até 1 s/rua onde o ViaCEP entrar; o cliente dele tem limitador próprio, então as séries **somam**). Retry soma +3 s na rua que falha. Breaker aberto (60 s) **reduz** o custo.

| Ruas | Piso do frio (modelo) |
|---|---|
| 500 | ~8 min |
| **~900** | **~15 min** ← alvo |
| 1.500 | ~25 min |

> **MEDIDO (REV. 8) — o modelo é piso, não previsão.** `tests/test_contacts_geocode_live.py`
> (`LIVE_MODE=true`, 5 ruas de Belém, 2026-09-29, **5 rodadas**): **4,76–4,81 s =
> ~0,95 s/rua** em quatro delas e **10,01 s = ~2,00 s/rua** numa quinta, quente a
> 0 requisição em todas. O que varia **não** é o ViaCEP: consultadas direto, as 5
> ruas **voltam com `postcode`** (é o mesmo campo que o §17.1 usa para achar o CEP
> do depósito), então o 2º elo nem é chamado. O que varia é a **latência**: o
> limitador marca o fim da chamada e dorme 1 s a partir dali, logo cada rua custa
> `1 s + latência` — ~1 s com rede boa, ~2 s com ~1 s de latência. Efeito: o alvo
> de 15 min vale para **~900 ruas** na rede boa e **~450** na lenta; o gatilho do
> Photon (§4.2) anda junto. Onde o OSM **não** trouxer `postcode`, o ViaCEP soma
> **+1 s** naquela rua (o parêntese acima).

### 4.2 Quando o Photon entra
Acima de **~900 ruas** (na rede lenta, **~450** — §4.1) o frio estoura 15 min → **`GEOCODING_PROVIDER=photon`** (D8), que não tem o teto de 1 req/s. É troca de config, não de código. O excedente, enquanto isso, vira triagem e o job retoma (etapa 8).

### 4.3 Passe Overpass (custo próprio, **não** entra no alvo de 15 min)
`passes ≈ nº de ruas alvo × (throttle + latência)`. Overpass público tem política de uso e **timeouts**; a query é pesada. Medir no spike (§8.0). Alvo próprio, contagem própria, retomada própria.

### 4.4 Alvos de engenharia

| Métrica | Alvo |
|---|---|
| Contatos/arquivo | 10.000 / 20.000 pico |
| `.vcf` | 3 MB / 16 MB pico |
| Upload+parse+upsert | < 2 min |
| Geocode frio | §4.1 |
| Apply | < 5 min |
| Bloco de upsert | 500/transação |
| Memória backend | < 512 MB |

## 5. Arquitetura

```
upload → parse → upsert (500/bloco) → [job geocode] → [job Overpass: intersecoes]
       → format → preview (paginado) → [job apply] → export
```

- `POST /whatsapp/contacts/jobs` · `POST .../jobs/{id}/process` (próximo lote) · `GET .../jobs/{id}` · `GET .../preview?page=&page_size=&filtro=`
- Padrão `bounded-batch` (igual a `POST /whatsapp-automation/process-pending`): cada request abaixo dos 30 s do nginx.
- Preview/apply desacoplados: **preview paginado**, **seleção por filtro**, **sem seleção → 422** (`all_matching=True` é o "todos" dito em voz alta).

## 6. Schema

| Versão | Conteúdo | Status |
|---|---|---|
| `a9c4e1b7d2f5` | `clients`: cep, entre_ruas, geocode_status, lat, lng | ✅ |
| `b3d7f1a5c9e2` | `clients`: cidade, uf, nome_importado | ✅ |
| `d4e8b2c6f1a3` (head) | `geocode_cache` (chave única, lat, lng, rua, bairro, cidade, uf, cep, provider, `intersecoes` JSON, criado_em) | ✅ |
| `e5c9f3a7b1d2` (head) | `contact_jobs` — job bounded-batch + cursor keyset (etapa 8) | ✅ |

> Migration v7 **ainda não rodou em Postgres** (só SQLite/testes).

## 7. Contratos congelados (não mudam depois)

| Contrato | Forma | Onde |
|---|---|---|
| `intersecoes` | `[{"nome": str, "numero": int}]` | cache + `escolher_entre_ruas` |
| `GeocodeResult` | lat, lng, rua, bairro, cidade, uf, cep, `intersecoes` | `domain/delivery/routing.py` |
| `chave_rua` | `sha256(normalize(rua\|bairro\|cidade\|uf))` | `application/contacts/geocoding.py` |
| `estimar_numero(posicao, ancoras)` | interpolação linear; `None` fora da faixa / <2 âncoras | `infrastructure/geocoding/axis.py` |
| Formatter | §D5 com fallbacks, idempotente (`^\d+\s*=\s*`) | etapa 7 |

**Testes que travam:** `TestContratoIntersecoes` (3) · `TestInterpolacaoDeAncoras` (7). Se a forma mudar, a etapa **não fecha**.

## 8. ETAPA 6 — Entre ruas (Overpass-only)

### 8.0 Spike de viabilidade — **antes de codar** (portão)

> ✅ **RESPONDIDO (REV. 7).** Resultado com números no ADR-0004 → *Resultado do
> spike T3/T4*; resumo em §17.2. Portão §8.0.3 **não disparou** (4/5 ruas com
> ≥2 âncoras úteis). Hipótese do caso de aceite **não se reproduziu** — ver §17.2.

~~⚠️ **Bloqueado pela pendência de cidade/UF (§12, item 1).**~~ — encerrado em REV. 7 (§17.1).

1. Escolher **5 ruas reais** da cidade do cliente, incluindo o caso conhecido (**Passagem Ivan Leão, 45** → esperado "entre Berredos e Andradas") — e 4 ruas comuns, de bairros diferentes.

   > **Verificado no repo (2026-09-25):** `"Ivan Le"` e `"Andradas"` **não
   > aparecem em nenhum arquivo** do repositório. O que existe é o literal de
   > teste do parser `1443= berredos 145` / `1= berredos Nº 145 entre Rua A e
   > Rua B - CEP 00000-000` (`app/application/contacts/vcf.py:11`). Ou seja: o
   > caso é **externo ao repo** (cadastro do cliente?) e precisa ser
   > **confirmado com quem o conhece** — senão o critério de aceite do spike é
   > inverificável.
   >
   > ✅ **Resolvido (REV. 7):** o endereço **é o depósito** (§17.1), confirmado
   > pelo cliente. O que faltava não era a existência do endereço e sim a
   > verificação do par — que **não se confirmou** no OSM (§17.2).

2. Rodar a query (§8.2) à mão (Overpass Turbo / `curl`) e responder, com números:
   - quantas das 5 têm **≥2 âncoras** `addr:housenumber`?
   - quantos cruzamentos nomeados cada uma tem?
   - a Ivan Leão reproduz o "entre Berredos e Andradas" esperado?
3. **Portão:** se a cobertura de âncoras for ~0, **pare e reporte** — a resposta honesta é (b) triagem (D2), e não construir pipeline que devolve vazio. O spike decide entre seguir e reavaliar (PostGIS/CNEFE, Fase 3).

Registrar o resultado do spike no ADR-0004 (números, não impressão).

> **Respostas do item 2 (REV. 7, medido):**
> - **≥2 âncoras:** **4 de 5** (34, 16, 19, 35 úteis). Só a Rodovia Augusto
>   Montenegro ficou em **0**.
> - **cruzamentos nomeados:** 6, 17, 16, 5, 22 por rua; com número estimável
>   3, 0, 16, 7, 27 respectivamente.
> - **a Ivan Leão reproduz?** **Não.** `escolher_entre_ruas(…, 45)` → `null`.
>   "Andradas" não é cruzamento da via; "Travessa dos Berredos" é, mas está
>   fora da faixa de âncoras. Ver §17.2 e ADR-0004.
> - **portão:** não disparou — há dado real, então segue.

### 8.1 Provider
`app/infrastructure/geocoding/overpass_provider.py`:
- **Uma query por rua** (§8.2), consumindo o `lat/lng` **já cacheado** (D14).
- Throttle conservador (política do Overpass público), timeout, retry, `User-Agent` — reusa `RateLimitedHttp` + `CircuitBreaker`.
- Devolve a `intersecoes` já no **contrato congelado**, ou `[]`.
- **`intersecoes` é o ÚNICO produto.** Não devolve lat/lng/cep e não os toca.

### 8.2 Query (forma base — a forma final é decisão da etapa 6, **com teste**)
```
[out:json][timeout:25];
way(around:80,LAT,LNG)["highway"]["name"]->.via;          // 1) o logradouro
way(around:ENTRE_RUAS_RADIUS_M,LAT,LNG)["highway"]["name"]->.cruza;  // 2) quem cruza
node(around:80,LAT,LNG)["addr:housenumber"];               // 3) as âncoras
out geom;
```
Bbox, tolerância e raio viram teste — não podem ser "achismo no código".

### 8.3 Conta local (uma vez por rua)
1. Projetar cada item na polilinha do logradouro → `posicao` 0..1. **Nó que projeta fora do eixo é descartado** (senão casa de via transversal vira âncora errada).
2. Âncoras = `(posicao, addr:housenumber)`.
3. **<2 âncoras ⇒ `intersecoes = []`** (fim).
4. Cada cruzamento → `estimar_numero(posicao, ancoras)` → `None` ⇒ **fora da lista** (nunca nulo, nunca aproximado).
5. Ordenar por `numero`; manter só o trecho **entre a 1ª e a última âncora**.
6. **<2 itens ⇒ `[]`**.

### 8.4 Passe de update (job, etapa 8 — regra já fixada)
- **UPDATE só da coluna `intersecoes`.** Nunca criar linha (criar com `lat/lng` nulos gravaria **negativo falso**), nunca tocar `lat/lng/cep/geocode_status`.
- Linha ausente no cache ⇒ **pula**.
- **Idempotente**: reexecutar só preenche `intersecoes` vazias.
- Falha no passe **não mexe em `geocode_status`**.
- Contagem e retomada **separadas** do geocode.

### 8.5 Métrica obrigatória (decide a viabilidade com dado)
Persistir, no resultado do job: **% de ruas com ≥2 âncoras** e **% com ≥2 cruzamentos**. Sem isso, "entre ruas" é opinião. O número entra no ADR.

### 8.6 Testes (§10 estendido)
- Query fake (Overpass) → interseções no contrato; item malformado ignorado.
- Projeção no eixo; nó fora do eixo descartado.
- `<2 âncoras ⇒ []` · `<2 cruzamentos ⇒ []` · cruzamento fora da faixa ⇒ fora.
- Só UPDATE de `intersecoes`; nada de INSERT; `lat/lng/cep/geocode_status` intactos.
- Idempotência (2ª passada não altera).
- Throttle/timeout/retry/breaker (mesmo padrão da etapa 5).

### 8.7 DoR / DoD da etapa 6
- **DoR:** spike respondido (§8.0) · cidade/UF definidos (§12, item 1) · contrato congelado verde.
- **DoD:** `intersecoes` preenchida só com âncora real · `[]` quando não há · UPDATE-only provado · métrica de âncoras persistida · gates §10 verdes · **nada commitado**.

### 8.8 Ajustes obrigatórios pós-spike (REV. 7 — saem do ADR-0004)

O spike (§8.0, números no ADR-0004) derrubou três suposições. Quem implementa
§8.1–§8.6 segue isto **junto** do texto original, não no lugar dele:

1. **A query de §8.2 não pode ir combinada.** Medido: uma única query com as
   três partes devolve **504** no `overpass-api.de`; **três queries separadas
   + retry passam**. A divisão (logradouro · cruzamentos · âncoras) é decisão
   da etapa 6 **com teste** — não é acidente de código.
2. **Validar `timestamp_osm_base`.** Instância planetária devolveu base de
   **4 meses atrás** sem erro HTTP. `osm.ch` não tem dado planetário. Quem não
   confere a data grava dado velho como se fosse atual.
3. **Deduplicar cruzamentos por `nome` antes de ordenar.** Medido: a mesma via
   transversal entra **2×** porque compartilha vários nós com o logradouro; e
   em Rua 8 de Maio **10 dos 16** cruzamentos receberam o **mesmo** número
   (plateau de âncoras). Sem dedup, `escolher_entre_ruas` devolve empate.
4. **Tolerância lateral do eixo vira teste** (§8.3.1). Com 40 m medem-se
   **6 a 19 inversões de número** por rua — âncora de via paralela passando
   por dentro. Dedup por nó não resolve: é o valor da tolerância que está
   generoso. Reportar a **% de inversões** junto da métrica, em vez de
   assumir que a projeção está limpa.
5. **§8.5 ganha duas colunas:** além de "% com ≥2 âncoras" e "% com ≥2
   cruzamentos", persistir **% de ruas com `entre` preenchido** e **% do eixo
   coberto pelas âncoras** (medido: 53% e 81% em duas ruas — cruzamento fora
   da faixa é o motivo nº 1 de `intersecoes` enxuta).
6. **Raio de cobertura ≠ raio de query** (§17.1): `around:20000` segue
   proibido; valem `around:150` e `around:80`.

## 9. Etapas 7–9

- **7 — Formatter:** `{codigo}= {rua} Nº {numero} entre {A} e {B} - CEP {cep} ({nome})` com fallbacks; `({nome})` só com `has_name`; idempotente; apply escopado ao filtro.
- **8 — Job + infra + UI:** `contact_jobs` **com o serviço que a consome**; nginx `client_max_body_size 16m` (não mexer no `proxy_read_timeout`); `CONTACT_RENAMER_ENABLED` **passa a valer** (endpoint 409 quando desligada); `ENTRE_RUAS_RADIUS_M` passa a valer; UI paginada + progresso + triagem + export; `import-vcf` deixa de devolver 10k linhas no JSON.
- **9 — E2E + DoD:** 10k ponta a ponta; gates finais; medir frio/quente com dado real.
  **✅ Feito (ADR-0007):** `tests/test_contacts_e2e.py` (marcado `slow`) roda parse →
  upsert → job GEOCODE → preview → job APPLY → formatação sobre 10.000 contatos, e
  mede frio (200 requisições = 200 ruas × 1) × quente (0 requisições). Números em §18.

## 10. Gates (fecham CADA etapa — colar o output)

```
cd backend
python -m pytest tests/test_contacts_vcf.py tests/test_contacts_crm.py tests/test_contacts_organizer.py tests/test_contacts_geocoding.py tests/test_contacts_formatter.py tests/test_contacts_cep_fallback.py -q
python -m pytest tests/test_contacts_jobs.py tests/test_contacts_overpass.py -q
# etapa 9 — E2E de 10k (lento ~2,5 min): rodar explicitamente e colar o relatório
python -m pytest tests/test_contacts_e2e.py -q -s
# etapa 9 — frio real (opt-in, bate na rede): rodar e colar o relatório
LIVE_MODE=true python -m pytest tests/test_contacts_geocode_live.py -q -s
python -m pytest tests/test_migrations_schema_alignment.py tests/test_schema_migration.py tests/test_desktop_migrations.py tests/test_app_integrity.py -q
python -m tests.integrity_audit     # 19/0 — allowlist intocada
python -m alembic heads             # head único
python -m ruff check app tests
# se tocar frontend:
cd ../frontend && npx tsc --noEmit && npx eslint .
```

## 11. DoD geral

- [x] Preview sem teto · apply por filtro (`all_matching`), sem seleção → 422
- [x] Parser com literais passando (`1443= berredos 145` · `1= berredos Nº 145 entre Rua A e Rua B - CEP 00000-000`)
- [x] Upsert em blocos de 500 (medido: 4.800 → 1.206 statements / 1.200 contatos)
- [x] Geocoding com cache por rua (frio = §4.1) · breaker reusado
- [x] **Etapa 6** — `intersecoes` por âncora, `[]` quando não há, UPDATE-only, métrica persistida
      (`infrastructure/geocoding/overpass_provider.py` + `ContactJobService._lote_overpass`;
      `tests/test_contacts_overpass.py` 27 + `TestJobOverpass` em `tests/test_contacts_jobs.py`
      provando "não toca em lat/lng" e métrica persistida; UI `OVERPASS` em `ContactsRenamerPage`)
- [x] Formatter idempotente (`formatter.py`, ADR-0005)
- [x] Job + retomada + nginx 16m + flags em vigor (`contact_jobs`, ADR-0006)
- [x] UI paginada + progresso + triagem + export (`ContactsRenamerPage`, rota `/whatsapp/contacts/renomeador`)
- [x] **Fallback de CEP** ViaCEP → BrasilAPI → PontoFato (etapa 9, ADR-0007)
- [x] 10k ponta a ponta (`tests/test_contacts_e2e.py`, marcado `slow`)
- [x] Frio × quente medido com número (200 req → 0 req) — §18
- [x] Frio **real** medido contra os provedores (0,95–2,00 s/rua; corrige o §4.1)
- [x] Origem do geocode (OSM × CEP) visível na triagem (`geocode-origem` + UI)
- [x] Todos os gates verdes · `integrity_audit` 19/0 · nada commitado

## 12. Pendências

| # | Pendência | Impacto |
|---|---|---|
| 1 | ~~**`contacts.default_city`/`default_uf` (fato do negócio)**~~ → **fechada (§17)** | valores definidos; gravação em `system_settings` na T5 |
| 2 | Alvo oficial: 10k ou 20k | dimensiona nginx e tamanho de lote |
| 3 | Photon agora ou depois | > ~900 ruas |
| 4 | Confirmar política multi-TEL | §D10 |
| 5 | ~~**Confirmar o caso "Passagem Ivan Leão, 45"** (§8.0)~~ → **fechada (§17)** | caso existe, mas **não se reproduz** no OSM; aceite passa a ser métrica |

## 13. Rollback

- Tudo atrás de `CONTACT_RENAMER_ENABLED=false`.
- Migrations aditivas: rollback = dropar o novo, sem tocar em `clients`.
- Job retoma pelo `contact_jobs`.

## 14. ADRs

| ADR | Assunto |
|---|---|
| 0001 | Renomeador `.vcf` — decisões de base |
| 0002 | Preview/apply desacoplados + `page_size=200` |
| 0003 | Importação em lote (bloco 500 + fallback linha a linha) |
| 0004 | Cache por rua + interseções; **orçamento D14**; **fonte das âncoras**; spike; **LGPD** |
| 0005 | Formatter do nome de rota e fallbacks (**etapa 7 — feito**) |
| 0006 | Jobs bounded-batch + `contact_jobs` + flag em vigor (**etapa 8 backend**) |
| 0007 | Fallback de CEP (ViaCEP → BrasilAPI → PontoFato) + E2E de 10 mil com medição frio/quente (**etapa 9**) |

> **LGPD** (registrada em `ADR-0004` → seção *LGPD*): os endereços dos contatos
> saem para terceiros (Nominatim/Photon/Overpass/ViaCEP); `.vcf` não persistido
> (D6); não logar PII em claro; `lat`/`lng` documentado como dado de localização.

## 15. Armadilhas conhecidas

- **OSM-BR quase não tem número de casa** → "entre" é minoria; medir (§8.5), nunca supor.
- `intersecoes` vazia **não é erro** — é triagem (D2).
- **Overpass é segunda requisição por rua**: por isso ficou fora do frio (D14).
- `BackgroundTasks` não existe no repo — não introduzir.
- Guard exclui `repositories/` — tabela nova precisa de consumidor em `application/`.
- Duas fontes de schema (`create_all` × Alembic) — v7 não rodou em Postgres.

## 16. Registro de revisões

| REV | Mudança |
|---|---|
| 4 | Consolidação Fase 2 |
| 4.1 | DoD como função do nº de ruas |
| 4.2 | Contrato congelado + âncoras |
| 5 | Rótulo padronizado; orçamento D14; seção 22 (numeração do REV. 5) |
| **6** | **Verificação de abertura; spike como portão; Overpass fora do frio; métrica de âncoras; D14** |
| **7** | **Fatos do negócio confirmados (§17); spike T3/T4 respondido (§8.0 fechado); pendências 1 e 5 encerradas** |
| **8** | **Etapa 9: fallback de CEP (ADR-0007) + E2E de 10 mil com medição de frio/quente (§18)** |

> **Regra do rótulo:** o número do cabeçalho é sempre o da **última linha** desta tabela.
>
> **Regra das referências:** `§N` aponta para uma seção **viva** deste documento
> (o gate `grep -oE '§[0-9]+(\.[0-9]+)?'` exige que todo alvo exista). Citação de
> numeração de REV. antiga aparece como “seção N”, sem o símbolo — é história,
> não referência.

> **Correções aplicadas na abertura (§0.1, 2026-09-25)** — o REV. 6 renumerou
> as seções e ficaram referências soltas do REV. 5; corrigidas nesta cópia:
>
> | Onde | Estava | Ficou |
> |---|---|---|
> | §0 | "ordem do `§17`" (inexistente) | `§0.1 → §8 → §9` |
> | §8.0 · §8.7 · fecho | seção 21.1 (antiga) | **§12, item 1** |
> | §8.6 | "Testes (`§14`)" (= ADRs aqui; era o §14 *Testes* do REV. 5) | `§10` (Gates) |
> | §8.0 | caso "Ivan Leão / Berredos e Andradas" dado como conhecido | marcado como **sem fonte no repo** (novo pendência 5) |
> | §14 | LGPD saiu do corpo no renumeração | ponteiro sob a tabela de ADRs |
> | `ADR-0004` | seções 7/18.5, 18, 13, 21.1 (numeração antiga) | `§7`/`§8`, `§15`, *sem seção*, `§12, item 1` |

## 17. REV. 7 — fatos confirmados e spike respondido (2026-09-25)

### 17.1 Fatos do negócio (definitivos — não re-perguntar)

| Fato | Valor |
|---|---|
| Depósito | **Passagem Ivan Leão, 45 — Icoaraci, Belém-PA** |
| CEP do depósito | **66811-120** (via Nominatim, campo estruturado `postcode`) |
| `contacts.default_city` | **Belém** |
| `contacts.default_uf` | **PA** |
| Cobertura | **20 km** do depósito — **raio de cobertura** (classificação dentro/fora, haversine) |
| Caso de aceite | Passagem Ivan Leão, 45 → esperado "entre Berredos e Andradas" (**hipótese, agora testada**) |

Ponto de referência medido: lat **-1.3056058**, lng **-48.4738326**.
`road` = "Passagem Ivan Leão" · `city_district` = Icoaraci · `suburb` = Agulha ·
`state` = Pará. **`Agulha` não funciona como sufixo de query** ("Passagem Ivan
Leao com Agulha, Belem, PA" → 0 resultados), mas **existe** no OSM como campo
estruturado — registrar e não tentar de novo.

> **Raio ≠ query.** Os 20 km são cobertura do cliente. **`around:20000` é
> proibido** na consulta Overpass; por rua valem `around:150` (cruza) e
> `around:80` (âncoras), como no §8.2.

### 17.2 Spike T3/T4 respondido

Números completos no **ADR-0004 → "Resultado do spike T3/T4"**. Resumo:

- **4 de 5 ruas com ≥2 âncoras úteis** (34 / 16 / 19 / 35) → **portão §8.0.3
  não dispara**: há dado real. Só a Rodovia Augusto Montenegro ficou em 0.
- **O caso de aceite não se reproduziu**: `escolher_entre_ruas(…, 45)` →
  `null`. Dos 6 cruzamentos reais da Ivan Leão, **"Andradas" não existe** e
  **"Travessa dos Berredos" existe mas cai fora da faixa de âncoras**.
- **Qualidade é o limite real, não quantidade**: inversões de número em 4/5
  ruas, colapso (10 de 16 cruzamentos com o mesmo número em 8 de Maio),
  duplicatas por nó compartilhado, eixo coberto só em 53–81%.
- **Operação**: query combinada morre (504), 3 queries separadas + retry
  passam; validar `timestamp_osm_base`; custo 13–895 s/rua ⇒ confirma D14.

**Consequência para o aceite (§8.7):** a etapa 6 se mede pela **% de ruas com
`intersecoes` ≥2 e com `entre` preenchido** (§8.5), nunca pelo par esperado
"Berredos e Andradas".

## 18. REV. 8 — etapa 9: fallback de CEP e E2E de 10 mil (2026-09-29)

### 18.1 Fallback de CEP (ADR-0007)

Segundo elo do geocode (D2), acionado **só** quando o provedor não conhece o
logradouro:

```
OSM miss → ViaCEP (endereço→CEP) → BrasilAPI (/cep/v2, lat/lon) → PontoFato (lat/lon)
```

- `app/infrastructure/geocoding/cep.py` (novo) — `BrasilApiCepClient`,
  `PontoFatoCepClient`, `CepFallback`; herdam `RateLimitedHttp` (rate limit,
  retry, breaker), sem dependência Python nova.
- `GeocodingService._resultado_por_cep` fecha a cadeia; `get_or_geocode` ganhou
  `cep_hint` (que **não** entra na `chave_rua` — contrato congelado).
- A coluna `provider` do cache passa a registrar a origem real
  (`brasilapi`/`pontofato`), para o ponto de trecho não se confundir com o OSM.
- Flags: `CEP_FALLBACK_ENABLED`, `BRASILAPI_ENABLED`, `PONTOFATO_ENABLED`
  (+ `*_BASE_URL`). O PontoFato é **B** no catálogo — entra como 3º elo e pode
  ser desligado sem tocar no código.
- Testes: `tests/test_contacts_cep_fallback.py` (26) + `tests/test_contacts_geocode_live.py` (opt-in, `live`).

### 18.1b Origem do geocode na triagem

A triagem do renomeador passou a mostrar **de onde veio cada endereço**:
`ContactOrganizer.geocode_origem()` → `GET /whatsapp/contacts/organizer/geocode-origem`
(devolve `por_origem` OSM × CEP, `por_status` e a lista das ruas resolvidas por
CEP), e o card **“Origem do endereço”** na `ContactsRenamerPage`. A classificação
é pelo `geocode_cache.provider` — um negativo cacheado do Nominatim continua
contando como OSM.

### 18.2 E2E de 10 mil + medição frio/quente

`tests/test_contacts_e2e.py` (marcado `slow`): parse → upsert em blocos →
job GEOCODE → preview → job APPLY → formatação, sobre 10.000 contatos / 200 ruas.
Sem rede (provedor mock contável), então a métrica é **requisições**, não latência.

```
== Etapa 9 - medicao (10.000 contatos / 200 ruas) ==================
  parse    :    0.48s
  upsert   :    6.49s  (20 blocos de 500)
  FRIO     :   77.02s  | 200 requisicoes (200 ruas x 1) | 101 faixas de ate 100
  QUENTE   :   10.03s  | 0 requisicoes (cache por rua)
  apply    :   45.52s  | 21 faixas de ate 500
  economia : 200 requisicoes no frio -> 0 no quente
```

| Métrica | Alvo (§4.4) | Medido | Situação |
|---|---|---|---|
| Upsert 10k | < 2 min | 6,5 s | ✅ |
| Apply 10k | < 5 min | 45,5 s | ✅ |
| Requisições no frio | nº de ruas | 200 → 200 | ✅ |
| Requisições no quente | 0 | 0 | ✅ |

### 18.2b Medição ao vivo do frio (`LIVE_MODE=true`)

`tests/test_contacts_geocode_live.py` mede a latência **real** (Nominatim +
ViaCEP + fallback de CEP), 5 ruas de Belém — **5 rodadas** em 2026-09-29:

```
  FRIO   :  4.76-4.81s |  0.95s por rua   (4 rodadas, rede boa)
  FRIO   :  10.01s     |  2.00s por rua   (1 rodada, rede lenta)
  QUENTE :   0.00-0.01s | 0 requisicao nova
  fallback de CEP real: brasilapi, Passagem Ivan Leão / Agulha (Icoaraci) - Belém/PA
  logradouro que o OSM nao conhece -> status OK via CEP
```

**Corrige o §4.1 (e a leitura anterior do REV. 8):** o frio é
`nº de ruas × (1 s + latência)`, não um número fixo. As 5 ruas **voltam com
`postcode`** no Nominatim (conferido por `curl` no mesmo dia), então o ViaCEP
**não** entrava nelas e a rodada de 2,00 s/rua não se explicava pelo 2º elo — era
latência (~1 s por requisição) somada ao intervalo do limitador. Alvo de 15 min:
**~900 ruas** na rede boa, **~450** na lenta. Amostra n=5 — indicativo.

### 18.3 Achado operacional (registrado, sem mudança de contrato)

`geocodificar_cliente` preenche `cidade`/`uf` do contato. Se o `.vcf` não traz UF
e o default (D11) não está semeado, a chave do cache muda entre a 1ª e a 2ª
passada e o "quente" deixa de ser quente **para essas ruas**. Em produção não
ocorre (§17.1: Belém/PA semeados). O E2E semeia os defaults de propósito; a
`chave_rua` **não** foi alterada (contrato congelado).

---

**Estado:** §0.1 verde · §8.0 (spike) respondido · §12 (itens 1 e 5) encerradas ·
etapas 6 e 7 verdes nos gates · **etapa 8 backend feita**
(`ContactJobService` + `contact_jobs`, ADR-0006; flag `CONTACT_RENAMER_ENABLED`
em vigor com 409; `ENTRE_RUAS_RADIUS_M` valendo; nginx `client_max_body_size 16m`;
`import-vcf` sem 10k linhas no JSON).
**Etapa 8 completa:** backend (jobs/flag/nginx) **e** UI
(`ContactsRenamerPage` — prévia paginada, progresso do job, triagem e export
`.vcf` renomeado com `?formatar_rota=true`).
**Etapa 9 completa:** fallback de CEP (`infrastructure/geocoding/cep.py` +
`GeocodingService._resultado_por_cep`, ADR-0007) e E2E de 10 mil com medição de
frio/quente (`tests/test_contacts_e2e.py`, marcado `slow`, ADR-0007).
**Fase 2 fechada.** Próximo natural: Fase 3 (PostGIS/CNEFE para "entre ruas").
