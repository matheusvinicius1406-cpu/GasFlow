# ADR-0001 — Renomeador automático de contatos (.vcf)

**Status:** Aceito · **Data:** 2026-09-25 · **Fase:** 1 (auditoria) → 2 (esqueleto)
**Contexto:** `docs/auditoria/renomeador-contatos-vcf-fase1.md` (P12 da Central
Financeira é missão separada — não confundir).

---

## 1. Contexto

O cliente precisa renomear em lote a agenda de contatos exportada do celular
(`.vcf`) para o padrão de rota usado pela revenda:

```
{codigo}= {rua} Nº {numero} entre {ruaA} e {ruaB} - CEP {cep}
```

A auditoria da Fase 1 mostrou que **~70% já existe**: `ContactOrganizer`
(F6) com preview obrigatório, conflitos e audit; `import-vcf`/`export-vcf`;
`codigo` sequencial global por tenant; e o contrato `RoutingProvider.geocode()`
(só mockado). As lacunas são: parser lê só `FN`/`TEL`, não há `cep`/`entre_ruas`
no schema, não há geocoding real e a regra gera `Nome — Bairro`.

## 2. Decisões (confirmadas pelo cliente em 2026-09-25)

### D1 — O código segue a ordem de cadastro; a lista é alfabética
O `codigo` é **imutável** (`entity.py`: *"Código nunca muda"*) e o backfill nunca
renumera buracos (I1). Portanto **não há renumeração**: o app atribui o código na
ordem em que cadastra (`proximo_codigo()`), e a ordenação alfabética por
`(rua, numero)` vale **apenas para exibição/preview** — nunca para o código.

**Adicional exigido pelo cliente:** se o contato **já vier com um código antigo
no nome** (ex.: `114= rua X Nº10`), esse código é **descartado** e substituído
pelo código do app. O código antigo **não** é copiado — ele sobrevive apenas no
`before_json` do audit `contact.rename` (rastreabilidade de graça, sem coluna
nova).

### D2 — CEP e "entre ruas" são best-effort, nunca bloqueantes
- **CEP:** obtido do `postcode` do **Nominatim** (OSM). ViaCEP fica como
  secundário — o endpoint por endereço do ViaCEP exige **município**, e o
  `Client` **não tem `cidade`** (confirmado em entity/model/repo). Não se
  adiciona `cidade` nesta fase.
- **Entre ruas:** obtido do **Overpass (OSM)** quando as duas ruas resolvem no
  mesmo bairro; caso contrário **o trecho é omitido** — nunca se inventa.
- Falha de CEP **não** manda o contato para "Clientes"; marca
  `geocode_status = NAO_ENCONTRADO` (ver D3).

### D3 — `geocode_status` em vez de heurística de rua
Critério de separação via campo explícito na tabela `clients`, no padrão de enum
do repo (`marketing_status`):

| Valor | Significado |
|---|---|
| `PENDENTE` | ainda não geocodificado |
| `OK` | endereço resolvido (tem `lat`/`lng`) |
| `NAO_ENCONTRADO` | Nominatim/Overpass não resolveu → entra na triagem |

Contatos não resolvidos **não são perdidos**: são renomeados só com o código e
apontados na triagem. **Nunca** usamos "rua não achada no Maps" como critério
sólido (falha de API descartaria contato).

### D4 — Lote alvo de até 5.000 por arquivo
Isso **obriga** três mudanças de infra (nenhuma é opcional):
1. `frontend/nginx.conf` não define `client_max_body_size` → vale o default
   **1 MB**; 5.000 vCards ≈ 0,6–1,0 MB → precisa de limite explícito.
2. `proxy_read_timeout 30s` (`nginx.conf:36`) mata qualquer lote síncrono →
   o processamento **tem de ser assíncrono** (o repo não tem Celery/RQ: usa
   `BackgroundTasks` do FastAPI ou o Redis/pubsub existente).
3. **Geocodificar a rua, não o endereço:** cache por `(rua, bairro)`
   normalizado derruba ~5.000 requisições para ~200–500 — o único jeito de
   caber na política de uso do Nominatim (≈1 req/s, uso massivo proibido).

### D5 — O nome da pessoa permanece no fim (padrão `crm_name`)
Formato final:
```
{codigo}= {rua} Nº {numero} entre {ruaA} e {ruaB} - CEP {cep} ({nome})
```
Fallbacks: sem "entre ruas" → omite `entre ...`; sem CEP → omite `- CEP ...`;
sem nome → omite `({nome})`. Manter o nome evita que **dois moradores do mesmo
endereço** fiquem indistinguíveis (risco identificado na auditoria).

### D6 — O `.vcf` não é persistido
Processamento em memória; guarda-se apenas **hash + contagem** no audit. Melhor
para LGPD, e o hash dá idempotência de re-upload de graça. O código existente já
não persiste o arquivo.

## 3. Decisões técnicas

| Tema | Decisão | Alternativa rejeitada |
|---|---|---|
| Parser `.vcf` | **Manter parser próprio**, estendido para `ADR`/`NOTE` e o padrão de nome legado | `vobject` — o repo adota explicitamente "parser próprio, sem dep nova" |
| Geocoding | **Nominatim (OSM)** por trás do contrato `RoutingProvider.geocode()` que já existe | Google Maps — **vetado pela restrição de projeto** ("nenhuma API key comercial", `rastreio-entre-inteligente-spec.md`) |
| "Entre ruas" | **Overpass API (OSM)** | Google Places |
| Fila | `BackgroundTasks` / Redis existente | Celery/RQ — não existem no repo e não valem a dependência |
| Geo no banco | Colunas `lat`/`lng` (Float) no `clients` | PostGIS — não instalado, e o domínio já usa `GeoPoint` |
| Frontend | React + Vite (inalterado) | Next.js |

## 4. Consequências

**Positivas**
- Reaproveita preview/apply/audit/conflitos já testados; nada de reescrever o
  renomeador.
- Aditivo: colunas novas são `nullable`, defaults preservam o comportamento
  atual, e o Desktop (SQLite) ganha as colunas por `_ensure_sqlite_columns()`.

**Negativas / custo aceito**
- Introduz dependência de internet para geocoding (o app é auto-hospedado);
  mitigado por cache e por ser best-effort.
- O nome humano continua em `nome` (padrão D5), então o formato é mais longo.

## 5. Riscos residuais

| # | Risco | Mitigação |
|---|---|---|
| R1 | `import-vcf` cria um `Client` para **todo** contato (agenda de 5.000 → 5.000 clientes) | Decisão explícita do cliente: manter o fluxo atual (D4/escopo) |
| R2 | Política de uso do Nominatim (1 req/s, sem uso massivo) | Cache por rua + throttle + processamento assíncrono |
| R3 | `export-vcf` escrevia `ADR` fora da ordem do spec (vCard: `pobox;ext;rua;bairro;região;cep;país`) | Corrigido nesta fase para o round-trip funcionar |
| R4 | Nomes de rua que contenham " e " podem confundir o `entre` | Documentado; a triagem cobre o caso |
| R5 | `preview_rename` limitado a 200 contatos | Fora de escopo desta fase; **bloqueante** para o lote de 5.000 (D4) — a corrigir antes do go-live |

## 6. Fora de escopo

Implementação do provider Nominatim/Overpass (só o contrato + cache ficam
preparados) · UI de triagem e export `.vcf` renomeado · correção do limite de 200
do preview · assíncrono/progresso do lote · `cidade` no schema · régua de
cobrança.

---

## 7. Registro de decisões por etapa

| Etapa | Entrega | Estado |
|---|---|---|
| 1 | ADR (este arquivo) | ✅ |
| 2 | Migration aditiva + modelo + entidade + repositório | ✅ |
| 3 | Parser `.vcf` estendido (`ADR`/`NOTE` + código legado) | ✅ |
| 4 | Provider de geocoding real (Nominatim/Overpass + cache) | ⏳ |
| 5 | UI de triagem + export `.vcf` renomeado + regra de nome de endereço | ⏳ |
