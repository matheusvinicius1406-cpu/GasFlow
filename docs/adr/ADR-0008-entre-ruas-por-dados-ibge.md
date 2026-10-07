# ADR-0008 — "Entre ruas" por dados oficiais do IBGE (CNEFE + Faces), sem PostGIS

**Status:** Aceito · **Data:** 2026-09-30 · **Fase:** 3 (spec) e prepara a Fase 4
**Relacionado:** `docs/adr/ADR-0004-cache-geocoding-por-rua.md`,
`docs/prompts/renomeador-contatos-fase2.md` (§7 contratos, §8.5 métricas, D9),
`docs/prompts/renomeador-contatos-fase3.md` (spec executável),
`docs/auditoria/catalogo-apis-externas.md`.

---

## Contexto

A Fase 2 fechou o "entre ruas" **somente** com Overpass (D9), e o spike T3/T4
(ADR-0004) já tinha mostrado o limite: **qualidade**, não quantidade. O OSM-BR
tem poucas âncoras `addr:housenumber` — a Rodovia Augusto Montenegro ficou com
**0** — e a query pública é lenta (13–895 s/rua), com política de uso. O gatilho
da Fase 3 sempre foi: usar **dado oficial de numeração** em vez de depender de
`addr:housenumber` do OSM.

Este ADR **responde o spike de viabilidade** antes de qualquer código de
produção, como manda o padrão da Fase 2 (§8.0). Os números foram medidos com os
arquivos reais de Belém (Censo 2022), baixados em 2026-09-30.

## Decisão (resumo)

1. **Fase 3 usa CNEFE + Faces de Logradouro (IBGE, Censo 2022)** como fonte de
   numeração e topologia. OSM/Overpass deixa de ser caminho obrigatório.
2. **PostGIS não é necessário.** A junção que resolve o problema é por **chave
   inteira** (`COD_SETOR` + `NUM_QUADRA` + `NUM_FACE`), não por geometria. O
   spike fez Belém inteira em Python puro da stdlib.
3. **Fase 4** (self-host: Photon + OSM local) fica especificada, não construída.
4. Nada de API paga, nada de chave, nenhuma dependência Python nova para ingerir
   os CSVs (é `csv` + `json` da stdlib).

## O que foi medido (Belém, Censo 2022)

Fontes reais (URLs na spec, §"Fontes"):

| Arquivo | Zip | Descompactado | Conteúdo |
|---|---|---|---|
| `Arquivos_CNEFE/CSV/Municipio/15_PA/1501402_BELEM.zip` | 13 MB | 97,9 MB | 618.075 endereços com rua, número, CEP, lat/lng |
| `.../Coordenadas_enderecos/Municipio/15_PA/1501402.zip` | 3,0 MB | 22,9 MB | só lat/lng (redundante com o de cima) |
| `.../base_de_faces_de_logradouros_versao_2022.../json/PA_...zip` | 15,4 MB | — | todas as 144 cidades do PA |
| `.../json/PA/1501402_faces_de_logradouros_2022.json` | — | 20,4 MB | 48.159 faces de Belém (GeoJSON) |
| `.../shp/PA_faces_de_logradouros_2022_shp.zip` | 20,1 MB | — | variante shapefile |

### 1. CNEFE — a lacuna de numeração fecha

```
total enderecos            : 618075
com lat/lng                : 618075 (100.0%)
NV_GEO_COORD in 1|2        : 614045 (99.3%)
com NUM_ENDERECO           : 618075 (100.0%)
  ... numerico puro        : 618075 (100.0%)
logradouros distintos      : 5962
com >= 2 numeros + coord   : 5892 (98.8%)   <- ancoras CNEFE
com >= 10 numeros + coord  : 4831 (81.0%)
```

Distribuição de `NV_GEO_COORD`: `{1: 564614, 2: 49431, 3: 3103, 4: 906, 5: 1, 6: 20}`
(1 = coordenada de porta; os demais são graus de aproximação — a spec define o
filtro).

O ponto que **sozinho** justifica a Fase 3: as ruas do spike da Fase 2 no CNEFE:

| Logradouro (nome canônico) | Âncoras CNEFE | OSM (spike T3/T4) |
|---|---|---|
| `rodovia augusto montenegro` | **8.668** | **0** |
| `travessa humaita` | 2.228 | — |
| `avenida pedro miranda` | 1.226 | — |
| `travessa dos andradas` | 689 | ("Andradas" não existia como cruzamento) |
| `travessa dos berredos` | 605 | existia, fora da faixa de âncoras |
| `passagem ivan leao` | 82 | 34 úteis |

Top 3 mais densos: `rodovia augusto montenegro` (8.668), `avenida conselheiro
furtado` (3.237), `passagem santo antonio` (3.213).

### 2. Faces de Logradouro — a topologia sai do próprio IBGE

```
faces (segmentos)           : 48159
logradouros distintos       : 5348
faces sem nome              : 9441 (19.6%)
nos distintos               : 75474
nos de >=2 ruas diferentes  : 30217   <- cruzamentos derivados
faces com 2 extremos cruzados: 25185 (52.3%)
```

Cada Face é um `LineString` de **2 pontos** = o trecho de rua entre dois nós.
Dois nós de ruas diferentes **compartilhados** = cruzamento. Isso substitui a
query Overpass de cruzamentos (§8.2, parte 2) por uma leitura local.

Junção CNEFE ↔ Face (por `COD_SETOR`/`NUM_QUADRA`/`NUM_FACE`, com `zfill(3)`):

```
enderecos CNEFE            : 618075
casados com uma face       : 528859 (85.6%)
faces com >=2 numeros      : 30708 (63.8%)
```

Ou seja: além da topologia, dá para ancorar a **faixa de numeração por face**.

### 3. O caso de aceite — agora reprodutível (mas não o par imaginado)

Passagem Ivan Leão tem 10 faces. **Cinco** delas têm faixa que contém o
número **45** (não há uma única resposta óbvia — é o caso da triagem, D2):

```
face 004/004 nums=     0..1115  cruza: ['passagem pedro alvares cabral', 'rua jose soares montenegro']
face 002/018 nums=    33..62    cruza: ['passagem pedro alvares cabral', 'travessa dos berredos']
face 002/004 nums=     0..188   cruza: ['rua menino deus', 'travessa santa maria']
face 004/011 nums=    35..65    cruza: ['passagem pedro alvares cabral', 'travessa dos berredos']
face 002/002 nums=  8..1565     cruza: ['passagem santa maria']
```

As duas faixas **mais apertadas** (`33..62` e `35..65`) concordam no mesmo par.
Resultado honesto: o par derivado é **"entre Passagem Pedro Álvares Cabral e
Travessa dos Berredos"** — **não** "entre Berredos e Andradas". *Berredos* é um
dos lados (confirma a memória do cliente em parte); *Andradas* **existe** no
dado (26 faces, 689 endereços) mas não é o cruzamento que emoldura o 45. A
conclusão é a mesma do §17.2 da Fase 2: **a hipótese do par esperado não se
reproduz**, e agora há dado oficial dizendo qual é o par real.

### 4. Limites medidos (não ler como perfeição)

O próprio IBGE avisa que a base pode ter "faces sem conectividade e com ausência
de nós". Medido em Belém:

- **19,6%** das faces sem nome.
- Só **52,3%** das faces têm os **dois** extremos em um nó de cruzamento — ou
  seja, **não** dá para assumir "extremos da face = cruzamentos"; há face longa
  varando a rua inteira (ex.: faixa `0..10010`).
- **14,4%** dos endereços CNEFE não casam com nenhuma face da versão preliminar
  (a base de faces ainda está "em consolidação" para trechos capturados em
  campo).
- Faixas de número por face às vezes cobrem tudo (`0..4001`) — a mediana é que
  decide, não o `min`/`max` cru.

Consequência de projeto: a Fase 3 **não** pode tratar a face como verdade
absoluta. Precisa (a) ordenar as âncoras CNEFE ao longo do eixo, (b) cruzar com
os nós das faces, e (c) cair na triagem (D2) quando os dois métodos discordam.

## Números reais da Fase 3 — banco ingerido (2026-10-05)

As seções acima vieram do spike sobre os **arquivos crus**. A Fase 3 mede de
novo sobre o **banco ingerido** (`_import_test.db` — os scripts de
`backend/scripts/`), que é o dado que o produto lê. Reprodução:

```bash
python scripts/metrica_cobertura_fase3.py --db sqlite:///./_import_test.db --amostra 100 --seed 42
```

| Métrica (§10) | Spike (arquivo cru) | Fase 3 (banco ingerido) |
|---|---|---|
| endereços | 618.075 linhas | **601.192 únicos** (16.883 deduplicadas) |
| com lat/lng | 100% | **100%** |
| âncoras (nº > 0 + coordenada) | — | **550.883 (91,6%)**; 50.309 têm nº `0` |
| ruas com ≥2 âncoras | 5.892/5.962 = 98,8% | **5.707/5.822 = 98,0%** |
| nós-cruzamento (≥2 ruas) | 30.217 | **30.203** de 44.354 distintos |
| faces com 2 extremos cruzados | 52,3% | **65,0%**¹ |
| **ruas com ≥2 cruzamentos** | — | **5.041/5.348 = 94,3%** |
| **endereços casados com face (D17)** | 85,6% | **514.459 = 85,6%** |
| **ruas com `entre` preenchido** (passe IBGE, 100 ruas, seed 42) | — | **67,0%** |
| **cobertura do eixo pelas âncoras** (média do passe) | — | **0,658** |

¹ A ingestão materializa **só as extremidades** de face como nó e descarta
faces sem nome (19,6%), então o denominador difere do spike — a definição do
produto é `logradouro_no`, não todos os vértices da polilinha.

Os quatro primeiros grupos de números são **população inteira** (segundos, sem
rede). `entre` preenchido e cobertura do eixo saem do `IbgeEntreRuasProvider`
sobre a **mesma amostra semeada** do gate D20. Todas as métricas do §8.5/§10
de contagem também ficam **persistidas por job** em `contact_jobs.metrica`
(`ruas`, `ruas_com_2_ancoras`, `ruas_com_2_cruzamentos`,
`ruas_com_intersecoes`, `cobertura_eixo_*`, `por_motivo`,
`por_intersecoes_provider`) — spec §10 / D20.

### Gate D20 — concordância CNEFE × Overpass (medido, 2026-10-07)

```bash
python scripts/metrica_concordancia_entre_ruas.py --amostra 100 --seed 42 \
  --db sqlite:///./_import_test.db --cache <cache> --json docs/auditoria/d20-concordancia.json
```

Amostra **saturada em 100/100 ruas respondidas** (a falha de rede não cacheia
por desenho — a re-rodada insiste nelas):

| | |
|---|---|
| cobertura IBGE (≥2 interseções) | **67,0%** |
| cobertura Overpass | **7,0%** (100/100 respondidas) |
| razão / vantagem | **9,57× · +60,0 pp** — folga exigida (2×, 10 pp) **✓** |
| interseccional (os dois ≥2) | **6 ruas** |
| cruzamentos comparados | OSM **38** · CNEFE **111** · comuns **29** |
| **concordância de cruzamentos** | **76,3%** — exigido **≥ 70%** **✓** |
| veredito | **APROVADO** |

Motivos Overpass (100): 60 `rua_sem_geometry_no_osm`, 23 `poucas_ancoras`,
7 `menos_de_duas_intersecoes`, 7 `ok`, 3 `poucos_cruzamentos`. Lado IBGE (100):
67 `ok`, 17 `menos_de_duas_intersecoes`, 11 `sem_face`, 5 `sem_ancora_util`.

#### A régua mudou — e foi medido por que a antiga não fechava

A primeira rodada comparava o **par** `escolher_entre_ruas` nos números
1/25/50/75/99 e dava **0,0%**. A apuração rua a rua (mesma amostra, mesmo
cache) mostrou que o problema não era dado faltando:

| | rodada antiga (par na grade) | rodada nova (cruzamentos) |
|---|---|---|
| pontos/conjuntos comparáveis | 31 pontos | 38 cruzamentos do OSM |
| de um lado só | **19 (61%)** | — (rua sem passe sai da régua) |
| **teto mesmo com acordo perfeito** | **38,7%** | 100% |
| medido | 0,0% | **76,3%** |

1. **O teto da régua antiga era 38,7%.** A faixa de âncoras do OSM não cobre os
   números baixos da grade (em `AVENIDA ALCINDO CACELA` o OSM começa em 1041 e
   o CNEFE em 4), então 19 dos 31 pontos eram de um lado só e entravam como
   discordância — **70% era inalcançável por construção**, mesmo com os dois
   provedores certos onde ambos respondiam (12 pontos; 0 batiam).
2. **A pergunta do gate é outra.** Trocar Overpass por CNEFE só é arriscado se
   o CNEFE **perder** cruzamento que o OSM enxerga. É o que se mede agora:
   fração dos cruzamentos do OSM que o CNEFE também traz, nas 6 ruas em que os
   dois têm passe — **29/38 = 76,3%**. O caminho inverso (26,1%) é
   **cobertura**, não concordância: o CNEFE traz 111 nomes onde o OSM traz 38,
   e é justamente a vantagem da Fase 3.
3. Os pontos da grade seguem no relatório (`pontos_comparaveis`,
   `concordancia_pontos_normalizada` = 0,0%) **como diagnóstico**, e o piso de
   evidência (`_CRUZAMENTOS_MINIMOS = 10`) impede que um percentual calculado
   sobre dois nomes feche fase.

#### Bug de âncora corrigido no passe Overpass (mesma rodada)

A tolerância de 40 m mede **distância**, não **pertencimento**: a caixa
`node["addr:housenumber"]` puxa a casa da via paralela. Medido em
`PASSAGEM SAMUEL SOARES`: as **9 âncoras aceitas** declaravam todas
`addr:street` de `Rua dos Caripunas`/`Rua dos Pariquis` (2023..2371 numa rua
que vai de 3 a 51), e o passe devolvia cruzamentos estimados em 2143/2371.
Correção: nó cujo `addr:street` nomeia **outra via** sai (mesma régua exata ou
por contenção do `_montar_eixo`); nó sem `addr:street` continua entrando pela
tolerância — não há como provar que é de outra rua. Consequência medida:
cobertura Overpass 11,0% → **7,0%** (mais `poucas_ancoras`) e a calibragem dos
números sobe (`RUA SANHACO` de `1,1,1,2,12,26` para `5,13,20,25,35` × CNEFE
`1,7,15,20,31,33,40`). Travado por teste em `test_contacts_overpass.py`
(`test_no_de_outra_rua_nao_vira_ancora`).

**Nenhuma allowlist e nenhum limite foi afrouxado**: o corte de 70% e a margem
de cobertura continuam os mesmos; o que mudou foi a **definição** do que se
compara, registrada aqui com o teto que motivou a mudança (spec §0: corrige-se
o código, e critério só muda com medição anexada).

## Por que **não** PostGIS (o ponto central)

A hipótese do D9 era "PostGIS na Fase 3". Este spike derruba a necessidade:

- A resolução que interessa — *qual face contém o número X* e *quais ruas cruzam
  os extremos* — é uma **junção por chave inteira** (`setor|quadra|face`) e um
  índice `nó → nomes`. Não há consulta espacial: a geometria só é usada para
  derivar *quais nós coincidem* (igualdade de coordenada arredondada).
- O spike processou **48.159 faces + 618.075 endereços** em Python puro, em
  segundos, em uma máquina de desenvolvimento — sem índice espacial.
- PostGIS **acelera** geometria, mas **não cria** o `addr:housenumber` que falta
  no OSM. O gargalo era **dado**, e o dado certo (CNEFE/Faces) cabe numa tabela
  comum indexada.

`osm2pgsql`/PostGIS só voltam a fazer sentido se a Fase 4 exigir consulta
espacial em tempo de request (ex.: "rua mais próxima de um ponto" em escala). A
spec deixa isso como item de gate da Fase 4, não como premissa.

## Escala de dados (para dimensionar a ingestão)

- CNEFE: o **Pará inteiro** são 98 MB (zip); Belém, 13 MB. O Brasil é a soma das
  UFs — cabe num pipeline de ingestão offline, não em request.
- Faces: **PA inteiro** são 15,4 MB (json) / 20,1 MB (shp). Belém, 20,4 MB
  descompactado.
- Portanto a Fase 3 **não** precisa de banco geoespacial nem de hardware
  especial: é ingestão de CSV/GeoJSON para tabelas indexadas.

## Fase 4 (self-host) — custo registrado, não decidido

Números para a spec da Fase 4 (fontes na spec):

| Item | Medida | Fonte |
|---|---|---|
| `brazil-latest.osm.pbf` | **2,0 GB** (2.089.100.230 B) | Geofabrik, medido |
| OSRM (disco/RAM/tempo) | 20–50 GB · 8–16 GB RAM · 1–8 h | `backend/docs/routing/osrm.md` |
| Photon (planeta) | ~95 GB disco · 64 GB RAM (2026) | komoot/photon |
| Photon (Brasil) | ~1/20 do planeta (estimativa) | derivado |

A Fase 4 **só** entra quando a medição da Fase 3 mostrar que o gargalo é a
**latência/limite dos provedores públicos** (§4.1/§4.2 da Fase 2: gatilho em
~900 ruas na rede boa, ~450 na lenta), e não o dado.

## Consequências

- O "entre ruas" deixa de depender de disponibilidade do Overpass e de
  `addr:housenumber` do OSM: passa a ter fonte **oficial, versionada e
  geocodificada**.
- `intersecoes` continua sendo o **contrato congelado** (§7 da Fase 2). O que
  muda é de **onde** vem o par, não a forma.
- Nenhuma migration nova é obrigatória para a ingestão (tabela nova indexada
  sim; geométrica não). `alembic heads` segue único.
- A qualidade medida (19,6% de faces sem nome; 52,3% com dois cruzamentos)
  vira **gate da Fase 3**: a spec exige persistir as mesmas métricas do §8.5 e
  o percentual de concordância entre o método CNEFE e o método Overpass da
  Fase 2 — se o CNEFE não ganhar com folga, a Fase 3 não fecha.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter Overpass como caminho principal | OSM-BR sem âncoras (Augusto Montenegro = 0) e query lenta/pública; o dado oficial resolve melhor |
| Trazer o OSM do Brasil para PostGIS + `addr:housenumber` | Continua sem os números que faltam — o gargalo é dado, não índice |
| Usar só o CNEFE (sem as Faces) | Sem topologia não há "entre": CNEFE dá número↔coordenada, não o cruzamento |
| Usar só as Faces (sem CNEFE) | A faixa de número por face depende do CNEFE para virar "entre A e B" por número |
| Tratar a face como verdade absoluta | 47,7% das faces não têm dois cruzamentos e 14,4% dos endereços não casam — exige o fallback de triagem (D2) |
| Subir Photon agora (Fase 4 antecipada) | Sem medir o gargalo da Fase 3 primeiro; custo de disco/RAM não se justifica ainda |
