# ADR-0003 — Importação de contatos em lote (uma transação por bloco)

**Status:** Aceito · **Data:** 2026-09-25 · **Fase 2 (§18 etapa 4)**
**Relacionado:** `docs/adr/ADR-0001-renomeador-contatos-vcf.md`,
`docs/adr/ADR-0002-preview-apply-desacoplados.md`

---

## Contexto

O `ContactService.sync_batch` processava o lote **contato por contato**,
chamando `upsert_contact` N vezes. Cada contato custava: 1 `SELECT` de telefone,
1 `INSERT`/`UPDATE`, 1 `COMMIT` e 1 `SELECT` de `refresh` — quatro idas ao banco
**por linha**.

Medido com `before_cursor_execute` (SQLite, 1.200 contatos):

| Caminho | Statements SQL | Commits |
|---|---|---|
| Antes (`upsert_contact` em loop) | **4.800** | 1.200 |
| Depois (`sync_batch`) | **1.206** | 3 |

Isso já era ruim para o sync do WhatsApp e fica **inviável** para o alvo do
renomeador: 10.000 contatos por arquivo (D4), com pico de 20.000. Extrapolando
a medição, eram ~40.000 statements e 10.000 commits por importação — minutos de
contenção de write lock no SQLite pelo ganho de zero função nova.

## Decisão

1. **Uma transação por bloco de 500 contatos** (`_UPSERT_CHUNK`).
   500 é o teto que mantém o `IN` de telefones abaixo do limite de variáveis por
   statement do SQLite (999). 10.000 contatos = 20 transações.
2. **Dois métodos novos no contrato do repositório** (`ClientRepository`), com
   implementação padrão (fallback linha a linha) para não quebrar nenhuma
   implementação existente:
   - `buscar_por_telefones(telefones) -> {telefone: Client}` — um `SELECT ... IN`
     por bloco em vez de N `SELECT`s;
   - `salvar_lote(criar, atualizar)` — `add_all` + 1 `COMMIT`; as linhas de
     update saem de um único `IN` por id (o `atualizar` por linha re-consultava
     o modelo).
3. **Contador de código por bloco.** `proximo_codigo()` continua sendo a fonte
   (`maior codigo + 1`), mas é lido **uma vez por bloco** e incrementado em
   memória. O `codigo` passou a ser parâmetro de `_build_new_client` — nunca
   mais 1 `SELECT` por contato criado.
4. **Telefone repetido no mesmo bloco é resolvido em memória.** O 2º card do
   mesmo telefone enriquece o objeto já agendado e entra uma única vez no
   `INSERT`. Sem isso, os dois cards virariam dois inserts e o bloco inteiro
   morreria numa `UNIQUE constraint`.
5. **Tudo ou nada por bloco, com rede de segurança.** Se `salvar_lote` falhar,
   o bloco é **refeito linha a linha** (`_sync_chunk_linha_a_linha`), onde cada
   contato tem o seu próprio `try/except`. O contrato antigo — *"lote nunca
   aborta por 1 contato ruim"* — continua valendo, agora com o custo pago só
   no caminho de exceção.
6. **Convite de comunidade (F5) depois do commit**, a partir de tuplas
   `(codigo, nome, telefone)` capturadas antes. Ler os atributos das entidades
   depois do `COMMIT` custaria 1 `SELECT` por contato (os objetos expiram).

## Consequências

- 4.800 → **1.206** statements e 1.200 → **3** commits para 1.200 contatos
  (10.000 contatos: 20 commits em vez de 10.000).
- O resultado por contato (`created`/`updated`/`unchanged`/`error`) é
  **idêntico e na mesma ordem** da entrada — a paginação/contadores do
  `import-vcf` não mudam de contrato.
- `ContactService` passou a depender de `buscar_por_telefones`/`salvar_lote`;
  repositórios de teste que não os implementam caem no fallback por bloco e
  continuam funcionando (lá o bloco falha e o serviço refaz linha a linha).
- O payload de resposta do `import-vcf` continua devolvendo os 10.000 resultados
  em JSON — o corte disso é a etapa 8 (job bounded-batch + UI paginada).

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| `bulk_insert_mappings` (Core) direto | Fura a entidade de domínio e as validações do `Client`; e não serve para o update "só enriquece" |
| Manter `upsert_contact` em loop e só aumentar o `page_size` | Não existe `page_size` de importação; o custo é por linha, não por página |
| Blocos de 1.000 | 1.000 telefones no `IN` passam do limite de parâmetros do SQLite |
| Só o usuário final decidir o tamanho do bloco | Superfície de API nova sem ganho: 500 já satura o ganho medido |
| Sem fallback linha a linha | 1 telefone duplicado no arquivo derrubaria 500 contatos de uma vez |
