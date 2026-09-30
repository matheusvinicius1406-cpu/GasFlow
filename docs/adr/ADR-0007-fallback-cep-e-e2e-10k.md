# ADR-0007 — Fallback de CEP (ViaCEP → BrasilAPI → PontoFato) e o E2E de 10 mil

**Status:** Aceito · **Data:** 2026-09-29 · **Fase:** 2 (etapa 9)
**Relacionado:** `docs/adr/ADR-0004-cache-geocoding-por-rua.md`,
`docs/prompts/renomeador-contatos-fase2.md` (§4.4, §7, §9 etapa 9),
`docs/auditoria/catalogo-apis-externas.md` (recomendação R1).

---

## Contexto

Duas lacunas fechavam a Fase 2:

1. **O logradouro que o OSM não conhece morria em triagem.** O cache por rua
   (ADR-0004) já resolvia o custo, mas quando o Nominatim devolvia `None` o
   contato saía `NAO_ENCONTRADO` mesmo quando o **CEP** era conhecido — e o
   Brasil tem CEP para muito logradouro que o OSM-BR não tem.
2. **A escala de 10 mil não estava medida.** O ADR-0006 registrou explicitamente
   "tempo e escala não foram medidos; o alvo de 10k ponta a ponta é a etapa 9".

A varredura de APIs externas (`docs/auditoria/catalogo-apis-externas.md`) achou
duas fontes keyless que resolvem CEP → endereço **e** coordenada, ambas
validadas com `curl` no endereço de aceite (CEP `66811-120`):

| Fonte | Endpoint | O que devolve | Licença |
|---|---|---|---|
| BrasilAPI | `/api/cep/v2/{cep}` | `street`, `city`, `state` + `location.coordinates` | MIT |
| PontoFato | `/api/cep/{cep}` | `pontos[]` com `lat`/`lon` (CNEFE/IBGE) | termos próprios (**B**) |

A regra travada do projeto proíbe chave comercial — os dois passam (o PontoFato
com a condição registrada no catálogo, por isso entra só como **3º elo**).

## Decisão

### 1. Cadeia fixa **ViaCEP → BrasilAPI → PontoFato**, só quando o provedor falha

`app/infrastructure/geocoding/cep.py` (novo) com `EnderecoCep`,
`BrasilApiCepClient`, `PontoFatoCepClient` e `CepFallback`.

A cadeia **não substitui** o geocoder: ela só roda quando
`geocode_street()` devolve `None` (`GeocodingService._resultado_por_cep`). Um CEP
que o contato já trazia abre a cadeia direto; sem ele, o ViaCEP (endereço → CEP)
descobre um primeiro — é isso que faz a cadeia ter os três nomes.

O CEP é **normalizado para 8 dígitos** antes de qualquer chamada: CEP fora do
formato não gera requisição (o provedor devolveria erro por nada e gastaria uma
cota do rate limit).

### 2. Ponto de CEP é de **trecho**, não de casa — e a origem fica gravada

Um CEP de rua cobre um trecho. Usar a sua coordenada é aceitável como
**fallback**, não como substituto do OSM. Consequência direta: a coluna
`provider` do cache passa a registrar quem respondeu de fato
(`brasilapi`/`pontofato`), em vez de carimbar tudo como o provedor do OSM.
Dado auditável tem de dizer a própria origem — sem isso, um ponto de CEP
ficaria indistinguível de um resultado do Nominatim.

### 3. `cep_hint` **não** entra na chave do cache

`chave_rua = sha256(normalize(rua|bairro|cidade|uf))` é contrato congelado (§7).
O CEP entra apenas como atalho do fallback
(`get_or_geocode(..., cep_hint=...)`), nunca na chave — senão duas consultas do
mesmo logradouro com CEPs diferentes (o do contato e o do ViaCEP) custariam duas
linhas de cache.

### 4. Sem dependência nova, com a mesma máquina de falha

Os clientes herdam de `RateLimitedHttp`, então ganham de graça o rate limit, o
retry com backoff, o `User-Agent` e o `CircuitBreaker` já usados pelos demais
provedores. Nenhum método levanta: provedor fora do ar, HTTP 4xx/5xx, resposta
sem coordenada e CEP inválido terminam em `None`, e o contato cai na triagem
(D3). A cadeia tolera um elo quebrado: falha do BrasilAPI **não** impede o
PontoFato.

### 5. Desligável por env, provedor a provedor

`CEP_FALLBACK_ENABLED` (default `true`), `BRASILAPI_ENABLED`,
`PONTOFATO_ENABLED` (+ respectivos `*_BASE_URL`). O rollout é o de sempre
(D13): tudo atrás de flag, `PontoFato` pode sair da cadeia sem tocar no código.

### 6. Etapa 9: E2E de 10.000 contatos com medição de frio × quente

`backend/tests/test_contacts_e2e.py` roda o pipeline inteiro pelos serviços de
aplicação (sem HTTP):

```
parse (.vcf) → upsert em blocos → job GEOCODE → preview → job APPLY → formatação
```**Não toca a rede** (provedor `MockGeocodingProvider`, contável), então o
"frio × quente" é medido em **requisições ao provedor** — a métrica que o
ADR-0004 usa para dimensionar o frio — e não em milissegundos de internet. O
teste está marcado como `slow` (registrado em `pytest.ini`) porque leva ~2,5 min;
é o gate da etapa 9, rodado explicitamente.

### 7. A origem do geocode aparece na triagem

O fallback de CEP só é seguro se quem aplica o lote souber onde ele foi usado: a
coordenada do CEP é de **trecho**, não da casa. Então a triagem do renomeador
passou a mostrar a origem:

- `ContactOrganizer.geocode_origem()` → `GET /whatsapp/contacts/organizer/geocode-origem`
  devolve `por_origem` (OSM × CEP), `por_status` (D3) e a **lista das ruas
  resolvidas por CEP** (com o provedor), limitada por `limite` — o resumo é
  sempre completo, só a lista é cortada.
- A tela (`ContactsRenamerPage`) ganhou o card **“Origem do endereço”** com os
  badges OSM/CEP e as ruas do fallback.
- A classificação é pelo `geocode_cache.provider`, não por ter coordenada: um
  **negativo** cacheado do Nominatim continua contando como OSM (a ausência de
  resultado é informação do OSM, não do CEP).

## Medição (2026-09-29)

10.000 contatos · 200 ruas distintas · SQLite em memória · provedor mock.
Os tempos medem **o nosso código**, não a latência da internet.

```
== Etapa 9 - medicao (10.000 contatos / 200 ruas) ==================
  parse    :    0.48s
  upsert   :    6.49s  (20 blocos de 500)
  FRIO     :   77.02s  | 200 requisicoes (200 ruas x 1) | 101 faixas de ate 100
  QUENTE   :   10.03s  | 0 requisicoes (cache por rua)
  apply    :   45.52s  | 21 faixas de ate 500
  economia : 200 requisicoes no frio -> 0 no quente
```

Leitura contra os alvos do §4.4:

| Métrica | Alvo | Medido | Situação |
|---|---|---|---|
| Upsert 10k | < 2 min | 6,5 s | ✅ |
| Apply 10k | < 5 min | 45,5 s | ✅ |
| Requisições no frio | nº de ruas | 200 ruas → 200 | ✅ (D12) |
| Requisições no quente | 0 | 0 | ✅ |
| Faixa por request | ≤ limite | ≤ 100 / ≤ 500 | ✅ (bounded-batch) |

## Achado colateral relevante (cache × enriquecimento)

Durante o E2E apareceu um comportamento que **não** é bug do fallback, mas que
quem operar precisa saber: `geocodificar_cliente` **preenche** `cidade`/`uf` do
contato com o default (`contacts.default_city`/`default_uf`, D11) e com o que o
provedor devolveu. Se o `.vcf` não traz UF **e** o default não está semeado, a
chave do cache (que inclui UF) muda entre a 1ª passada e a 2ª — o "quente" deixa
de ser quente para essas ruas.

Em produção **não ocorre**: os defaults estão semeados com os fatos do cliente
(§17.1 — Belém/PA), então o UF que o provedor devolve coincide com o default e a
chave é estável. Foi exatamente por isso que o E2E semeia os defaults: medir com
a configuração real, não com uma configuração que não existe. **Não foi feita
nenhuma mudança na `chave_rua`** (contrato congelado) — registra-se o fato.

## Consequências

- Um logradouro que o OSM não conhece e **tem CEP** deixa de virar
  `NAO_ENCONTRADO`: vira `OK` com coordenada de trecho e origem auditável.
- Um logradouro sem CEP e sem cidade/UF continua em triagem — a cadeia não
  inventa (D2), apenas usa o que existe.
- Nenhuma tabela nova, nenhuma migration nova, nenhuma dependência Python nova;
  `alembic heads` segue com um único head.
- A escala de 10k deixou de ser promessa: tem teste, tem número e tem alvo
  comparado.

## Medição ao vivo (opt-in) — e a correção do §4.1

`tests/test_contacts_geocode_live.py`, rodado com `LIVE_MODE=true`, bate nos
provedores **reais** (Nominatim público + ViaCEP + fallback de CEP). Resultado de
2026-09-29, 5 ruas de Belém — a 1ª rodada aparece abaixo; o teste foi repetido
mais 4 vezes no mesmo dia (ver a faixa logo após o bloco):

```
== Geocode FRIO real (Nominatim publico, 1 req/s) =================
  ruas medidas : 5
  FRIO         :  10.01s  |  2.00s por rua
  QUENTE       :   0.01s  | 0 requisicao nova (cache por rua)
  alvo 4.1     : ~5s para 5 ruas (1 s/rua)
  por rua:
    OK               Passagem Ivan Leão
    OK               Travessa São Roque
    OK               Rua 8 de Maio
    OK               Estrada do Outeiro
    OK               Avenida Augusto Montenegro

== Fallback de CEP real (endereco de aceite) =====================
  cep      : 66811120
  provedor : brasilapi
  endereco : Passagem Ivan Leão / Agulha (Icoaraci) - Belém/PA
  lat,lng  : -1.45583, -48.50444

== Logradouro que o OSM nao conhece ===============================
  rua      : Rua Que Nao Existe Nenhum 12345
  status   : OK
  origem   : CEP (fallback)
```

Quatro rodadas seguintes, mesmas 5 ruas: **FRIO 4,76–4,81 s (0,95 s/rua)**, QUENTE
0 requisição.

**Achado que muda uma conta do §4.1.** O prompt estima o frio em **~1 s/rua**.
Medido: **0,95 s/rua** em quatro rodadas e **2,00 s/rua** numa quinta — mesmas 5
ruas, mesmo dia. A causa **não** é o ViaCEP: consultando o Nominatim direto
(`curl`), as 5 ruas voltam **com `postcode`** — o mesmo campo que o §17.1 usa para
achar o CEP do depósito —, logo o 2º elo nem é chamado. A causa é a **latência**:
o limitador marca `_last_call` **depois** da resposta (`http_provider._executar`)
e dorme 1 s a partir dali, então cada rua custa `1 s + latência`. Com ~1 s de
latência por requisição as 5 ruas custam ~10 s; com rede boa, ~4,8 s.

Consequência prática: o alvo de **15 min de frio** corresponde a **~900 ruas** na
rede boa e a **~450 ruas** na rede lenta — uma faixa, não um número. O gatilho do
Photon (§4.2) anda junto. Onde o OSM **não** trouxer `postcode`, o ViaCEP soma
**+1 s** naquela rua (o parêntese do §4.1).

> **Amostra pequena (n=5) e rede não controlada.** O que está provado é a
> *propriedade* (intervalo contado a partir do fim da resposta; no máximo 1 req/s
> por provedor) e o `postcode` presente nas 5 ruas consultadas; o segundo exato
> varia com a rede. Repetir é barato (`LIVE_MODE=true … -k frio`) — foi assim que
> a medição única deste ADR virou faixa.

## Limites do que está provado (não ler como medido)

- O E2E de 10 mil mede **o nosso pipeline** (mock). A latência real tem a medição
  ao vivo acima — indicativa, n=5.
- O teste ao vivo é **opt-in** (`LIVE_MODE=true`) e não roda em CI: sem rede, o
  comportamento honesto é triagem (D2), e o teste aceita esse resultado.
- O caminho do fallback usa **fakes injetados** nos testes de unidade; os dois
  clientes reais foram provados por `curl` no catálogo, **não** por teste
  automatizado contra a rede (o suite não sai para a internet).
- O PontoFato é **B** no catálogo (termos não publicados de forma explícita):
  entra como 3º elo e pode ser desligado com `PONTOFATO_ENABLED=false`.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Trocar o Nominatim pelo PontoFato/BrasilAPI | Eles resolvem CEP, não logradouro livre — não cobrem o caso de uso (ADR-0004) |
| Passar a coordenada do CEP como resultado "normal" (sem origem) | Misturaria trecho de CEP com logradouro do OSM no mesmo cache, sem auditoria |
| Colocar o CEP na `chave_rua` | Quebraria o contrato congelado (§7) e duplicaria linhas para o mesmo logradouro |
| Usar `Geonames`/`REST Countries` como fallback | Rejeitados no catálogo: exigem chave (401) |
| Não expor a origem na triagem | O operador aplicaria um lote com coordenada de trecho sem saber — e não teria como conferir qual rua veio do CEP |
| Fallback dentro do job (`jobs.py`) e não no serviço | O job é orquestração de faixa; a regra de resolução pertence ao `GeocodingService`, que já é o dono do cache |
| Assertar tempo de parede no E2E | Flaky em CI; o teste trava as **propriedades** (1 req/rua, 0 no quente, faixa limitada) e publica o tempo |
