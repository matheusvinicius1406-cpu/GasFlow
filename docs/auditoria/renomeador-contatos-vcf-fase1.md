# Renomeador automático de contatos (.vcf) — Fase 1: auditoria e levantamento

**Data:** 2026-09-25 · **Escopo:** renomear em lote contatos de um arquivo `.vcf`
para o formato de rota (`1= <rua> Nº <numero> entre <rua A> e <rua B> - CEP <cep>`)
· **Estado:** **Fase 1 — somente diagnóstico. Nenhuma linha de código de solução
foi escrita**, conforme a regra de ouro da missão.

> **Método:** reconhecimento do repositório `GasFlow/` por leitura direta de
> código e docs (grep estrutural + leitura de arquivos). Toda afirmação abaixo
> tem `arquivo:linha` ou caminho de arquivo como evidência. O que depende de
> decisão de produto está marcado `[PENDENTE]`.

---

## 0. Achado principal (leia antes de tudo)

**A funcionalidade não começa do zero: ~70% dela já está no repo.**

1. **O formato-alvo já existe como código morto.** `Client.crm_name`
   (`backend/app/domain/client/entity.py:88-92`) monta exatamente
   `"{codigo}= {rua} Nº{numero}{ref} ({nome})"` com o comentário *"Nome
   formatado para CRM (padrão Marcos Gás)"* — e **não é chamado em nenhum
   lugar** (grep vazio fora da definição). É o molde do que o cliente pediu.
2. **O renomeador em lote já existe** (missão F6): `ContactOrganizer`
   (`backend/app/application/contacts/organizer.py`) com regras puras
   testáveis, **preview obrigatório**, exclusão de conflitos da lista
   "Revisar", backfill de código sequencial global e **audit por contato**.
   UI em `frontend/src/features/whatsapp/ContactsOrganizerPage.tsx`, rotas em
   `frontend/src/App.tsx:76-77`.
3. **O import/export `.vcf` já existe**: `POST /whatsapp/contacts/import-vcf`
   e `GET /whatsapp/contacts/export-vcf`
   (`backend/app/presentation/api/whatsapp/contacts.py:118,165`) + UI de
   upload/download em `frontend/src/features/whatsapp/ContactsCrmPage.tsx:64,79`.

O que **realmente falta** são 4 coisas: (a) o `.vcf` de entrada precisa ser lido
**além de FN+TEL** (hoje o parser ignora `ADR`/`NOTE`, logo não há rua/numero/
bairro na entrada); (b) o schema **não tem `cep` nem "entre ruas"**; (c) a regra
de renomeação atual gera `"Nome — Bairro"`, não o formato de endereço; (d) **não
há geocoding real** (só um mock). Detalhe em §9.

---

## 1. Contexto do repo (o que já existe e pode ser reusado)

| Peça | Caminho | O que faz hoje |
|---|---|---|
| Renomeador em lote (F6) | `backend/app/application/contacts/organizer.py` | `build_rename_rule` / `apply_rename_rule` (trim, strip de prefixos `WA-`, Title/UPPER/lower, padrão `Nome — Bairro`), `preview_rename`, `apply_rename` (grava só se o `before` ainda bate — anti-corrida com o sync), `backfill_codes`, `list_conflicts` (`duplicate_name`, `bad_phone`), audit `contact.rename` |
| Endpoints do organizador | `.../whatsapp/contacts.py:259-332` | `rename-preview`, `rename-apply`, `backfill-codes`, `conflicts` — todos com `require_permission("customer.update")` (conflicts só `get_tenant_context`) |
| Upsert de contatos | `backend/app/application/contacts/service.py` | upsert idempotente por telefone normalizado; cria com placeholders (`rua="A definir"`, `numero="S/N"`, `bairro="A definir"`); `enrich_with_ai` (LLM extrai endereço do **nome**) |
| Import VCF | `.../whatsapp/contacts.py:118-162` | parser próprio (FN + TEL, sem dep nova); **ignora `ADR`, `NOTE`, `ORG`** |
| Export VCF | `.../whatsapp/contacts.py:165-198` | escreve `FN`, `N`, `TEL;TYPE=CELL`, `ADR;TYPE=HOME` (rua/complemento) |
| Entidade Cliente | `backend/app/domain/client/entity.py` | `codigo` (6 díg., imutável), `nome`, `telefone`, `rua`, `numero`, `complemento`, `referencia`, `bairro`, `crm_name` (morto) |
| Modelo/DB | `backend/app/infrastructure/repositories/client_model.py:15-41` | colunas reais; **não há `cep`** |
| Contrato de geocoding | `backend/app/domain/delivery/routing.py:36-45` | `RoutingProvider.geocode(address) -> GeoPoint` — **só `MockRoutingProvider`** (retorna São Paulo fixo) |
| Roteamento por matriz | `backend/app/domain/routing/provider.py`, `infrastructure/routing/{factory,haversine_provider,osrm_provider}.py` | haversine default; **OSRM opt-in** via `ROUTING_PROVIDER=osrm` + `OSRM_BASE_URL` (`core/config.py:145-152`); self-host pronto em `docker-compose.osrm.yml` |
| Testes | `backend/tests/` (organizer), `frontend/src/features/whatsapp/ContactsOrganizerPage.test.tsx` | regras puras + UI já testadas |

**Status declarado pela própria documentação:** `docs/entregas-cupons-spec.md:24`
(ponto 9 "Organizador de Contatos" ~50%) e `:168` (F6 = "100% dos contatos com
código sequencial; zero duplicatas após renomeação em lote").

---

## 2. Perguntas de negócio

### 2.1 Volume e uso
| Pergunta | Resposta |
|---|---|
| Contatos por `.vcf` | `[PENDENTE]` — o repo não guarda histórico. **Alerta de escala:** o `preview_rename` lê **apenas 200 contatos** (`organizer.py`, `page_size=200`) → para 1k/10k o preview fica **incompleto** (ver G5). |
| Frequência | `[PENDENTE]` — os endpoints são **sob demanda** (upload manual), não há agendamento |
| Quem opera | Backoffice com permissão `customer.update`/`customer.create` (`contacts.py`); entregador (app Android) **não** tem acesso a essa superfície |
| Multiempresa (SaaS)? | **Sim, multi-tenant por design** — `tenant_id` em todo modelo (`client_model.py:15`), `TenantContext` em cada endpoint. Não é uso interno único |

### 2.2 Regra de renomeação
| Pergunta | Resposta |
|---|---|
| Formato final exato | `[CONFIRMAR]` `"{codigo}= {rua} Nº {numero} entre {ruaA} e {ruaB} - CEP {cep}"` — base já existe em `crm_name` (`{codigo}= {rua} Nº{numero} ({nome})`) |
| Código reinicia por quê? | **Não reinicia.** Hoje o código é **sequencial GLOBAL por tenant** (I1): `repo.proximo_codigo()`, derivado do maior código existente. `entity.py` exige 6 dígitos. |
| Critério de ordenação | `[PENDENTE]` — hoje o organizer **não define ordenação** (usa a ordem do `repo.buscar`). Alfabético por rua? Geográfico (rota)? Ordem do `.vcf`? **Bloqueante** (§10). |
| Sobrescreve código antigo? | **Não.** `backfill_codes` só preenche código **vazio**; buracos pré-existentes **não** são renumerados (decisão I1 documentada no código). |
| Nome sem número de casa | Hoje vira `numero="S/N"` no upsert (`service.py`) → sairia `Nº S/N`. `[PENDENTE]` se é isso que se quer. |

### 2.3 "Entre ruas"
| Pergunta | Resposta |
|---|---|
| Fonte das ruas vizinhas | **Não existe hoje.** `[PENDENTE]` — proposta: **Overpass API (OSM)**, gratuito e sem key (ver §8) |
| Se não achar | `[PENDENTE]` — propor: deixar em branco **ou** mandar para a lista de revisão (nunca inventar) |
| Formato do "entre" | `[PENDENTE]` — o cliente escreveu `entre Rua A e Rua B`; confirmar separador |

### 2.4 CEP
| Pergunta | Resposta |
|---|---|
| Obrigatório no nome? | `[PENDENTE]` |
| Fonte do CEP | **Não existe hoje** (sem coluna). Proposta: **ViaCEP** por (rua, bairro, cidade) — gratuito |
| Se não achar CEP | `[PENDENTE]` — propor: revisão, nunca chutar |

### 2.5 Separação Entregas vs. Clientes
| Pergunta | Resposta |
|---|---|
| Critério | **Não existe hoje esse conceito.** O mais próximo: filtro `missing_address` (`contacts.py`, `list_contacts`) e os `Segmentos` (`/segments`). `[PENDENTE]` |
| "Clientes" é lista/tag/categoria? | `[PENDENTE]` — o CRM não tem "lista" de contatos; tem `segmentos` para clientes |

---

## 3. Perguntas técnicas

### 3.1 Stack atual
| Item | Realidade (evidência) |
|---|---|
| Backend | **Python + FastAPI** (`backend/app/presentation/api/...`), SQLAlchemy, Alembic |
| Frontend | **React 19 + Vite** (TypeScript) — **não é Next.js**; + **Electron** (`desktop/`) e app **Android** (`mobile/`) |
| Banco | **PostgreSQL** em produção (`docker-compose.yml: postgres`) via Alembic; **SQLite** no desktop/dev (ver `docs/DIAGNOSTICO_WHATSAPP_CLIENTES_INTELIGENCIA.md`) |
| Upload `.vcf` já existe? | **Sim** — `POST /whatsapp/contacts/import-vcf` + UI |
| Onde ficam os contatos? | Tabela **`clients`** (CRM), sincronizada do serviço WhatsApp (Baileys). Não é Google Contacts nem CRM externo |

### 3.2 Infra
| Item | Realidade |
|---|---|
| Onde roda | **Docker Compose** auto-hospedado (`docker-compose.yml`, `docker-compose.prod.yml`, `DEPLOY.md`). Sem K8s |
| Docker/K8s | Docker Compose ✅ (K8s ❌) |
| CI/CD | **GitHub Actions** ✅ — `ci.yml`, `e2e.yml`, `build-push.yml`, `release.yml` |
| Observabilidade | Prometheus + Grafana + Alertmanager (`monitoring/`) |

### 3.3 APIs externas
| Item | Realidade |
|---|---|
| **Google Maps API Key** | **Não existe e não é aceitável.** A spec de rastreio (`rastreio-entrega-inteligente-spec.md`, "Restrições globais") fixa: *"somente open source e gratuito … nenhuma API key comercial"* |
| Alternativas aceitáveis | ✅ **Nominatim (OSM)** p/ geocoding, ✅ **ViaCEP** p/ CEP, ✅ **Overpass (OSM)** p/ "entre ruas", ✅ **OSRM** já self-hosted (`docker-compose.osrm.yml`). Todas gratuitas e alinhadas à restrição |
| Já há provider plugável? | ✅ o **contrato** existe (`app/domain/delivery/routing.py`) e o **roteamento** já tem factory haversine/osrm. O **geocoding** precisa de implementação (hoje só `MockRoutingProvider`) |

### 3.4 Formato do .vcf
| Item | Realidade |
|---|---|
| Versão | Parser aceita 3.0/4.0 "de leve" (`contacts.py:141`) |
| Campos lidos | **Só `FN` + `TEL`** no import; export escreve `FN/N/TEL/ADR`. **`ADR`/`NOTE` não são lidos** → rua/numero/bairro do arquivo são descartados (G1) |
| Encoding | Lê `utf-8` com `errors="replace"`. **Não trata `quoted-printable`** nem `CHARSET` de vCard 2.1 |
| Exemplo real anonimizado | `[ANEXAR]` |

### 3.5 Saída
| Item | Realidade |
|---|---|
| Gera novo `.vcf`? | **Hoje não** (para o rename). Existe export do CRM (`/export-vcf`) |
| Salva no banco? | ✅ o import faz upsert no CRM |
| Exporta CSV? | **Não** para contatos (CSV existe só no módulo financeiro) |
| Log de auditoria? | ✅ **Sim** — `contact.rename` (before/after) e `contact.backfill_code` em `AuthAuditModel` (`organizer.py::_audit`) |

---

## 4. Perguntas de UX
| Item | Realidade |
|---|---|
| Upload via | ✅ **Web** (`ContactsCrmPage.tsx`, input `accept=".vcf,text/csv"`) |
| Preview antes de confirmar | ✅ **Já é obrigatório** (`rename-preview` → `rename-apply` só com os códigos vistos — regra I3) |
| Tela de correção manual | ✅ **Já existe** — lista "Revisar"/conflitos (`ContactsOrganizerPage.tsx`) |
| Notificação ao terminar | ❌ Nenhuma (nem email nem webhook) — `[PENDENTE]` se precisa |

---

## 5. Qualidade e segurança
| Item | Realidade |
|---|---|
| PII (LGPD)? | **Sim** — nome + telefone + endereço. `marketing_status` (`OPTED_IN/OPTED_OUT/BLOCKED`) é o espelho de consentimento (`client_model.py:38`) |
| Mascaramento em logs | ❌ não implementado para contatos — `[PENDENTE]` |
| Criptografia em repouso | ❌ não (volume do Postgres) |
| Retenção do `.vcf` original | ❌ hoje o upload **não é persistido** (parseado em memória) — bom por privacidade; `[PENDENTE]` se precisa guardar |
| Limite de upload | ⚠️ **`frontend/nginx.conf:28-36` não define `client_max_body_size`** → vale o **default do nginx = 1 MB**. Um `.vcf` de ~10k contatos passa disso → **quebra** (G6) |
| Rate limit | ✅ `RateLimitMiddleware` por path (`backend/app/core/rate_limit.py:125`), com backend Redis e fallback in-memory |

---

## 6. Restrições
| Item | Resposta |
|---|---|
| Prazo | `[PENDENTE]` |
| Orçamento p/ APIs pagas | **Zero** — restrição de projeto: só open source/gratuito, sem API key comercial |
| Time / stack dominante | Python (FastAPI) + React/TS; app Android separado |
| Rodar offline/on-premise | **Sim** — é auto-hospedado. Geocoding externo (Nominatim/ViaCEP) requer internet; OSRM é local |

---

## 7. Critérios de aceite (proposta — validar)
- [ ] `X` contatos processados em `< T` (a definir com o volume real)
- [ ] **0 contatos perdidos** no processo (o sync em lote já nunca aborta por 1 contato ruim)
- [ ] **0 nomes sobrescritos sem preview/confirmação** (regra I3 já existe — manter)
- [ ] Toda renomeação com **audit before/after** (já é o padrão)
- [ ] Contatos sem rua/nº/CEP vão para **revisão**, nunca recebem dado inventado
- [ ] `[PENDENTE]` % mínimo de CEP correto
- [ ] `[PENDENTE]` critério de separação Entregas vs Clientes

---

## 8. Entregáveis da auditoria

### 8.1 Mapa de fluxo (alvo)
```
(.vcf)  →  parser estendido (FN, TEL, ADR, NOTE, CEP)
        →  upsert no CRM (por telefone normalizado)      [JÁ EXISTE]
        →  geocoding: Nominatim → lat/lng                 [FALTA]
        →  CEP: ViaCEP (rua+bairro+cidade)                [FALTA]
        →  "entre ruas": Overpass (vias próximas)         [FALTA]
        →  regra de nome "endereço" (codigo= rua Nº n entre A e B - CEP)  [FALTA]
        →  PREVIEW (nada grava sem confirmação)           [JÁ EXISTE, adaptar]
        →  APPLY + audit por contato                       [JÁ EXISTE, adaptar]
        →  lista "Revisar" para o que faltou              [JÁ EXISTE, adaptar]
        →  export .vcf renomeado                           [FALTA]
```

### 8.2 Integrações externas
| Integração | Uso | Custo | Risco |
|---|---|---|---|
| **Nominatim (OSM)** | geocodificar endereço | grátis | **rate limit ~1 req/s** + política de uso (User-Agent obrigatório, proibido uso massivo) → precisa **cache + fila** |
| **ViaCEP** | obter CEP | grátis | sem SLA; cachear |
| **Overpass (OSM)** | achar vias adjacentes ("entre") | grátis | pesado; consultas por bairro devem ser cacheadas/agregadas |
| **OSRM** (já existe) | rota/ETA | grátis (self-host) | precisa dos dados `.osrm` |

### 8.3 Riscos
| # | Risco | Mitigação |
|---|---|---|
| R1 | **Google Maps é "indispensável"?** Para "entre ruas" com precisão, Google é melhor — mas a restrição de projeto **proíbe API key comercial** | Usar Overpass+OSM e aceitar cobertura parcial → revisão manual; reavaliar com o cliente |
| R2 | Rate limit do Nominatim derruba lote grande | cache persistente (endereço→lat/lng) + processamento assíncrono com throttle |
| R3 | `.vcf` > 1 MB quebra no nginx | `client_max_body_size` explícito + limite documentado |
| R4 | Parser atual descarta o endereço do `.vcf` | estender o parser (**sem dep nova**, padrão do repo) |
| R5 | Preview de 200 → renomeação parcial silenciosa em base grande | paginar/streamar o preview; **bloqueante para 10k** |
| R6 | PII em logs | mascarar telefone/nome em log de diagnóstico |

### 8.4 Stack recomendada (validada contra o repo)
| Camada | Recomendação | Observação vs. sua proposta |
|---|---|---|
| Parser `.vcf` | **manter o parser próprio**, estendido para `ADR/NOTE/CEP` | ⚠️ **não** adicionar `vobject` — o repo adota explicitamente "parser próprio, sem dep nova" e já tem dependência sensível (`python-multipart`) |
| Backend | **FastAPI** | ✅ confirmado (já é o backend) |
| Geocoding | **Nominatim (OSM)** + **ViaCEP** | ✅ encaixa; implementar atrás do contrato `RoutingProvider.geocode` que **já existe** |
| "Entre ruas" | **Overpass API (OSM)** | ✅ encaixa; cachear por bairro |
| Fila | ⚠️ **Redis já existe** (rate limit, pubsub, whatsapp limits) mas **não há Celery/RQ/ARQ** | **Não** introduzir Celery só por isso: usar `BackgroundTasks` do FastAPI ou um job leve sobre o Redis/pubsub existente |
| Banco | **PostgreSQL** (já é) | ⚠️ **PostGIS não está instalado** — para este caso bastam colunas `cep` + `lat`/`lng` (o domínio já usa `GeoPoint`), **evitar PostGIS** |
| Frontend | **React + Vite** (já é) | ⚠️ **não** migrar para Next.js — o painel é SPA |
| Container | Docker Compose (já é) | — |

### 8.5 Estimativa de esforço (estimativa, não compromisso)
| Cenário | Escopo | Estimativa |
|---|---|---|
| **MVP sem geocoding** | estender parser (`ADR/NOTE`), ler rua/nº/bairro do `.vcf`, adicionar modo "endereço" na regra do organizer, corrigir o preview paginado, export `.vcf` renomeado | **3–5 dias** |
| **Completo** | + coluna `cep`, Nominatim/ViaCEP/Overpass com cache, processamento assíncrono com throttle, lista de revisão ampliada, feature flag, testes + E2E | **2–3 semanas** |

---

## 9. Lacunas concretas (o que falta construir)

| # | Lacuna | Evidência |
|---|---|---|
| **G1** | O parser `.vcf` **não lê `ADR`/`NOTE`** → sem rua/numero/bairro na entrada | `contacts.py:140-162` |
| **G2** | **Sem coluna `cep`** (e sem "entre ruas") | `client_model.py:15-41` |
| **G3** | **Sem geocoding real** (só `MockRoutingProvider`) | `domain/delivery/routing.py:36-45` |
| **G4** | Regra de rename gera `"Nome — Bairro"`, **não o formato de endereço** | `organizer.py::apply_rename_rule` |
| **G5** | `preview_rename` limitado a **200 contatos** | `organizer.py::preview_rename` |
| **G6** | **nginx sem `client_max_body_size`** (default 1 MB) | `frontend/nginx.conf:28-36` |
| **G7** | Sem export `.vcf` renomeado (só export do CRM cru) | `contacts.py:165` |
| **G8** | `crm_name` (formato-alvo) **não é usado** | `entity.py:88-92` |

---

## 10. Decisões — **FECHADAS** em 2026-09-25

Detalhamento e consequências em `docs/adr/ADR-0001-renomeador-contatos-vcf.md`.

| # | Pergunta | Decisão |
|---|---|---|
| D1 | Ordenação do código | **Alfabética só na lista**; o código segue a **ordem de cadastro** (imutável, sem renumeração). Se o contato vier com código antigo no nome (`114= ...`), o app **descarta** e usa o dele. |
| D2 | CEP / "entre ruas" | **Best-effort:** CEP do `postcode` do Nominatim; "entre ruas" do Overpass. Se falhar, **omite o trecho** — nunca inventa. |
| D3 | Entregas vs. Clientes | Sai a heurística de rua; entra **`geocode_status`** (`OK`/`NAO_ENCONTRADO`/`PENDENTE`). Contato nunca é perdido. |
| D4 | Volume | **Até 5.000/arquivo** → exige `client_max_body_size`, assíncrono (hoje síncrono morre no `proxy_read_timeout 30s`) e **geocoding por rua, não por endereço**. |
| D5 | Sobrescrever nome | Não sobrescreve cegamente; código **nunca** reatribuído (I1). O **nome da pessoa permanece no fim** do padrão (evita colisão de endereço). |
| D6 | Reter o `.vcf` | **Não persiste**: processa em memória, guarda só **hash + contagem** no audit. |

---

## 11. Próximo passo proposto

Nada de código antes das decisões da §10. Com elas, a ordem natural é:

1. **ADR** (uma por decisão arquitetural: parser próprio × lib, fonte de
   geocoding, fila, `cep`/`entre ruas` no schema, feature flag).
2. **Schema**: migration aditiva (`cep`, `entre_ruas`, `lat`/`lng` opcionais) —
   aditiva e com defaults, sem quebrar o SQLite do desktop (padrão do repo).
3. **Esqueleto**: estender o parser `.vcf` (com testes de fixture anonimizada) e
   o contrato `RoutingProvider.geocode` com um provider Nominatim atrás de flag.
4. **Protótipo**: rodar um `.vcf` de exemplo pelo fluxo preview → apply → export.
