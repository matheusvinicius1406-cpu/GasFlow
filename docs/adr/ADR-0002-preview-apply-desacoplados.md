# ADR-0002 — Preview e apply desacoplados no renomeador de contatos

**Status:** Aceito · **Data:** 2026-09-25 · **Fase 2 (§6.4/§18.1)**
**Relacionado:** `docs/adr/ADR-0001-renomeador-contatos-vcf.md`

---

## Contexto

O `ContactOrganizer` (F6) fazia o preview em **uma única leitura de
`page_size=200`** (`organizer.py::preview_rename`). Com o alvo de 10.000
contatos/arquivo (D4), isso trunca a seleção **em silêncio**: a UI pega
`preview.changes` e envia os códigos, renomeando só o primeiro bloco. Não havia
erro, aviso nem contagem — o operador veria "5.000 renomeados" acreditando que
era a base inteira.

Além disso, o `apply_rename` documentava uma trava anti-corrida (*"só grava se o
nome atual ainda é o `before` que o operador viu"*) que **não existia no
código**: `skipped_stale` era inicializado e nunca incrementado. Ou seja, um
sync do WhatsApp entre o preview e o apply renomeava por cima do valor novo.

## Decisão

1. **Preview paginado, sem teto.** `preview_rename` varre *toda* a base que casa
   (leitura lazy, blocos de 500) e devolve **apenas a página pedida** +
   `total`/`page`/`page_size`/`total_pages`. `page_size` clampado em 500.
2. **Seleção por filtro.** `apply_rename` passa a aceitar
   `filtro{bairro,status}` (+ `search`) e `all_matching=True`, além do
   `codes` legado. Filtros que o `buscar()` do repositório não conhece
   (`bairro` exato normalizado, `status` → `OK`/`NAO_ENCONTRADO`/`PENDENTE`/
   `SEM_ENDERECO`) são resolvidos no organizer.
3. **Nada de "aplicar a todos" implícito.** Sem `codes`, sem `filtro` e sem
   `all_matching=True`, o método levanta `ValueError` → **HTTP 422**. O
   "todos" existe, mas precisa ser dito.
4. **Trava anti-corrida implementada.** `expected={codigo: nome_visto}` (vindo
   do preview) faz o contato ser pulado como `stale` quando o nome atual
   diverge.

## Consequências

- O teto de 200 deixa de existir na varredura; o `total` do preview passa a ser
  a contagem real de mudanças.
- O default do endpoint `rename-preview` ficou em **`page_size=200`** por
  paridade exata com a UI atual (que ainda envia `codes`). Sem isso, a UI
  legada passaria a aplicar 100 em vez de 200 — uma quebra silenciosa nova.
- A UI paginada (com filtro/job) é a Fase 2 §13; o caminho `codes` continua
  funcionando enquanto isso.
- Segurança do I3 preservada e agora **real**: o `expected` é opcional, então a
  UI só ganha a trava quando passar a enviá-lo.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter 200 e paginar só na UI | O teto voltaria a truncar no dia em que a UI enviasse a lista inteira |
| Preview devolvendo todos os 10k de uma vez | Payload gigante e sem paginação de verdade |
| Aplicar por lista de códigos sempre | 10k IDs no corpo; o prompt §6.4 pede seleção por filtro |
| Guardar um "snapshot" de IDs no servidor | Mais estado e expiração; o audit por contato já dá a rastreabilidade |
