# Renomeador de contatos — Fase 3 (e 4) — "entre ruas" por dados oficiais do IBGE

**Status:** spec de execução · **REV. 1** · 2026-09-30
**Base:** `docs/adr/ADR-0008-entre-ruas-por-dados-ibge.md` (spike respondido),
`docs/adr/ADR-0004-cache-geocoding-por-rua.md`,
`docs/prompts/renomeador-contatos-fase2.md` (contratos §7, métricas §8.5, D9).
**Escopo entregue nesta revisão:** spec + ADR + spike. **Sem código de produção.**

---

## 0. Regras do projeto (valem para tudo aqui)

- **Sem API paga e sem chave.** CNEFE/Faces do IBGE são públicos (ftp/geoftp).
- **Sem dependência Python nova para ingerir** o dado: `csv`, `json`, `zipfile`,
  `unicodedata` da stdlib bastam (medido — ver §4).
- **Sem Celery/RQ/BackgroundTasks:** a ingestão é **offline** (script de carga);
  o request nunca sai para a rede para resolver "entre ruas" (D14 mantida).
- **Nunca inventar** (D2): sem dado ⇒ `intersecoes = []` + triagem.
- **Não commitar/push sem pedido.** **Se um gate falhar, corrige-se o código —
  nunca o allowlist** (gate verde é `19/0`).

## 1. Objetivo

Trocar a dependência do **Overpass público** (`addr:housenumber` do OSM, que em
Belém é escasso) por **dados oficiais do IBGE (Censo 2022)**: o **CNEFE** dá
número↔coordenada e as **Faces de Logradouro** dão a topologia. O produto final
não muda: `geocode_cache.intersecoes` no **contrato congelado** (`[{"nome",
"numero"}]`), consumido pelo `ResolverEntreRuas` que já liga o par ao nome
(commit `83d5fd7`, D12).

## 2. Decisões travadas (novas)

| # | Decisão |
|---|---|
| D15 | Fonte de numeração = **CNEFE 2022** (`Arquivos_CNEFE/CSV/Municipio/<UF>/<cod>_<NOME>.zip`), campo `NUM_ENDERECO` + `LATITUDE`/`LONGITUDE` |
| D16 | Fonte de topologia = **Faces de Logradouro 2022** (GeoJSON por município); **dois nós de ruas diferentes que coincidem = cruzamento** |
| D17 | Junção CNEFE↔Face por **`COD_SETOR` + `NUM_QUADRA.zfill(3)` + `NUM_FACE.zfill(3)`**. **Sem PostGIS** (ADR-0008) |
| D18 | Ingestão é **offline e idempotente** (carga por município); **nada de rede no request** |
| D19 | Resolução por número combina **âncora CNEFE ordenada no eixo** + **nós de face**; discordância/empate ⇒ **triagem** (D2) |
| D20 | **Gate de qualidade:** persistir as métricas do §8.5 **+** a concordância CNEFE × Overpass da Fase 2; se o CNEFE **não ganhar com folga**, a Fase 3 **não fecha** |
| D21 | `geocode_cache.provider` passa a poder registrar **`ibge`** (origem auditável, igual ao `brasilapi`/`pontofato` do ADR-0007) |

## 3. Contratos (congelados — não mudam)

Reaproveita **integralmente** o §7 da Fase 2:

| Contrato | Forma |
|---|---|
| `intersecoes` | `[{"nome": str, "numero": int}]` |
| `GeocodeResult` | lat, lng, rua, bairro, cidade, uf, cep, `intersecoes` |
| `chave_rua` | `sha256(normalize(rua\|bairro\|cidade\|uf))` |
| `estimar_numero(posicao, ancoras)` | interpolação linear; `None` fora da faixa |
| Formatter | §D5 da Fase 2, idempotente (`^\d+\s*=\s*`) |

Se a forma mudar, a etapa **não fecha**. Os testes que travam (`TestContratoIntersecoes`,
`TestInterpolacaoDeAncoras`) continuam valendo.

## 4. Spike — resposta medida (Belém, 2026-09-30)

Números completos no **ADR-0008**. Resumo do que decide a viabilidade:

- **CNEFE Belém:** 618.075 endereços, **100%** com lat/lng e **100%** com número
  numérico; **98,8%** dos 5.962 logradouros com **≥2 âncoras**.
- **Augusto Montenegro:** **8.668** âncoras CNEFE × **0** no OSM (a rua que
  sozinha reprovava o gate da Fase 2).
- **Faces Belém:** 48.159 segmentos; **30.217** nós de ≥2 ruas (cruzamentos
  derivados); junção CNEFE↔face cobre **85,6%** dos endereços.
- **Caso de aceite (Ivan Leão, 45):** agora **resolvível**, com **ambiguidade
  assumida** — 5 faces de Ivan Leão contêm o 45; as 2 faixas mais apertadas
  (`33..62`, `35..65`) concordam no par **"Passagem Pedro Álvares Cabral e
  Travessa dos Berredos"**. O par imaginado ("Berredos e Andradas") **não** se
  reproduz (mesma conclusão do §17.2, agora com dado oficial). A resolução por
  faixa-apertada + triagem é o §6.6.
- **Limites:** 19,6% das faces sem nome; só 52,3% com **dois** cruzamentos;
  14,4% dos endereços não casam com face. ⇒ a face **não** é verdade absoluta.

`Fortaleza`/outras cidades não foram medidas; a spec assume **Belém** como piloto
por causa do `default_city`/`default_uf` (D11).

## 5. Schema (proposta — a etapa 1 decide com teste)

Tabelas **indexadas comuns** (sem coluna geométrica):

| Tabela | Colunas-chave | Índice |
|---|---|---|
| `cnefe_endereco` | `cod_setor`, `num_quadra`, `num_face`, `num_endereco` (int), `nome_logradouro` (canônico), `tipo`, `titulo`, `lat`, `lng`, `cep`, `nv_geo_coord`, `cod_municipio` | `(cod_municipio, chave_logradouro)` e `(cod_setor, num_quadra, num_face)` |
| `logradouro_face` | `cod_setor`, `num_quadra`, `num_face`, `nome_logradouro`, `tipo`, `titulo`, `geom` (JSON, polilinha completa), `tot_res`, `tot_geral`, `cod_municipio` | `(cod_municipio, chave_logradouro)` |
| `logradouro_no` | `node_lat`, `node_lng`, `nome_logradouro` | PK `(node_lat, node_lng, chave_logradouro)` |

`chave_logradouro = chave_rua` (contrato) do nome canônico
`normalize(tipo|titulo|nome)`. `node_lat`/`node_lng` arredondados a 6 casas
(igual ao spike) — é a chave de coincidência de nó.

> **Sem PostGIS:** `geom` é um JSON `[[lat, lng], ...]` arredondado a 6 casas;
> "o mesmo nó" é igualdade de par arredondado (medido no spike). As
> extremidades `geom[0]`/`geom[-1]` **são** o nó e não viram coluna própria:
> medido na etapa 1, **22% das faces têm mais de 2 pontos** (3..104, não só 2),
> então o par de extremidades decretado nesta proposta teria jogado fora a forma
> de 10.460 das 48.159 faces e `projetar_no_eixo` projetaria por uma corda,
> estourando a tolerância de 40 m e perdendo âncora. `geom` subsume o par.

## 6. Algoritmo de resolução (por rua, com desempate)

1. Montar o **eixo** da rua: pontos do CNEFE (`lat/lng`) ordenados pela posição
   projetada (`estimar_numero` já existe).
2. **Âncoras** = `(posicao, num_endereco)` do CNEFE, com `NV_GEO_COORD ∈ {1,2}`
   (99,3% dos endereços; o filtro é teste, não achismo).
3. **<2 âncoras** ⇒ `intersecoes = []` (fim).
4. Cruzamentos candidatos = **nós das faces** da rua que compartilham nó com
   faces de **outra** rua (D16) — substitui a query 2 do Overpass.
5. `estimar_numero(posicao_do_no, ancoras)`; `None` ⇒ fora.
6. **Desempate:** quando várias faces da rua contêm o número (medido — **5** na
   Ivan Leão), vence a **faixa mais apertada** (menor `max - min`); empate
   persistente, ou discordância entre face e âncora ⇒ **triagem** (D2), nunca
   chute. A discordância entra na métrica (D20).
7. `<2 itens` ⇒ `[]`. Ordenar por `numero`; manter o trecho entre a 1ª e a
   última âncora.

**Idempotência e passe:** o UPDATE continua **só de `intersecoes`** (nunca cria
linha, nunca toca `lat/lng/cep/geocode_status` — §8.4), agora com um provedor
`ibge` ao lado do `overpass` (§8.1).

## 7. Etapas

| # | Etapa | Entregável |
|---|---|---|
| **1** | Ingestão CNEFE | Script de carga por município (`csv`+`zipfile`), tabela `cnefe_endereco`, idempotente (re-rodar não duplica), teste com fixture pequena |
| **2** | Ingestão Faces | Parser GeoJSON → `logradouro_face` + `logradouro_no`, teste com fixture de Belém (recorte) |
| **3** | Serviço `IbgeEntreRuasProvider` | Implementa a interface do §8.1 sem rede; reusa `axis.juntar_segmentos`/`projetar_no_eixo` |
| **4** | Ligação ao cache | Escreve `intersecoes` no contrato congelado; `provider='ibge'`; UPDATE-only; idempotente |
| **5** | Métricas (D20) | Persistir §8.5 + concordância CNEFE × Overpass; endpoint de triagem ganha a origem `ibge` |
| **6** | E2E de 10 mil | Reusar `test_contacts_e2e.py` com o provider IBGE; medir frio/quente novamente |
| **7** | Gates finais | §9 abaixo, ADR atualizado com os números reais |

## 8. Fase 4 — escala/self-host (especificada, não construída)

**Gatilho (D22):** só entra quando a métrica da Fase 3 mostrar que o gargalo é a
**latência/limite do provedor público** — §4.1/§4.2 da Fase 2: ~900 ruas na rede
boa, ~450 na lenta; ou quando o volume de Overpass público incomodar.

| Item | Custo medido/citado |
|---|---|
| `brazil-latest.osm.pbf` (Geofabrik) | **2,0 GB** |
| OSRM (`backend/docs/routing/osrm.md`) | 20–50 GB disco · 8–16 GB RAM · 1–8 h |
| Photon (planeta, 2026) | ~95 GB disco · 64 GB RAM (Brasil ≈ 1/20) |

**Decisões Fase 4:** Photon para geocoding **livre** (D8) · OSM local para o
passe de cruzamentos **se** o IBGE não cobrir uma cidade · **PostGIS só entra se
houver consulta espacial em request** (senão, índice em memória — `nearest` do
OSRM/Photon já resolve) · nenhuma API paga.

## 9. Gates (fecham CADA etapa — colar o output)

```
cd backend
python -m pytest tests/test_contacts_vcf.py tests/test_contacts_crm.py \
  tests/test_contacts_organizer.py tests/test_contacts_geocoding.py \
  tests/test_contacts_formatter.py tests/test_contacts_cep_fallback.py -q
python -m pytest tests/test_contacts_jobs.py tests/test_contacts_overpass.py -q
# novos
python -m pytest tests/test_contacts_ibge.py -q
python -m pytest tests/test_contacts_e2e.py -q -s
python -m pytest tests/test_gate_d20_metrica.py -q
python -m ruff check app tests
python -m mypy app
ADMIN_PASSWORD='<sua>' python -m tests.integrity_audit     # espera 19/0
python -m alembic heads                                    # um unico head
```

**Output colado (2026-10-07, `.venv-ci`):**

```
pytest (contatos + ibge + gate d20 + ingestao + metricas + renamer + ia) ... 378 passed
pytest tests/ (suíte completa) .................................. 2237 passed, 30 skipped
ruff check app tests scripts ................................... All checks passed!
ruff format --check app tests scripts ......................... 460 files already formatted
python -m alembic heads ......................................... 9f4b7e2a6c31 (head unico)
frontend npm test (vitest) ...................................... 74 arquivos / 441 testes pass
whatsapp npm test (node --test) ................................. 106 pass / 0 fail
```

`mypy app` **não executou neste ambiente** (AppLocker bloqueia o import do
mypy — `ImportError: DLL load failed`); último verde registrado em
2026-10-05 (`Success: no issues found in 334 source files`). O
`tests.integrity_audit` exige `ADMIN_PASSWORD` e ficou para rodar com as
credenciais do ambiente.

Testes novos desta fase: `test_ibge_ingestao.py` (7 — ingestão CNEFE/Faces
com fixture, idempotência, escopo, zip estadual),
`test_metrica_cobertura_fase3.py` (5 — definições do §10 sobre fixture) e
`test_gate_d20_metrica.py` (9 — a régua do D20, incluindo a que prova o teto
de 38,7% e a que proíbe rua de um só lado de entrar no corte).

> ✅ **Gate D20 aprovado** (medido em rodadas até saturar a amostra, 100/seed 42,
> cache 100/100): cobertura **67,0% × 7,0%** (**9,57× — folga ✓**) e
> **concordância de cruzamentos 76,3%** (29 de 38 cruzamentos do OSM trazidos
> também pelo CNEFE, em 6 ruas em comum; exigido ≥70%) **✓** → **APROVADO**.
> Números, diagnóstico e o **porquê da régua** (a régua de pontos na grade tem
> teto de 38,7% nesta amostra) em
> `docs/adr/ADR-0008-entre-ruas-por-dados-ibge.md`; relatório em
> `docs/auditoria/d20-concordancia.json`.

## 10. Métricas obrigatórias (D20)

| Métrica | O que decide |
|---|---|
| % de ruas com ≥2 âncoras CNEFE | piso de viabilidade (spike: 98,8% em Belém) |
| % de ruas com ≥2 cruzamentos de face | piso de topologia (spike: 52,3% com dois extremos) |
| % de ruas com `entre` preenchido | produto real (§8.5) |
| % do eixo coberto pelas âncoras | qualidade da projeção (§8.5) |
| **Concordância CNEFE × Overpass** | **critério de fechamento (D20)**: fração dos cruzamentos que o OSM reporta e que o CNEFE também traz, nas ruas em que os dois têm ≥2 — **≥ 70%** e piso de 10 cruzamentos (medido: **76,3%**; a régua de pontos na grade fica só como diagnóstico, teto 38,7% nesta amostra) |
| % de endereços casados com face | cobertura da junção (spike: 85,6%) |

## 11. DoD da Fase 3

- `intersecoes` preenchida pelo **IBGE** no contrato congelado; `[]` quando não há.
- UPDATE-only provado; idempotência provada; `lat/lng/cep/geocode_status` intactos.
- Métricas do §10 **persistidas** e o ADR atualizado com os números reais.
- **Concordância CNEFE × Overpass medida** e favorável ao CNEFE (D20).
- Gates do §9 verdes; **nada commitado sem pedido**.

## 12. Pendências abertas (não respondidas nesta revisão)

1. **Cidades além de Belém:** o `default_city`/`default_uf` (D11) é Belém/PA; a
   ingestão é por município. Cobertura de outras cidades não foi medida.
2. **CNEFE é de 2022** (coleta 2022-2023). Endereços novos pós-censo não entram —
   o Overpass (ou Photon na Fase 4) fica como complemento, não substituto.
3. **Faces "versão preliminar":** o IBGE diz que trechos capturados em campo
   ainda estão em consolidação; re-ingerir quando sair a versão definitiva.
4. **Alvo de 10k × 20k pico:** a Fase 2 mediu 10k; a Fase 3 herda a pendência.
5. **PontoFato** (3º elo de CEP) é **B** no catálogo — continua desligável.

## 13. Fontes (URLs reais, verificadas 2026-09-30)

- CNEFE por município:
  `https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/<UF>/<cod>_<NOME>.zip`
- Faces de Logradouro 2022 (json/shp por UF):
  `https://geoftp.ibge.gov.br/recortes_para_fins_estatisticos/malha_de_setores_censitarios/censo_2022/base_de_faces_de_logradouros_versao_2022_censo_demografico/`
- OSM Brasil: `https://download.geofabrik.de/south-america/brazil-latest.osm.pbf`
- Photon: `https://github.com/komoot/photon` · OSRM: `backend/docs/routing/osrm.md`
