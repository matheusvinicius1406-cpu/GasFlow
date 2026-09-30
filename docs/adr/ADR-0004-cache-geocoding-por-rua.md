# ADR-0004 — Cache de geocoding por RUA + interseções para "entre ruas"

**Status:** Aceito · **Data:** 2026-09-25 · **Fase 2 (§7/§8 — REV. 6)**
**Relacionado:** `docs/adr/ADR-0001-renomeador-contatos-vcf.md`,
`docs/adr/ADR-0003-importacao-contatos-em-lote.md`,
`docs/prompts/renomeador-contatos-fase2.md`

---

## Contexto

10.000 contatos por arquivo (D4). A geocodificação é o passo mais caro do
pipeline e o único que depende de terceiros.

Duas armadilhas se somam:

1. **Chave errada.** Cachear por **endereço completo** (rua + número) faria uma
   requisição por contato. Em uma revenda, a esmagadora maioria dos contatos
   concentra-se em dezenas de ruas — cachear por endereço completo é pagar
   10.000 requisições por um dado que tem ~50 valores distintos.
2. **`entre_ruas` não é um atributo da rua.** "Rua A e Rua B" depende do
   **número**: o mesmo logradouro produz pares diferentes em cada trecho. Se o
   cache guardasse o par pronto por rua, todos os contatos da rua receberiam o
   mesmo par — errado, e pior: errado em silêncio.

Além disso o OSM-BR **quase não tem número de casa** (§15), então resolver
"entre" por reverse-geocoding do número não é alternativa viável.

## Decisão

1. **A chave do cache é a RUA**, não o endereço:
   `chave = sha256(normalize(rua|bairro|cidade|uf))`. 10.000 contatos em ~50
   ruas ⇒ **~50 requisições** ao provedor em vez de 10.000.
2. **O cache guarda as interseções** (`intersecoes`, JSON): as vias que cruzam o
   logradouro, cada uma com o número de casa do cruzamento.
3. **O "entre A e B" é montado em memória, por contato**, projetando o número
   sobre o eixo e escolhendo as **duas interseções que o cercam**. O par nunca é
   lido do cache — é derivado dele.
4. **Cache global, sem `tenant_id`** (ver §"Por que sem `tenant_id`").
5. **Provedores plugáveis** atrás do contrato já existente em
   `app/domain/delivery/routing.py` (`geocode()`): `NominatimProvider`
   (default), `PhotonProvider` (self-host) e `MockGeocodingProvider`. Um segundo
   contrato de geocoding no domínio seria uma segunda verdade.
6. **Taxa e resiliência explícitas**: 1 requisição/s (política de uso do
   Nominatim público), timeout configurável, retry com backoff, `User-Agent`
   identificando o app, e **o mesmo `CircuitBreaker` do OSRM reusado**. Falha
   **nunca** derruba o lote: o contato sai com `geocode_status = PENDENTE`
   (falha transitória) ou `NAO_ENCONTRADO` (o provedor respondeu e não achou) —
   D3.
7. **CEP**: `postcode` do OSM primeiro; ViaCEP só como fallback e só quando
   houver `cidade`/`uf` (o ViaCEP é indexado por CEP, não por endereço).
8. **Cache negativo**: um logradouro que o provedor não conhece também é
   gravado (linha com `lat`/`lng` nulos). Sem isso, a mesma rua não encontrada
   seria reconsultada a cada contato que a usa — exatamente o custo que o cache
   existe para evitar. `lat IS NULL` é o marcador de "negativo já perguntado".

## Por que sem `tenant_id` (vai ser questionado)

`geocode_cache` é a única tabela do renomeador **sem `tenant_id`**, e isso é
deliberado:

- **O dado não é do cliente.** É o que a rua "Rua Berredos, Osasco/SP" é no
  OpenStreetMap. Dois tenants que atendam a mesma cidade teriam, na melhor das
  hipóteses, linhas idênticas duplicadas.
- **A chave não referencia cliente.** É `sha256(endereço normalizado)` — não há
  `client_id`, telefone, nome nem qualquer identificador de pessoa na tabela.
  O que ela associa é *endereço → coordenada pública*.
- **O custo evita a duplicação.** Com `tenant_id`, N tenants na mesma cidade
  multiplicariam requisições ao provedor público por N — pagando N vezes pelo
  mesmo dado e martelando um serviço comunitário.

O que **seria** vazamento é o inverso: guardar *quais contatos* moram em cada
rua. Isso não existe aqui — e não deve passar a existir. A associação
contato↔endereço vive em `clients`, que é por tenant como todo o resto.

## LGPD

Os endereços dos contatos **saem para terceiros**: `nominatim.openstreetmap.org`
(ou o Photon self-host), Overpass (etapa 6) e `viacep.com.br`. Consequências
operacionais já embutidas no código:

- O `User-Agent` identifica o app (`GEOCODING_USER_AGENT`) — rastreabilidade da
  origem das consultas, exigida pela política do Nominatim.
- **Não se loga endereço em claro.** Os logs carregam a URL e a **chave** (hash)
  ou o status, nunca o logradouro junto com o contato.
- `.vcf` não é persistido (D6) e `lat`/`lng` ficam documentados como dado de
  localização do cliente.
- Só o **logradouro** vai para o provedor. O número da casa é usado localmente
  pelo formatter (etapa 7) e pelo cruzamento; ele não sai na consulta de rua.

## Contrato de `intersecoes` — CONGELADO (etapa 6)

```python
intersecoes = [{"nome": str, "numero": int}, ...]   # ordem crescente de numero
```

- Vive no cache (coluna JSON), no `GeocodeResult` e em `escolher_entre_ruas()`.
- **Não muda depois desta etapa.** Há teste de contrato
  (`TestContratoIntersecoes`) travando o formato e o tratamento de itens
  malformados: mudar o formato invalida o cache já gravado em produção.
- **Estado hoje: sempre vazio.** Nem o Nominatim nem o Photon devolvem as vias
  que cruzam um logradouro — os dois provedores preenchem `intersecoes=[]` **de
  propósito**. Preencher com palpite seria inventar "entre ruas" (D2). Quem
  preenche é o Overpass, na etapa 6.

### Plano para o caso majoritário (etapa 6) — obrigatório

O OSM-BR quase não tem número de casa. Se o provider devolvesse só a posição
geométrica do cruzamento, o contrato congelado (que exige `numero: int`) não
teria o que gravar — e "entregar interseção sem número" **não fecha a etapa**.

O caminho escolhido é **(a) estimar por interpolação com âncoras**, já
implementado e testado nesta etapa:

- `infrastructure/geocoding/axis.py::estimar_numero(posicao, ancoras)` — com
  **≥2 âncoras** (pontos do logradouro com posição no eixo *e* número
  conhecidos), o número de qualquer posição intermediária sai por interpolação
  linear;
- fora da faixa coberta devolve `None` — **extrapolar número de casa é chute**;
- o provider Overpass **omite** o cruzamento cujo número não deu para estimar.
  Ele nunca entra na lista com `numero` nulo ou aproximado.

**(b) é a consequência aceita e documentada** deste desenho: rua sem âncoras
suficientes produz `intersecoes` vazias ⇒ "entre" vazio ⇒ **triagem**. Isso é
compatível com a D2 ("nunca inventar"), mas tem custo operacional real que
precisa ser medido na etapa 9: **o caso majoritário hoje é triagem, não
formatação completa**. Ninguém deve ler "entre ruas implementado" como "entre
ruas resolvido para a base toda".

### De onde vêm as âncoras (quem as produz é o Overpass, na mesma query)

`estimar_numero` está pronto e testado, mas está **órfão** sem quem entregue as
âncoras. O provider Overpass (etapa 6) as busca numa **única query**, que traz
três coisas:

1. **a via do logradouro** — `way["name"=…]` com geometria (seqência de nós
   lat/lon), localizada por bbox a partir do `lat`/`lng` já cacheado;
2. **as vias que a cruzam** — `way` com `highway` + `name` em volta do
   logradouro (`around`, raio `ENTRE_RUAS_RADIUS_M` = 150 m), menos a própria;
3. **os nós `addr:housenumber`** próximos ao logradouro — **essa é a fonte das
   âncoras**.

Daí a conta, toda local (nenhuma requisição extra):

- **posição no eixo** = distância normalizada (0..1) do ponto projetado sobre
  a polilinha do logradouro. Vale para âncora **e** para cruzamento.
- **âncoras** = `(posição, addr:housenumber)`. **<2 âncoras ⇒ `intersecoes=[]`**
  (D2). Nó que projeta para fora do eixo (deslocamento perpendicular acima da
  tolerância) é **descartado** — senão uma casa da via transversal viraria
  âncora errada.
- **cada cruzamento** = posição → `estimar_numero(posicao, ancoras)` →
  `{"nome": str, "numero": int}`. `None` ⇒ **cruzamento fica fora da lista**.
- lista ordenada por `numero`, **mantendo só o trecho entre a primeira e a
  última âncora**; **<2 itens ⇒ `[]`**.

O que **não** entra: número aproximado, extrapolação além das âncoras ou
cruzamento sem número — nada é inventado (D2), e um provider que entregue
cruzamento sem `numero` **não fecha a etapa 6**.

Tolerância de deslocamento lateral, bbox exato e forma da consulta Overpass são
**decisão de implementação da etapa 6** — precisam de teste, não de suposição.

## Orçamento de tempo do geocode frio (o "frio < 15 min" não fecha em 1 req/s)

O DoD original dizia "geocode frio < 15 min" como se o limite fosse o volume da
base. Não é: em cache-por-rua o limitante é o **teto de 1 requisição/s da
política do Nominatim público**.

Com o rate limit do próprio código (`GEOCODING_RATE_LIMIT_S=1.0`):

| Ruas distintas | Piso do geocode frio |
|---|---|
| 500 | ~8 min |
| **~900** | **~15 min** |
| 1.500 | ~25 min |

Com **retry**, uma rua que falha custa +1 s +2 s (backoff 1 s/2 s antes da 3ª
tentativa). Com o **ViaCEP** entrando (postcode ausente no OSM + cidade/uf
presente), some até +1 s/rua, porque o cliente do ViaCEP tem o seu próprio
limitador — as duas séries se somam.

**DoD reescrito como função do nº de ruas distintas** (não como constante):

> geocode frio ≈ **nº de ruas distintas × 1 s**, mais ~1 s/rua onde o ViaCEP
> entrar. Ou seja: **≤ 15 min até ~900 ruas** (ou ~450 ruas com ViaCEP em
> todas); acima disso o resultado é **parcial por construção**, e o job da etapa
> 8 retoma de onde parou — o excedente vira triagem, não erro.

**Escapatória documentada (D8):** passando de ~900 ruas, a resposta é
**antecipar o Photon self-hosted** — não há teto de 1 req/s numa instância
própria. É uma troca de configuração, não de código:
`GEOCODING_PROVIDER=photon` + `GEOCODING_BASE_URL` (o `PhotonProvider` e o
`factory` já entregam isso). Enquanto não for antecipado, o número honesto é o
da tabela acima.

### Decisão de orçamento: o Overpass fica FORA do geocode frio (opção 2)

O Overpass é uma **segunda requisição por rua**, e o rate limit é por
**instância** (`RateLimitedHttp._last_call` é de cada provider, não global).
Nominatim e Overpass teriam limitadores separados rodando **em série dentro da
mesma rua**, então o custo por rua dobraria:

| Ruas distintas | só geocode (§acima) | + Overpass em série |
|---|---|---|
| 500 | ~8 min | ~17 min |
| **~900** | **~15 min** | **~30 min** |
| 1.500 | ~25 min | ~50 min |

O limiar do Photon cairia de ~900 para ~450 ruas — e o alvo de 15 min deixaria
de ser verdadeiro. Pior: esse segundo pedágio seria pago **também** no caso
majoritário (sem âncoras ⇒ `intersecoes=[]`), ou seja, pagaria 1 s/rua para
descobrir que não há interseção.

**A escolha registrada é a opção 2 — "sob demanda":**

1. **O geocode frio (etapa 5) não chama Overpass.** É rua + ViaCEP só; a tabela
   acima continua valendo, **≤ 15 min até ~900 ruas**.
2. **O Overpass roda em passada própria**, orquestrada na etapa 8, com
   contagem, orçamento e retomada **separados**. Falhar ali não muda
   `geocode_status` de ninguém — vira `intersecoes` vazia ⇒ triagem (D2).
3. **O passe Overpass é um UPDATE da coluna `intersecoes` de linha já
   existente.** Ele não cria linha (criar uma com `lat`/`lng` nulos gravaria um
   *negativo* falso e derrubaria o cache) e não toca em `lat`/`lng`/`cep`.
   Linha ausente ⇒ a rua ainda não geocodificou ⇒ pula.

**O alvo de 15 min é do geocode frio, não do pipeline completo.** O passe do
Overpass tem alvo próprio, medido na etapa 9; o pipeline completo (frio +
interseções) **soma os dois**. É isso que o §4 do prompt precisa dizer — e não
um "< 15 min" valendo para tudo, que é a contradição que este ADR corrige.

Rejeitadas: **opção 1** (juntar os dois no mesmo orçamento — limiar do Photon
cairia para ~450 ruas e o alvo de 15 min deixaria de ser verdadeiro);
**opção 3** (um limitador compartilhado — impede pico, mas as chamadas seguem
em série e **não economiza tempo nenhum**).

## Consequências

- Custo de rede proporcional ao **número de ruas distintas**, não ao número de
  contatos — mas o **tempo** é limitado pela política do provedor público, como
  na tabela acima.
- `intersecoes` entra no schema (`JSON`) já na v7, mesmo que o preenchimento só
  chegue na etapa 6: sem a coluna, a etapa 6 exigiria migration nova e o cache
  já gravado ficaria sem espaço para o dado.
- Cache **stale** por rua é aceitável: logradouros não mudam de coordenada. Não
  há TTL nem invalidação na Fase 2.
- **Resiliência reusa o `CircuitBreaker` do OSRM**
  (`infrastructure/routing/circuit_breaker.py`), não uma segunda estratégia de
  falha. O que difere é só o **fallback**, e ele difere porque o domínio é
  outro: rota tem `HaversineRoutingProvider` local para cair, geocoding não tem
  — "onde fica esta rua" só o provedor sabe. Então breaker aberto ⇒ nenhuma
  tentativa ⇒ `PENDENTE` no contato ⇒ triagem. Nunca um endereço chutado.

## Limites do que está provado (não ler como medido)

- **"Falha do provedor não derruba o lote" está provado em UNIDADE.** O
  `GeocodingService` devolve status em vez de levantar, e há teste disso. **Não
  existe chamador em lote ainda** (é a etapa 8): não há prova ponta a ponta de
  que 10.000 contatos sobrevivem a um provedor fora do ar.
- **`CONTACT_RENAMER_ENABLED` e `ENTRE_RUAS_RADIUS_M` estão declarados e
  inertes.** Ninguém os lê hoje — nenhum endpoint responde 409 (etapa 8) e
  nenhuma busca por raio roda (etapa 6). *Flag declarada não é flag em vigor.*
- **O ViaCEP está morto até a pendência §12.1 do prompt.** Sem
  `contacts.default_city`/`contacts.default_uf` preenchidos, a guarda "só com
  cidade/uf" nunca deixa a chamada passar. Os testes provam o **código** (com
  cidade/uf injetados), não o **comportamento em produção**.
- **Geocode frio/quente não foi medido.** Não há job (etapa 8), então os alvos
  do §4 continuam sendo alvo — a conta acima é aritmética do rate limit, não
  medição.
- **A passada do Overpass (opção 2) ainda não existe.** Não há provider nem
  job: a decisão de orçamento acima é de **desenho**, e a tabela dela é
  aritmética do rate limit por instância, não medição. Quem entrega é a etapa 6
  (provider) + etapa 8 (job). Enquanto isso, `intersecoes` segue vazia.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Cache por endereço completo (rua+número) | ~10.000 requisições em vez de ~50; o OSM-BR não tem número mesmo |
| Guardar `entre_ruas` pronto no cache da rua | Todos os números da rua herdariam o mesmo par — errado e silencioso |
| Reverse-geocoding do número pelo OSM | OSM-BR quase não tem número de casa (§15) — devolveria vazio e custaria 1 req/contato |
| `tenant_id` no cache | Dado público multiplicado por tenant; N tenants = N vezes o mesmo dado e N vezes o provedor comunitário |
| Cruzamento sem número entrando com `numero` nulo | Quebraria o contrato congelado e faria a derivação devolver `None` em silêncio, parecendo funcionar |
| Provedor devolvendo número aproximado sem âncora | Extrapolação de número de casa é chute — proibido por D2 |
| Breaker próprio para geocoding | Dois provedores HTTP com estratégias de falha diferentes é dívida; a classe do OSRM já serve |
| Overpass dentro do geocode frio (mesmo orçamento) | Dobra o custo por rua (limitador por instância) e derruba o limiar de ~900 para ~450 ruas — pagando o pedágio também no caso que não produz nada |
| Limitador compartilhado Nominatim+Overpass | Impede pico, mas as chamadas seguem em série: não economiza tempo nenhum |
| Cachear falha transitória (timeout) | Marcaria uma rua como inexistente por causa de uma queda momentânea do provedor |


---

## Resultado do spike T3/T4 — REV. 7 (2026-09-25)

Medido, não estimado. 5 ruas de Belém-PA, pipeline real do repo
(`axis.py::estimar_numero` + `geocoding.py::escolher_entre_ruas`), não reimplementação.
Endpoint `https://overpass-api.de/api/interpreter`, `timestamp_osm_base`
variedade por rodada — a mais recente `2026-09-25T17:39:51Z`.

| Rua | âncoras brutas → úteis | faixa do eixo coberta | inversões de nº | cruzamentos c/ nº estimável | `entre` (alvo) |
|---|---|---|---|---|---|
| Passagem Ivan Leão (aceite) | 64 → **34** | 0,00–0,53 | 19 | 3 de 6 | **`null`** (45) |
| Rodovia Augusto Montenegro | 10 → **0** | — | 0 | 0 de 19 | `null` |
| Rua 8 de Maio | 37 → **16** | 0,00–0,81 | 6 | 16 de 16 | `null`¹ |
| Travessa São Roque | 44 → **19** | 0,00–1,00 | 10 | 7 de 7 | `null`¹ |
| Travessa dos Berredos | 139 → **35** | 0,00–1,00 | 17 | 27 de 27 | `null`¹ |

¹ alvo arbitrário menor que a menor âncora — artefato do teste, não do dado.

**Portão T4 (§8.0.3): não dispara.** 4 de 5 ruas têm **≥2 âncoras úteis**; há dado
real, então não é o caso "pipeline que devolve vazio". Só a Rodovia Augusto
Montenegro ficou em 0 (10 nós `addr:housenumber` descartados por projetarem
fora do eixo) — é **rua sem dado**, não **base sem dado**.

### O caso de aceite NÃO se reproduziu

`escolher_entre_ruas(intersecoes, 45)` → **`null`**, não `"entre Berredos e
Andradas"`. O OSM mostra **6** cruzamentos nomeados da Passagem Ivan Leão:

`Passagem Pedro Alvares Cabaral` · `Rua José Soares Montenegro` ·
`Rua Menino Deus` · `Travessa Santa Maria` · `Travessa Souza Franco` ·
**`Travessa dos Berredos`**

- **"Andradas" não existe** como cruzamento dessa via no OSM (nem como sufixo
  de busca no Nominatim — `"Passagem Ivan Leao com Agulha, Belem, PA"` → 0).
- **"Travessa dos Berredos" existe**, mas está **fora da faixa das âncoras**
  (faixa termina em 0,53) → `estimar_numero` devolve `None` → sai da lista.
- Os 3 cruzamentos que receberam número são 120, 330 e 1111 — **todos > 45**,
  então `abaixo` fica vazio e `escolher_entre_ruas` cai em `None` (D2).

Consequência: **o critério de aceite do §8.0.1 não é verificável com dado
público** e a hipótese original foi registrada como não reproduzida. Não é
motivo para mudar o dado nem para mexer no contrato — é motivo para a etapa 9
medir `% com `entre` preenchido` em vez de assumir o par esperado.

### Qualidade das âncoras (limite medido, não suposto)

- **Inversões de número** em 4 das 5 ruas (6 a 19). Ex.: Travessa dos Berredos
  começa `728, 1074, 1078` **no mesmo ponto 0,00** e depois cai para `302`;
  Rua 8 de Maio começa `726, 750, 715, 737`. Tolerância lateral de 40 m é
  generosa e puxa casa de via paralela/transversal — **a tolerância e o filtro
  de monotonicidade viram teste na etapa 6**, não suposição.
- **Colapso de números:** em Rua 8 de Maio **10 dos 16** cruzamentos recebem
  `726`; em Travessa dos Berredos **8 dos 27** recebem `728`; em São Roque 3
  recebem `610` e 3 recebem `1021`. Plateau de âncoras duplicadas na mesma
  posição ⇒ interpolação constante ⇒ empate no `sort`.
- **Duplicatas:** o mesmo cruzamento entra 2× (ex.: `Rua 2 de Dezembro`,
  `Rua 15 de Agosto`) porque a via transversal compartilha vários nós com o
  logradouro. O provider precisa **deduplicar por nome** antes de ordenar.
- **Faixa incompleta:** só 53% da Ivan Leão e 81% da 8 de Maio ficam cobertas.
  Cruzamento fora da faixa ⇒ fora da lista (comportamento previsto), mas a
  **% de cobertura do eixo** entra na métrica do §8.5 junto com a de âncoras.

### Operação do Overpass (medido)

- **1 query combinada morre; 3 queries separadas + retry passam.** O
  `overpass-api.de` devolve 504/429 em rajada; `timeout:60` numa query só com
  as três partes não passa. A etapa 6 deve tratar **retry + possível divisão**
  como decisão com teste, não como acidente.
- Instâncias: `overpass-api.de` é a única planetária estável; `private.coffee`
  respondeu com `osm_base 2026-05-06` (**4 meses defasado**) numa rodada —
  **validar `timestamp_osm_base`** antes de confiar; `osm.ch` não tem dado
  planetário (devolve `117272`); `maps.mail.ru` é planetário porém com
  latência de 28 s+.
- Custo por rua: **13 s a 895 s**, mediana acima de 300 s puxada pelos
  retries. Confirma o D14: Overpass **não** cabe no geocode frio.

### Raio: cobertura ≠ query

Os 20 km de **cobertura** do cliente são distância haversine do depósito
(classificação dentro/fora do raio de atendimento). **Não é raio de query.**
`around:20000` é proibido: a consulta por rua usa `around:150` para cruzar e
`around:80` para âncoras, como já está no §8.2.
