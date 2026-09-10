# GASFLOW — WAVE 1 — AUDITORIA DOS 11 REPOSITÓRIOS

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).


**Data:** 2 de setembro de 2026
**Baseline:** Backend 1002/1002 PASS, Frontend 62/62 PASS

---

## 1. EVOLUTION API

| Campo | Valor |
|-------|-------|
| URL | https://github.com/evolution-foundation/evolution-api |
| Licença | **Apache 2.0** (com brand-protection) |
| Stack | TypeScript/Node.js |
| WhatsApp Engine | Baileys + WhatsApp Cloud API |
| Multi-instance | ✅ |
| Webhooks | ✅ |
| REST API | ✅ |
| Docker | ✅ |
| Maturidade | Alta (produção ativa) |
| RAM estimado | ~200-500MB por instância |
| Multi-tenant | ❌ (multi-account sim) |
| Documentação | Boa |

**Classificação:** `USE AS SERVICE` — Candidato a self-hosted WhatsApp gateway substituindo o provider atual (whatsapp-web.js). Licença permite uso comercial. Brand protection não impede uso como backend.

**Risco:** Baixo. Apache 2.0 é permissiva. Brand protection só impede usar "Evolution" no nome do produto.

---

## 2. BAILEYS

| Campo | Valor |
|-------|-------|
| URL | https://github.com/WhiskeySockets/Baileys |
| Licença | **Custom** (Copyright 2025 Rajeh Taher/WhiskeySockets) — NÃO é MIT |
| Stack | TypeScript |
| WhatsApp Web | ✅ WebSocket direto (sem Chromium) |
| Multi-device | ✅ |
| Mídia | ✅ |
| Reconexão | ✅ |
| Docker | Não nativo (lib) |
| Maturidade | Alta |
| RAM | ~50-100MB (lib leve) |

**Classificação:** `USE AS LIBRARY` — Engine WhatsApp mais leve que whatsapp-web.js. Licença custom requer verificação de compatibilidade comercial. **NÃO é MIT nem Apache.**

**Risco:** Médio. Licença custom pode ter restrições não óbvias. Verificar termos antes de uso em produto comercial.

---

## 3. CHATWOOT

| Campo | Valor |
|-------|-------|
| URL | https://github.com/chatwoot/chatwoot |
| Licença | **MIT** (Community Edition) |
| Stack | Ruby on Rails + React |
| Stars | ~33k |
| WhatsApp | ✅ (via provider) |
| Omnichannel | ✅ |
| Agentes | ✅ |
| Assignment | ✅ |
| Tags/Notas | ✅ |
| Docker | ✅ |
| Maturidade | Muito alta |
| RAM | ~1-2GB (Rails app) |

**Classificação:** `USE AS REFERENCE` — Excelente referência de arquitetura de inbox/atendimento. **NÃO incorporar** o Chatwoot inteiro (Ruby stack incompatível com FastAPI/Python). Estudar: modelagem de conversas, assignment de agentes, tags, notas.

**Risco:** Baixo para referência. Alto para incorporação (stack diferente).

---

## 4. N8N

| Campo | Valor |
|-------|-------|
| URL | https://github.com/n8n-io/n8n |
| Licença | **Sustainable Use License** (fair-code) — **NÃO é OSI-compliant** |
| Stack | TypeScript |
| Workflows | ✅ |
| Triggers | ✅ |
| Schedule | ✅ |
| AI workflows | ✅ |
| 400+ integrations | ✅ |
| Docker | ✅ |
| Maturidade | Muito alta |
| RAM | ~500MB-1GB |

**Classificação:** `DO NOT USE` — Licença Sustainable Use **NÃO permite uso comercial sem restrições**. Não é open source no sentido OSI. Usar apenas como `REFERENCE` para design de workflow engine.

**Risco:** Alto. Licença proíbe uso comercial em competição com n8n. Código não pode ser reutilizado.

---

## 5. VALHALLA

| Campo | Valor |
|-------|-------|
| URL | https://github.com/valhalla/valhalla |
| Licença | **BSD** |
| Stack | C++ |
| Routing | ✅ |
| ETA | ✅ |
| Distance matrix | ✅ |
| Isochrones | ✅ |
| Map matching | ✅ |
| Tour optimization (TSP) | ✅ |
| OpenStreetMap | ✅ |
| Docker | ✅ |
| Maturidade | Muito alta (Linux Foundation) |
| RAM | ~2-8GB (depende do tamanho do mapa) |
| CPU | Alto (pré-processamento) |

**Classificação:** `USE AS SERVICE` — Candidato principal a routing engine. Licença BSD é permissiva. Funcionalidades completas para dispatch/logística.

**Risco:** Baixo. BSD é permissivo. Complexidade de部署 (precisa de mapa OSM pré-processado).

---

## 6. OSRM

| Campo | Valor |
|-------|-------|
| URL | https://github.com/Project-OSRM/osrm-backend |
| Licença | **BSD-2-Clause** |
| Stack | C++ |
| Routing | ✅ |
| Shortest path | ✅ |
| Distance matrix | ✅ |
| ETA | ✅ |
| OpenStreetMap | ✅ |
| Docker | ✅ |
| Maturidade | Muito alta |
| RAM | ~2-4GB |
| Performance | Extremamente rápida (Contraction Hierarchies) |

**Classificação:** `BENCHMARK ONLY` — Mais rápido que Valhalla para rotas simples, mas menos funcional (sem isochrones, sem TSP). Comparar performance antes de decidir.

**Risco:** Baixo. BSD é permissivo.

---

## 7. MAPLIBRE GL JS

| Campo | Valor |
|-------|-------|
| URL | https://github.com/maplibre/maplibre-gl-js |
| Licença | **BSD-3-Clause** |
| Stack | TypeScript/WebGL |
| Vector tiles | ✅ |
| Markers | ✅ |
| Layers | ✅ |
| Routes | ✅ |
| Heatmap | ✅ |
| React integration | ✅ (react-map-gl) |
| Docker | N/A (lib frontend) |
| Maturidade | Alta |
| RAM | ~50-100MB (browser) |

**Classificação:** `USE` — Candidato principal para live map do GasFlow. BSD é permissivo. Substitui Mapbox GL que mudou licença.

**Risco:** Muito baixo. BSD-3-Clause é permissivo. Comunidade ativa.

---

## 8. COOLIFY

| Campo | Valor |
|-------|-------|
| URL | https://github.com/coollabsio/coolify |
| Licença | **Apache 2.0** |
| Stack | PHP/Laravel + Vue.js |
| Docker | ✅ |
| Databases | ✅ |
| Services | ✅ |
| Environments | ✅ |
| Multi-server | ✅ |
| Maturidade | Alta |
| RAM | ~500MB-1GB |

**Classificação:** `USE AS SERVICE` — Candidato a deployment layer para self-hosting. Apache 2.0 é permissivo. Gerencia Docker, databases, SSL, domains.

**Risco:** Baixo. Apache 2.0 é permissivo. Alternativa sólida a Vercel/Heroku.

---

## 9. METABASE

| Campo | Valor |
|-------|-------|
| URL | https://github.com/metabase/metabase |
| Licença | **AGPL** |
| Stack | Clojure + React |
| BI | ✅ |
| Dashboards | ✅ |
| SQL | ✅ |
| Embedding | ✅ (Pro) |
| Stars | ~44k |
| Docker | ✅ |
| Maturidade | Muito alta |
| RAM | ~1-2GB |

**Classificação:** `USE AS OPTIONAL SERVICE` — BI potente, mas AGPL requer que qualquer modificação seja compartilhada. Usar como optional analytics, não como dependência obrigatória.

**Risco:** Médio. AGPL é copyleft — se integrar profundamente, código GasFlow precisaria ser AGPL. Manter como serviço separado.

---

## 10. POSTHOG

| Campo | Valor |
|-------|-------|
| URL | https://github.com/posthog/posthog |
| Licença | **MIT** (core) + EE parts |
| Stack | Python/Django + React |
| Product analytics | ✅ |
| Session replay | ✅ |
| Feature flags | ✅ |
| Experiments | ✅ |
| Stars | ~39k |
| Docker | ✅ |
| Maturidade | Alta |
| RAM | ~2-4GB (ClickHouse) |

**Classificação:** `BENCHMARK ONLY` — Muito pesado para self-hosting simples. Usar como referência de product analytics. Feature flags úteis mas podem ser implementados nativamente.

**Risco:** Baixo (MIT). Mas peso operacional alto.

---

## 11. ERPNEXT

| Campo | Valor |
|-------|-------|
| URL | https://github.com/frappe/erpnext |
| Licença | **GPL-3.0** |
| Stack | Python/Frappe Framework |
| ERP | ✅ |
| Inventory | ✅ |
| Accounting | ✅ |
| POS | ✅ |
| CRM | ✅ |
| Workflows | ✅ |
| Stars | ~22k |
| Docker | ✅ |
| Maturidade | Muito alta |
| RAM | ~2-4GB |

**Classificação:** `DO NOT USE` — GPL-3.0 é copyleft forte. Incorporar código ERPNext obrigaria GasFlow a ser GPL. Usar apenas como `REFERENCE` para modelagem de domínio.

**Risco:** Extremo. GPL contaminaria todo o projeto GasFlow.

---

## MATRIZ DE DECISÃO FINAL

| # | Projeto | Licença | Decisão | Uso no GasFlow |
|---|---------|---------|---------|----------------|
| 1 | Evolution API | Apache 2.0 | **USE AS SERVICE** | Substituto potencial do WhatsApp provider |
| 2 | Baileys | Custom | **USE AS LIBRARY** | Engine WhatsApp leve (verificar licença) |
| 3 | Chatwoot | MIT | **USE AS REFERENCE** | Arquitetura de inbox/conversas |
| 4 | n8n | Sustainable Use | **DO NOT USE** | Apenas referência conceitual |
| 5 | Valhalla | BSD | **USE AS SERVICE** | Routing engine principal |
| 6 | OSRM | BSD-2 | **BENCHMARK ONLY** | Comparar com Valhalla |
| 7 | MapLibre | BSD-3 | **USE** | Live map do GasFlow |
| 8 | Coolify | Apache 2.0 | **USE AS SERVICE** | Deployment/self-hosting |
| 9 | Metabase | AGPL | **USE AS OPTIONAL** | Analytics opcional |
| 10 | PostHog | MIT | **BENCHMARK ONLY** | Referência product analytics |
| 11 | ERPNext | GPL-3.0 | **DO NOT USE** | Apenas referência de domínio |

---

## DEPENDÊNCIAS LICENCIADAS PARA INTEGRAR

| Dependência | Licença | Compatível com GasFlow? |
|-------------|---------|------------------------|
| Evolution API | Apache 2.0 | ✅ Sim |
| Baileys | Custom | ⚠️ Verificar termos |
| Valhalla | BSD | ✅ Sim |
| OSRM | BSD-2 | ✅ Sim |
| MapLibre GL JS | BSD-3 | ✅ Sim |
| Coolify | Apache 2.0 | ✅ Sim |

**INCOMPATÍVEIS (não usar código):**
- n8n (Sustainable Use)
- ERPNext (GPL-3.0)
- Metabase (AGPL — OK como serviço separado, não como lib)

---

## PRÓXIMOS PASSOS (WAVE 2+)

| Wave | Foco | Depende de |
|------|------|------------|
| 2 | WhatsApp Provider Abstraction | Wave 1 ✅ |
| 3 | Baileys/Evolution Benchmark | Wave 2 |
| 4 | WhatsApp Reliability | Wave 3 |
| 5 | Scheduler + Durable Worker | Wave 2 |
| 6 | Automation Engine | Wave 5 |
| 7 | CRM Intelligence (já existe 13.1-14) | Wave 1 ✅ |
| 8 | WhatsApp Commerce | Wave 4, 6 |
| 9 | Dispatch + Valhalla/OSRM | Wave 1 ✅ |
| 10 | MapLibre + Realtime | Wave 1 ✅ |
| 11 | Analytics + Heatmap | Wave 1 ✅ |
| 12 | Coolify + Self-Hosting | Wave 1 ✅ |
| 13 | Observability + Backup | Wave 12 |
| 14 | Chaos + E2E | Todos anteriores |

---

**WAVE 1 CONCLUÍDA.**
**STOP. Não iniciar WAVE 2 automaticamente.**
