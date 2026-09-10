# Achados por área — Frontend, WhatsApp, Agent e Docs

> [histórico] Este documento menciona whatsapp-web.js — motor antigo, substituído por Baileys (ver docs/phase16/BAILEYS_MIGRATION.md).


## F-1 · 🟢 Frontend: limpo e integrado (estado atual)

**Evidência:** ESLint sem erros; `tsc -b` limpo; 159/159 testes; rota `/contacts` + menu "Contatos WhatsApp" ligados (ContactsCrmPage não é mais órfã); `UpdateNotifier` montado no DashboardLayout com `window.gasflowUpdater` opcional (no navegador, não renderiza).

**Resíduo:** nenhum TS6133 restante.

## W-1 · 🟢 WhatsApp: auto-recovery implementado (validar em campo)

**Evidência:** evento `logged_out` distinto no BaileysEngine; manager apaga credenciais corrompidas e reinicia com QR novo (antes: 10 reconexões inúteis → conta morta — 13 ocorrências nos logs do app). 86/86 testes, tsc strict OK.

**Pendência (🟡):** validação E2E real — parear, fechar/abrir o app, conferir que o QR regenera. Só possível com o usuário e um celular.

## W-2 · 🟢 `@hapi/boom` declarado

Era dependência transitiva do Baileys importada direto pelo código; agora explícita em `dependencies`.

## A-1 · 🟢 Agent: limpo

27/27 testes, tsc strict OK, sem órfãos, depcheck limpo.

## DOC-1 · 🟡 Documentação com motor antigo espalhado

**Evidência:** 6 arquivos citam `wwebjs` como motor atual (`docs/phase5/…`, `phase15/PENDING_RESOLUTION.md`, `phase16/BAILEYS_MIGRATION.md` descreve a migração, `docs/ARCHITECTURE_AUDIT.md`).

**Ação:** marcar os docs de fase como histórico (banner "superseded") ou atualizar a referência ao motor padrão (Baileys).

## DOC-2 · 🟡 README do desktop vs. realidade

`desktop/README.md` descreve porta 3101 corretamente, mas não menciona auto-update, migration de schema no boot nem o comportamento do `waEnabled`. Atualizar junto com o primeiro release via CI.

## E2E-1 · 🟡 Suite Playwright existe (7 specs) mas não roda neste ambiente

**Evidência:** `find e2e -name '*.spec.ts' | wc -l` → 7; execução local não foi feita na semana (depende de navegador instalado no runner/PC).

**Ação:** garantir que o CI rode o projeto Playwright (está no ci.yml? confirmar job) e, no mínimo, smoke de login + aba Clientes.
