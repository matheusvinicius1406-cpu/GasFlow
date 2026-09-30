# Catálogo de APIs Externas — varredura de 3 repositórios

> Missão **docs-only**. Nada aqui foi implementado, nada foi commitado.
> Toda API com status **A** ou **B** foi **chamada de verdade** com `curl` e a resposta está colada em §2.10.
> Regra travada: **proibido** recomendar API com chave comercial/trial/"free tier" que vira pago (ver §3).

---

## 1. Sumário executivo

### 1.1 O que foi varrido

| # | Repositório | Como é organizado | Universo lido | Aproveitável sob a regra D8 |
|---|---|---|---|---|
| R1 | `public-apis/public-apis` | `README.md` único, tabelas por seção `###` | 2.466 linhas · 12 categorias-alvo · **306 entradas sem chave** | ~90% dos itens úteis |
| R2 | `kawsarlog/Ultimate-API-List` | **pastas por categoria**, 1 `README.md` cada | 10 pastas lidas · **67.625 linhas de tabela** | **0 (zero)** |
| R3 | `public-api-lists/public-api-lists` | `README.md` único | 1.221 linhas · 12 categorias-alvo · **137 entradas sem chave** | quase espelho do R1 + exclusivas |

- **373 URLs únicas** depois de deduplicar (sobreposição massiva entre R1 e R3).
- **28 fichas aprofundadas** (todas as A/B), cada uma com teste real.
- Veredito da triagem: **A = 10 · B = 18 · C = 12 grupos** (mais as **67.625** entradas do R2, todas comerciais).

### 1.2 Os 3 achados que valem ação

1. **`BrasilAPI` cobre num único host keyless o que hoje está espalhado em 3 lugares nossos** — `cep/v2` (com **coordenadas**, que o ViaCEP não devolve), `cnpj/v1`, `feriados/v1/{ano}` e `ibge` para código de município. Testado com o endereço de aceite e devolveu `"Passou... Passagem Ivan Leão"/"Belém"/"PA"` + `location.coordinates`. Custo de adoção: baixo. Ver §5.
2. **`PontoFato` devolve lat/lon + vizinhança para o CEP de aceite** (`66811-120`) sem chave — é um segundo elo honesto para a cadeia de fallback de geocoding quando o ViaCEP não basta. Fica **B** só porque os termos de uso não são publicados de forma explícita; a condição está escrita na ficha.
3. **O campo "Auth" das listas não é confiável — e o R2 é uma vitrine paga.** Três APIs listadas como `No` (sem chave) hoje **exigem chave**: `REST Countries` → `401 authKeyMissing`, `Open Charge Map` → `403 must specify an API key`, `GeoNames` → `401 add a username`. Além disso, o **R2 é 100% Apify**: 67.625/67.625 linhas apontam para `apify.com` (pago, conta obrigatória). Consequência prática: qualquer adoção futura **tem de passar pelo `curl`**, não pelo campo Auth da lista.

### 1.3 O que **não** muda

Nenhuma das 3 listas traz alternativa keyless melhor para o núcleo do renomeador. **Nominatim, OSRM e ViaCEP ficam** — a justificativa de "não vale a troca" (item 8 do brief desta missão) está refletida nas fichas de §2.1 e §2.3.

---

## 2. APIs por categoria (P0 → P3)

**Legenda de procedência**

- `R1` = `public-apis/public-apis · README.md`
- `R2` = `kawsarlog/Ultimate-API-List · <Categoria>/README.md`
- `R3` = `public-api-lists/public-api-lists · README.md`

Status: **A** = usável hoje · **B** = passa com condição escrita · **C** = rejeitada (vai para §3).

### 2.1 P0 — Geolocalização / Geocoding

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **Nominatim** | R1:1287 | sem chave | público: **1 req/s**, sem bulk, `User-Agent`/`Referer` obrigatório | dados ODbL; uso comercial do dado OK; self-host permitido | sim | é o nosso geocoder | manter; **self-host** elimina o teto de 1 req/s | **B** (público) / A se self-hosted |
| **Open-Meteo Geocoding API** | R1:2436 + R3:1211 (endpoint próprio) | sem chave | ~10k/dia (fair use) | serviço grátis **não-comercial**; AGPL → self-host permitido | sim | não; complementa o Nominatim na resolução de topônimo | reverter lat/lon de bairro/cidade quando a rua falha no OSM | **B** (só self-host p/ uso comercial) |
| **IBGE Localidades** | R1:1259 | sem chave | não declarado | dados abertos, uso livre com atribuição | sim | não | validar/normalizar município+UF+código IBGE | **A** |
| **adresse.data.gouv.fr** | R1:1223 + R3:605 | sem chave | 50 req/s (doc BAN) | Etalab-2.0, uso comercial OK | **não** (França) | não | — | **B** (cobertura não-BR) |
| **Postcodes.io** | R1:1299 + R3:656 | sem chave | não declarado | MIT + dados OGL | **não** (Reino Unido) | não | — | **B** (cobertura não-BR) |

### 2.2 P0 — CEP / Endereço BR

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **ViaCEP** | R1:1315 + R3:662 | sem chave | fair use, sem header de limite | termos próprios, uso livre p/ consulta | sim | é o nosso CEP | manter como 1º elo | **A** |
| **BrasilAPI** (`/cep/v2`) | R1:1333 | sem chave | fair use | MIT (open source) | sim | **complementa** o ViaCEP (traz lat/lon e `service`) | 2º elo: CEP → coordenada sem Overpass | **A** |
| **PontoFato** | R1:1295 | sem chave | não declarado | termos próprios — **não publicados de forma explícita** | sim | não; alternativa com vizinhança por distância | 3º elo + "vizinhança do CEP" | **B** (confirmar termos antes de produção) |
| **IBGE Localidades** | R1:1259 | sem chave | não declarado | dados abertos | sim | não | resolver `ibge` devolvido pelo ViaCEP em município | **A** |
| **Postmon** | R1:2198 + R3:1089 | sem chave | não declarado | open source | sim | não | fallback opcional | **B** (retornou **503** no teste — indisponível hoje) |

### 2.3 P0 — Roteamento / Distância / Matriz

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **OSRM** (self-hosted) | — (nossa stack, `docker-compose.osrm.yml`) | sem chave | nosso | BSD-2 | sim | já é o nosso roteador | manter | **A** |
| **transport.rest** | R1:2293 | sem chave | fair use | open source (derhuerst) | não (transporte público DE) | não | não é roteamento de entrega | **B** (retornou **503**; escopo ≠ rota de veículo) |

> **Nenhuma alternativa keyless de roteamento/matriz apareceu nas 3 listas.** Concorrente direto do OSRM não foi achado — ver §6.

### 2.4 P1 — Clima / Previsão

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **Open-Meteo** | R1:2436 + R3:1211 | sem chave | 10k chamadas/dia | grátis **só não-comercial**; AGPL → self-host | sim | não (não temos clima) | janela de chuva por bairro p/ priorizar entrega | **B** (self-host obrigatório p/ comercial) |
| **7Timer!** | R1:2415 + R3:1204 | sem chave | não declarado | termos próprios | sim | não | reserva do Open-Meteo | **B** |
| **wttr.in** | R1:2455 | sem chave | fair use, sem SLA | termos próprios; dados agregados | sim | não | consulta pontual (operador) | **B** |
| **Meteorologisk Institutt (met.no)** | R1 + R3:1208 | sem chave | fair use | NLOD/CC-BY; `User-Agent` **obrigatório** | sim | não | alternativa de previsão por hora | **B** (UA obrigatório) |
| **NASA POWER** | R1:2433 | sem chave | fair use | domínio público NASA | sim | não | climatologia, não previsão operacional | **B** (histórico/médio) |

> `weather.gov` (R1:2448 + R3:1209) responde keyless, mas é **exclusivo dos EUA** → sem uso para Belém; não entrou no ranque.

### 2.5 P1 — Horário / Fuso / Feriados

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **BrasilAPI** (`/feriados/v1/{ano}`) | R1:1333 | sem chave | fair use | MIT | sim (nacional, com `type`) | não | dias úteis BR no agendamento | **A** |
| **Nager.Date** | R1:391 + R3:168 | sem chave | fair use | MIT | sim (90+ países, inclui BR) | não | fallback de feriado + expansão multi-país | **A** |
| **OpenHolidays API** | R3:171 | sem chave | fair use | CC-BY-4.0 | **não** (sem dados BR no teste — `[]`) | não | — | **B** (sem cobertura BR) |
| **isdayoff.ru** | R1:394 + R3:169 | sem chave | não declarado | open source | **não** (RU/UA) | não | — | **B** (sem cobertura BR) |
| **UK Bank Holidays** | R1:398 | sem chave | arquivo estático | Open Government Licence | **não** (RU) | não | — | **B** (sem cobertura BR) |

### 2.6 P1 — Automação / Webhooks / Filas

**Nenhum item A/B.** As 3 listas não oferecem nada keyless que sirva ao padrão `bounded-batch`. Ver §6.

### 2.7 P1 — IA / LLM / Embeddings

**Nenhum item A/B.** As candidatas sem chave estão mortas: `OpenVisionAPI` (R1:1565) e `EXUDE-API` (R1:1546). O resto da categoria é `apiKey`/`OAuth`, e o R2 só traz atores Apify. Continuamos com o provider de IA já existente. Ver §6.

### 2.8 P2 — Integrações / Pagamento / ERP / Câmbio

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **currency-api** (fawazahmed0, via jsDelivr) | R1:546 | sem chave | **sem limite** (arquivo estático em CDN) | MIT | sim (inclui BRL) | não | conversão de custo/insumo dolarizado | **A** |
| **Frankfurter** | R1:555 + R3:258 | sem chave | fair use | open source; dados do BCE | sim (BRL) | não | alternativa simples de câmbio | **A** |
| **BCB — Olinda (PTAX/Moedas)** | R1:1334 (portal `dadosabertos.bcb.gov.br`) | sem chave | fair use | dados abertos do Banco Central | sim | não | fonte **oficial** de câmbio | **A** |

### 2.9 P2 — Validação de dados (telefone, e-mail, CPF/CNPJ)

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **BrasilAPI** (`/cnpj/v1`) | R1:1333 | sem chave | fair use | MIT | sim | não | enriquecer cliente PJ (razão social, situação) | **A** |
| **ReceitaWS** | R1:1335 | sem chave | **apertado** (free tier ~3 req/min) | termos próprios | sim | não | fallback de CNPJ | **B** (rate limit apertado) |
| **PurgoMalum** | R1:575 + R3:277 | sem chave | não declarado | termos próprios | neutro | não | sanitizar texto livre do cadastro | **A** |
| **cnpj.wiki** | R3:678 | sem chave | não declarado | termos próprios (**não declarados**) | sim | não | — | **B** (rota JSON não confirmada: `/api/...` devolveu HTML) |

> A suíte **apilayer** (`numverify`, `mailboxlayer`, `languagelayer`, `vatlayer`) aparece no R3 **como `No`**, mas é provedor comercial com chave → §3.

### 2.10 P3 — Outras (bucket)

| API | Procedência | Auth | Rate limit declarado | Licença / comercial | BR? | Substitui algo nosso? | Uso no Gás Flow | Status |
|---|---|---|---|---|---|---|---|---|
| **Wikipedia / MediaWiki API** | R1:1720 + R3:849 | sem chave | fair use | conteúdo CC-BY-SA; API livre | sim (pt.wikipedia) | não | descrição/validação de topônimo | **A** |
| **Microlink.io** | R1:1688 + R3:838 | sem chave | free tier limitado | termos próprios | neutro | não | unfurl de link no painel | **B** (free tier) |

> `Open Charge Map` (R3:1109), `REST Countries` (R1:1302 + R3:657) e `GeoNames` (R1:1249) caíram para **C** — ver §3. Eram os itens "P3/pontos de recarga e países" que pareciam keyless.

### 2.10b Validação real (item 7 do brief desta missão) — comando e resposta colados

Todas as chamadas abaixo foram feitas **sem chave**, com `User-Agent` identificando a aplicação (exigência de política do Nominatim/met.no). Endereço-caso de aceite: **Passagem Ivan Leão, 45, Icoaraci, Belém-PA, 66811-120** → CEP `66811120`.

**P0 — Geolocalização / CEP**

```
ViaCEP         curl -s https://viacep.com.br/ws/66811120/json/                      → 200  "logradouro":"Passagem Ivan Leão","bairro":"Agulha (Icoaraci)","localidade":"Belém","uf":"PA","ibge":"1501402"
BrasilAPI cep  curl -s https://brasilapi.com.br/api/cep/v2/66811120                 → 200  "street":"Passagem Ivan Leão","city":"Belém","location":{"coordinates":{"longitude":"-48.4..."}}
IBGE           curl -s https://servicodados.ibge.gov.br/api/v1/localidades/municipios/1501402 → 200  {"id":1501402,"nome":"Belém", ... "UF":{"sigla":"PA"}}
PontoFato      curl -s https://pontofato.com/api/cep/66811120                       → 200  {"cep":"66811-120","pontos":[{"logradouro":"ALAMEDA SEM DENOMINACAO","lat":-1.3047,"lon":-48.4736,...}]}
Postmon        curl -s https://api.postmon.com.br/v1/cep/66811120                   → 503  (sem corpo — serviço indisponível no teste)
Nominatim      curl -s "https://nominatim.openstreetmap.org/search?q=Passagem+Ivan+Leao+45+Icoaraci+Belem&format=json&limit=1" → 200  [{"lat":"-1.3056058","lon":"-48.4738326","type":"residential",...}]
Nominatim rev  curl -s "https://nominatim.openstreetmap.org/reverse?lat=-1.3056&lon=-48.4738&format=json" → 200  {"osm_type":"node","lat":"-1.3056882","lon":"-48.4736860",...}
Open-Meteo geo curl -s "https://geocoding-api.open-meteo.com/v1/search?name=Belem&count=1" → 200  {"results":[{"name":"Belém","latitude":-1.45583,"country_code":"BR",...}]}
adresse (FR)   curl -s "https://api-adresse.data.gouv.fr/search/?q=8+bd+du+port&limit=1" → 200  {"label":"8 Boulevard du Port 95000 Cergy",...}
Postcodes.io   curl -s https://api.postcodes.io/postcodes/SW1A1AA                   → 200  {"postcode":"SW1A 1AA","country":"England",...}
OpenPLZ (DE)   curl -s "https://openplzapi.org/de/Localities?postalCode=10115"      → 200  [{"postalCode":"10115","name":"Berlin",...}]  (exclusiva do R3:651; não-BR, fora do ranking por utilidade)
```

**P0 — Roteamento**

```
OSRM route     curl -s "https://router.project-osrm.org/route/v1/driving/-48.47,-1.30;-48.46,-1.29?overview=false" → 200  {"code":"Ok","routes":[{"distance":2150.5,"duration":177.5}]}
OSRM nearest   curl -s "https://router.project-osrm.org/nearest/v1/driving/-1.3056,-48.4738" → 200  {"code":"Ok","waypoints":[...]}
transport.rest curl -s "https://transport.rest/locations?query=Berlin&results=1"   → 404 ;  https://v6.db.transport.rest/... → 503 (instância fora no teste)
```

**P1 — Clima**

```
Open-Meteo     curl -s "https://api.open-meteo.com/v1/forecast?latitude=-1.3056&longitude=-48.4738&daily=precipitation_sum&timezone=America%2FBelem" → 200  {"latitude":-1.3005,"utc_offset_seconds":-10800,"daily_units":{...}}
7Timer!        curl -sL "http://www.7timer.info/bin/api.pl?lon=-48.47&lat=-1.30&product=civil&output=json" → 200  {"product":"civil","dataseries":[{"temp2m":27,...}]}
wttr.in        curl -s "https://wttr.in/Belem?format=j1"                            → 200  {"current_condition":[{"FeelsLikeC":"17",...}]}
met.no         curl -s -H "Accept: application/json" "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=-1.30&lon=-48.47" → 200  {"type":"Feature","geometry":{"coordinates":[-48.47,-1.3,17]},...}
NASA POWER     curl -s "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR&community=AG&longitude=-48.47&latitude=-1.30&start=20260101&end=20260103&format=JSON" → 200  {"properties":{"PRECTOTCORR":{"20260101":2.0,"20260102":3.2,...}}}
weather.gov    curl -s -H "Accept: application/geo+json" "https://api.weather.gov/points/39.7456,-97.0892" → 200  (EUA apenas)
```

**P1 — Feriados / Fuso**

```
BrasilAPI fer  curl -s https://brasilapi.com.br/api/feriados/v1/2026                    → 200  [{"date":"2026-01-01","name":"Confraternização mundial","type":"national"},{"date":"2026-02-16","name":"Carnaval",...}]
Nager.Date BR  curl -s https://date.nager.at/api/v3/PublicHolidays/2026/BR              → 200  [{"date":"2026-01-01","localName":"Confraternização Universal"},{"date":"2026-02-16","localName":"Carnaval",...}]
OpenHolidays   curl -s "https://openholidaysapi.org/PublicHolidays?countryIsoCode=BR&validFrom=2026-01-01&validTo=2026-12-31" → 200  []  (sem dados BR)
isdayoff.ru    curl -s "https://isdayoff.ru/20260101?cc=ru"                             → 200  1
UK Bank Hols   curl -s https://www.gov.uk/bank-holidays.json                            → 200  {"england-and-wales":{"events":[{"title":"New Year’s Day",...}]}}
```

**P2 — Câmbio / Validação**

```
currency-api   curl -s "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json" → 200  {"date":"2026-09-28","usd":{"brl":...,"eur":...}}
Frankfurter    curl -sL "https://api.frankfurter.app/latest?from=USD&to=BRL"            → 200  {"amount":1.0,"base":"USD","date":"2026-09-28","rates":{"BRL":5.2018}}
BCB Olinda     curl -s "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/Moedas?%24format=json" → 200  {"value":[{"simbolo":"AUD","nomeFormatado":"Dólar australiano",...}]}
BrasilAPI CNPJ curl -s https://brasilapi.com.br/api/cnpj/v1/19131243000197              → 200  {"uf":"SP","cep":"01311902","qsa":[{"nome_socio":"HAYDEE SVAB",...}]}
ReceitaWS      curl -s https://receitaws.com.br/v1/cnpj/19131243000197                  → 200  {"situacao":"ATIVA","nome":"OPEN KNOWLEDGE BRASIL",...}
PurgoMalum     curl -s "https://www.purgomalum.com/service/json?text=hello"             → 200  {"result":"hello"}
cnpj.wiki      curl -sL https://cnpj.wiki/api/cnpj/19131243000197                       → 200  (HTML do site, não JSON — rota da API não confirmada)
```

**P3 — Open Data**

```
Wikipedia      curl -s "https://pt.wikipedia.org/api/rest_v1/page/summary/Bel%C3%A9m"   → 200  {"type":"standard","title":"Belém","wikibase_item":"Q5776",...}
Microlink.io   curl -s "https://api.microlink.io/?url=https://example.com"              → 200  {"status":"success","data":{"publisher":"example.com","title":"Example Domain",...}}  (sem headers de limite)
```

**Sobre headers de limite:** nenhuma das respostas testadas trouxe `X-RateLimit-*` nem `Retry-After`. O que existe é limite **declarado em política/documentação** (Nominatim 1 req/s; Open-Meteo 10k/dia; ReceitaWS ~3 req/min; met.no exige `User-Agent`). Só o ViaCEP e o Nager.Date mandaram `Cache-Control` público (`max-age=3600` / `604800`).

---

## 3. Anexo A — Rejeitadas (com motivo)

Cada linha **falhou em ≥1 portão** (Auth / política de uso em lote / licença comercial).

| API | Procedência | Motivo da rejeição | Evidência |
|---|---|---|---|
| **REST Countries** | R1:1302, R3:657 (ambas dizem `No`) | **Auth** — virou comercial; exige `Authorization` | `curl https://api.restcountries.com/v5/all` → **401** `{"errors":[{"message":"Authorization key required.","code":"authKeyMissing"}]}`; `restcountries.com/v3.1/*` → só devolve aviso de depreciação |
| **Open Charge Map** | R3:1109 (diz `No`) — o R1:2245 já dizia `apiKey` | **Auth** — chave obrigatória | `curl "https://api.openchargemap.io/v3/poi/?..."` → **403** `You must specify an API key using the key query parameter` |
| **GeoNames** | R1:1249 (diz `No`) | **Auth** — exige `username` | `curl "http://api.geonames.org/searchJSON?q=Belem&maxRows=1"` → **401** `Please add a username to each call` |
| **TransitLand** | R1:2258, R3:1115 (dizem `No`) | **Auth** — exige chave (agora) | `curl https://transit.land/api/v2/rest/operators?limit=1` → **401** `{"error":"Unauthorized"}` |
| **Cep.la** | R1:1233 | **Política/disponibilidade** — domínio morto | `curl -L http://cep.la/66811120` → **404** "Page not found" |
| **Zippopotam.us** | R1:1319, R3:666 | **Política/cobertura** — sem dados BR (404) | `curl http://api.zippopotam.us/BR/66811120` → **404** `{}` |
| **OpenVisionAPI** | R1:1565 | **Disponibilidade** — host não responde | `curl https://openvisionapi.com/` → **000** (falha de conexão) |
| **EXUDE-API** | R1:1546 | **Disponibilidade** — endpoint da lista não responde JSON | `curl http://uttesh.com/exude-api/` → **301** (redireciona, sem API) |
| **NumValidate** | R3:275 | **Disponibilidade** — é demo, não serviço (404) | `curl "https://numvalidate.com/api/validate?number=..."` → **404** |
| **Pirate Weather** | R1:2441 | **Auth** — chave no path | `curl https://api.pirateweather.net/forecast//-1.30,-48.47` → **404** `no Route matched` (falta a chave no path) |
| **apilayer** — `numverify`, `mailboxlayer`, `languagelayer`, `vatlayer` | R3:272,274,276,284 (todas dizem `No`) | **Auth/licença** — provedor comercial; chave paga | rejeitado por política (restrição D8, item 2 do brief); não testado |
| **caldays** | R1:381, R3:161 | **Disponibilidade** — rota de API não confirmada | `curl "https://caldays.com/api/v1/holidays?country=BR&year=2026"` → **200** mas devolveu **HTML**, não JSON |
| **Todo o R2 (`Ultimate-API-List`)** | R2 (10 pastas) | **Auth/licença** — atores Apify pagos, conta obrigatória | **67.625/67.625** linhas de tabela apontam para `apify.com`; **0** entradas não-Apify |

> Não é lixo: a lista acima é o que impede alguém de tentar de novo o que já falhou.

---

## 4. Anexo B — Procedência (quem trouxe o quê)

### 4.1 R1 — `public-apis/public-apis` (o mais útil)

`README.md` único, 2.466 linhas, seções `###`. Carregou ~90% do material aproveitável. Categorias-alvo conferidas por linha: `Calendar` (378), `Data Validation` (568), `Finance` (973), `Geocoding` (1215), `Government` (1325), `Machine Learning` (1532), `Open Data` (1656), `Phone` (1788), `Tracking` (2190), `Transportation` (2208), `Weather` (2411), `Currency Exchange` (535).

### 4.2 R3 — `public-api-lists/public-api-lists` (espelho + exclusivas)

`README.md` único, 1.221 linhas. Quase espelho do R1, com **exclusivas** que valeram: `OpenHolidays API` (171), `OpenPLZ API` (651), `cnpj.wiki` (678), `Crime Brasil` (688), `NumValidate` (275), `TimeZones iCal Library` (174), `DWD API` (1206), `Postali` (654). Também tinha **erros de auth** que o R1 acertou (Open Charge Map: R3 diz `No`, R1 diz `apiKey` — e a realidade é chave obrigatória).

### 4.3 R2 — `kawsarlog/Ultimate-API-List` (vitrine paga)

17 pastas por categoria — **não tem** Geocoding, Weather nem Calendar. Leitura real das 10 pastas relevantes:

| Pasta | Linhas de tabela | → `apify.com` |
|---|---:|---:|
| Developer_tools | 15.962 | 15.962 |
| Automation | 15.857 | 15.857 |
| Ecommerce | 10.493 | 10.493 |
| AI | 7.072 | 7.072 |
| Other | 6.643 | 6.643 |
| Real_estate | 3.546 | 3.546 |
| Agents | 2.601 | 2.601 |
| Integrations | 2.586 | 2.586 |
| Travel | 1.927 | 1.927 |
| Open_source | 938 | 938 |
| **Total** | **67.625** | **67.625 (100%)** |

As poucas aparências de domínios "reais" (ex.: `openchargemap.org`, `amazon.com`, `booking.com`) são **alvos de scraping** dentro da descrição do ator, não entradas de API. **Nada exclusivo e aproveitável** sob a regra D8.

### 4.4 Deduplicação

- **Presente nos 3 repos:** nenhum item.
- **Presente em 2 (R1+R3), deduplicado preservando as 2 procedências:** Open-Meteo, ViaCEP, Postmon, Nager.Date, Frankfurter, REST Countries, adresse.data.gouv.fr, Postcodes.io, Zippopotam.us, PurgoMalum, Microlink.io, Wikipedia, Open Charge Map, TransitLand, 7Timer!, met.no, weather.gov, NASA POWER.
- **Exclusivo do R1:** Nominatim, IBGE, BrasilAPI, PontoFato, ReceitaWS, currency-api, GeoNames, OpenVisionAPI, EXUDE-API, wttr.in, UK Bank Holidays. (R1 foi a fonte da maior parte do P0 BR.)
- **Exclusivo do R3:** OpenHolidays API, OpenPLZ API, cnpj.wiki, NumValidate, DWD API, TimeZones iCal Library.
- **Exclusivo do R2:** nada usável.

---

## 5. Recomendações (máx. 3)

### R1 — Cadeia de fallback de CEP: `ViaCEP → BrasilAPI → PontoFato`
- **O que muda:** o CEP passa a poder devolver **coordenada** (`BrasilAPI /cep/v2` → `location.coordinates`) sem depender do Overpass para o caso simples. Entra como fallback **bounded** (padrão de jobs de ADR-0006) e cacheado em `geocode_cache` (ADR-0004) — nunca em loop aberto.
- **Custo:** baixo — 2 endpoints novos na camada `infrastructure/geocoding`, atrás do mesmo `RateLimitedHttp`.
- **Risco:** baixo. `PontoFato` é **B** (termos não publicados): só entra como 3º elo, com flag para desligar.
- **Agora?** **Sim.** É a maior lacuna real do renomeador (lat/lon por CEP).

### R2 — Feriados nacionais BR via `BrasilAPI /feriados/v1/{ano}`
- **O que muda:** cálculo de dia útil (agendamento, horário do WhatsApp) deixa de depender de tabela local.
- **Custo:** muito baixo — 1 endpoint, 1 cache anual.
- **Risco:** baixo. Fallback: `Nager.Date` (também **A**, valida o mesmo calendário).
- **Agora?** **Sim.**

### R3 — Clima **somente self-hosted** (Open-Meteo), se e quando a janela de entrega precisar
- **O que muda:** previsão de chuva por bairro para priorizar entrega.
- **Custo:** médio — subir o contêiner Open-Meteo ao lado do OSRM.
- **Risco:** baixo, **desde que self-hosted**: a instância **pública** é explicitamente **não-comercial** (`open-meteo.com/en/terms`), o que a reprova no portão 3 para um produto comercial.
- **Agora?** **Não — Fase 3.** Não há ganho imediato sobre o núcleo do renomeador.

---

## 6. Lacunas (o que a varredura **não** cobriu bem)

- **Roteamento / matriz de distância:** nenhuma alternativa keyless nas 3 listas. O que apareceu (TransitLand, transport.rest) é transporte público ou está fora do ar. **OSRM fica; não vale a troca.**
- **Automação / webhooks / filas:** nada. Nenhum provedor keyless compatível com o padrão `bounded-batch` do projeto.
- **IA / LLM / Embeddings sem chave:** nada vivo. `OpenVisionAPI` e `EXUDE-API` estão mortos; `Statlyte`/`ModelFfax`/`TensorFeed` são só metadados de preço; o R2 nem cobre IA keyless. Mantém-se o provider já existente.
- **CRM / Contatos:** não coberto (e fora de escopo, por decisão do item 12 do brief).
- **Busca de logradouro por NOME de rua (não por CEP):** as listas só oferecem CEP→endereço. A resolução "rua por nome + bairro" continua dependendo de Nominatim/OSM. Nada novo aqui.
- **Interseções / "entre ruas":** nenhuma das listas cobre grafo viário. Permanece exclusivamente Overpass (arquitetura já existente).
- **Categorias‑alvo ausentes no R2:** Geocoding, Weather e Calendar não existem como pasta no `Ultimate-API-List` — a cobertura dessas faixas veio só de R1/R3.
- **Fuso horário:** a única API keyless boa que testei (`timeapi.io`, → 200) **não tem procedência em nenhuma das 3 listas** — por isso ficou fora do catálogo, conforme a regra de citar `repo:arquivo:linha`. Fica registrada aqui como pista para uma varredura futura.
- **`PontoFato` e `cnpj.wiki`:** validados no endpoint principal, mas com **termos de uso não publicados** de forma explícita. Ambos ficaram **B**; uma revisão jurídica leve fecharia o A.
