# ADR-0006 — Jobs bounded-batch e a tabela `contact_jobs`

**Status:** Aceito · **Data:** 2026-09-29 · **Fase:** 2 (etapa 8)
**Relacionado:** `docs/adr/ADR-0002-preview-apply-desacoplados.md`,
`docs/adr/ADR-0004-cache-geocoding-por-rua.md`,
`docs/adr/ADR-0005-formatter-nome-rota.md`,
`docs/prompts/renomeador-contatos-fase2.md` (§5, §8.4, §9 etapa 8).

---

## Contexto

O renomeador em lote não cabe num request só:

- o nginx corta em **30 s** (`frontend/nginx.conf`, `proxy_read_timeout`), e a
  regra da missão é **não** mexer nesse timeout;
- o geocode frio paga **~1 s/rua** (política do Nominatim público, ADR-0004);
- o passe Overpass paga outro pedágio por rua (D14).

Além disso, o processamento precisa **retomar** depois de um restart do backend
(hoje `BACKEND_WORKERS=2` em prod) e nenhum estado podia viver na memória do
processo — um `dict` de job sumiria no restart (foi exatamente o problema que a
F10.7 resolveu para impressão com `print_jobs`).

O padrão do repo para isso já existe: **bounded-batch**, como
`POST /whatsapp-automation/process-pending`.

## Decisão

### 1. Tabela `contact_jobs`, com o serviço que a consome

`app/infrastructure/repositories/contact_job_model.py` (migration
`e5c9f3a7b1d2`, aditiva) e o consumidor na camada de aplicação
`app/application/contacts/jobs.py` (`ContactJobService`). O guard de
integridade do repo **exclui `repositories/`** do scan, então tabela nova sem
consumidor em `application/`/`presentation/` reprovaria como `dado-invisivel` —
por isso os dois entram juntos.

Colunas: `id`, `tenant_id`, `tipo`, `status`, `cursor`, `regra`, `filtro`,
`total`, `processados`, `alterados`, `metrica`, `erro`, `criado_em`,
`atualizado_em`.

### 2. Retomada por **cursor keyset**, não por offset

O passe muda a base enquanto roda: o contato geocodificado sai do conjunto
“pendente”. Paginar por offset pularia item quando o conjunto encolhe; o cursor
guarda o **último `codigo`/`id` visto** e a próxima consulta usa
`codigo > cursor` (GEOCODE/APPLY) ou `id > cursor` (OVERPASS). É estável porque
nada é apagado durante o passe.

### 3. Três tipos, três custos

| Tipo | Unidade | Lote padrão | O que faz |
|---|---|---|---|
| `GEOCODE` | contato | 20 | cache-first por rua (ADR-0004) |
| `OVERPASS` | rua (linha do cache) | 15 | preenche `intersecoes` |
| `APPLY` | contato | 500 | renomeia com a regra (organizer) |

O lote é **clampado** por um teto (`_LOTE_MAX`) para o request não passar dos
30 s. Geocode/Overpass são pequenos porque pagam ~1 s/item; o apply é local e
cabe lote grande.

### 4. O passe Overpass é **UPDATE-only** de `intersecoes` (§8.4)

A faixa vem de um `SELECT` sobre `geocode_cache` (linhas com `lat` e
`intersecoes` nulas). Para cada linha: roda o provider e grava **só**
`intersecoes` — nunca cria linha (criar com `lat/lng` nulos gravaria um
*negativo falso*) e nunca toca `lat/lng/cep`. Linha já preenchida (inclusive com
`[]`) conta como processada. A métrica §8.5/§8.8.5 (ruas com ≥2 âncoras, ≥2
cruzamentos, com interseções, inversões) é acumulada em `metrica` — sem número,
“entre ruas” seria opinião.

### 5. `CONTACT_RENAMER_ENABLED` passa a valer

A flag estava declarada e **inerte** (ADR-0004 registrou isso). Agora um
dependency (`require_renamer_enabled`) responde **409** quando ela está
desligada, nos endpoints de job. Desligado não é 200 silencioso: o rollback da
§13 é “nada de novo roda” — os endpoints F6 legados (preview/apply/backfill/
conflicts) continuam como estavam, porque já estão em uso; a flag gateia a
**superfície nova** (jobs).

`ENTRE_RUAS_RADIUS_M` passa a valer pelo mesmo motivo: o provider já a lia, mas
não havia consumidor; o job OVERPASS é o consumidor.

### 6. `client_max_body_size 16m` no nginx

Sem isto vale o default de **1 MB**, e um `.vcf` de ~10k contatos (~3 MB; pico
de 20k ≈ 16 MB) quebra no nginx antes de chegar no backend. Fica em
`location /api`, dentro do limite de alvo do §4. **`proxy_read_timeout` fica
intacto** — o processamento longo virou job, não request longo.

### 7. `import-vcf` deixa de devolver 10k linhas no JSON

A resposta passa a trazer só contadores (`imported`, `created`, `updated`,
`telefones_ignorados`). O detalhe por contato vivia só na resposta; o que
importa (before/after) é o audit, e o CRM é a fonte da verdade.

### 8. Correção de schema necessária ao passe: `JSON(none_as_null=True)`

`geocode_cache.intersecoes` era `JSON` sem `none_as_null`; o SQLAlchemy grava
`None` como o **JSON `null`** (a string), não SQL NULL. O passe seleciona
`intersecoes IS NULL` como “rua não processada” e **nunca casaria**. A coluna
passa a `JSON(none_as_null=True)` — sem mudança de DDL (o export do Alembic é o
mesmo), só de comportamento de persistência. É pré-requisito do item 4, não
cosmético.

### 9. `export-vcf?formatar_rota=true` (fecha a lacuna G7)

O export do CRM já existe, mas só devolvia o nome **atual** do contato — a
auditoria registrou isso como “sem export .vcf renomeado”. O parâmetro liga o
formatter do ADR-0005 no export, então o operador confere o resultado do
renomeador **sem aplicar nada** (e o `.vcf` de saída é o objeto final do fluxo).
Sem o parâmetro, o comportamento é o de sempre.

## Consequências

- Nenhum request do renomeador passa dos 30 s; o cliente dirige o avanço e o
  job sobrevive a restart (estado no banco).
- O schema ganha uma tabela aditiva (`contact_jobs`) e sobe a `SCHEMA_VERSION`
  para 8; `alembic upgrade head` cria do zero e alinha com os models (teste de
  alinhamento verde).
- `import-vcf` tem payload pequeno e previsível.

## Limites do que está provado (não ler como medido)

- **Tempo e escala não foram medidos**: os lotes padrão são cálculo do rate
  limit, não medição. O alvo de 10k ponta a ponta é a etapa 9.
- **A UI paginada/progresso/triagem/export é a parte pendente da etapa 8.**
  O backend está fechado; sem a tela, o operador ainda usa os endpoints F6.
- As chaves de `contact_jobs.regra`/`filtro` são o dict já validado pelo
  organizer; um job APPLY criado por outro caminho precisa da mesma validação.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| `BackgroundTasks` do FastAPI | Não existe padrão disso no repo, não retoma após restart e não dá progresso ao operador |
| Celery/RQ/ARQ | Dependência nova pesada por um job que o padrão bounded-batch já resolve (a missão proíbe) |
| Estado do job em memória (`dict`) | Perde o ponto de retomada no restart — o bug que a F10.7 já corrigiu para impressão |
| Paginação por offset | Pula item quando o conjunto candidato encolhe durante o passe |
| Aumentar `proxy_read_timeout` | Viola a regra da missão e troca um problema (timeout) por outro (request pendurado) |
| `none_as_null` só no teste (gravar `""` como marcador) | Polui a coluna com um valor que não é lista de interseções, contra o contrato congelado |
| Gatear também o F6 legado pela flag | Quebraria a superfície já em uso; a flag existe para o rollout da Fase 2 |
