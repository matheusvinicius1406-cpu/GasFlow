# ADR-0005 — Formatter do nome de rota e fallbacks

**Status:** Aceito · **Data:** 2026-09-29 · **Fase:** 2 (etapa 7)
**Relacionado:** `docs/adr/ADR-0001-renomeador-contatos-vcf.md` (D1/D2/D5/D7),
`docs/adr/ADR-0002-preview-apply-desacoplados.md`,
`docs/adr/ADR-0004-cache-geocoding-por-rua.md`,
`docs/prompts/renomeador-contatos-fase2.md` (§9 etapa 7, §7 contrato).

---

## Contexto

A Fase 1 mostrou que o formato-alvo já existia como **código morto**:
`Client.crm_name` montava `"{codigo}= {rua} Nº{numero} ({nome})"` e não era
chamado em lugar nenhum (G8). O `ContactOrganizer`, por sua vez, só sabia gerar
`"Nome — Bairro"` (G4). Faltava o elo entre os dados já estruturados do contato
(`rua`, `numero`, `cep`, `entre_ruas`, `cidade`, `uf`, `lat`, `lng` — colunas
adicionadas nas etapas 2–6) e o renomeador em lote.

O formato final é o da D5:

```
{codigo}= {rua} Nº {numero} entre {ruaA} e {ruaB} - CEP {cep} ({nome})
```

## Decisão

### 1. O formatter é uma função de aplicação, não do domínio

`app/application/contacts/formatter.py`, funções puras:

| Função | Papel |
|---|---|
| `formatar_nome_rota(cliente, entre_ruas=None)` | monta o nome no padrão D5 |
| `limpar_codigo(nome)` | remove prefixo de código legado (`114= …`) |
| `nome_da_pessoa(cliente)` | extrai o nome humano (idempotência) |
| `codigo_padding_zero(codigo)` | `"000001"` → `"1"` (D7) |

Fica em `application/` porque **compõe** domínio (`Client`) e o resultado do
geocoding — não é uma regra do agregado `Client`. `crm_name` no domínio nunca é
chamado por ninguém; o formatter o substitui como a única fonte do formato.
(`crm_name` **não** é removido nesta etapa: remoção de superfície pública do
domínio é mudança própria, com teste próprio.)

### 2. Fallbacks: só os três da D5 (D2 — nunca inventar)

- sem `entre_ruas` → omite `entre ...`;
- sem `cep` → omite `- CEP ...`;
- sem `has_name` ou sem nome humano → omite `({nome})`.

**Não** há tratamento especial para os placeholders `rua = "A definir"` e
`numero = "S/N"`: eles são **valores válidos** da coluna e saem como estão. A
separação “endereço resolvido × pendente” é do campo explícito
`geocode_status` (D3), não de heurística sobre o texto do nome — exatamente a
razão pela qual a D3 substituiu a heurística de rua. Inventar um fallback
(“omitir se A definir”) seria criar um segundo critério de triagem fora da D3.

### 3. `({nome})` só com `has_name` — e o modo endereço não promove `has_name`

`has_name` distingue nome de pessoa de placeholder do import
(`Contato 1199…`). O `apply_rename` promovia `has_name = True` após renomear
(comportamento do padrão “Nome — Bairro”). No modo endereço isso **quebraria a
idempotência**: o primeiro apply omitiria o placeholder, o segundo o incluiria.
O `apply_rename` passa a promover `has_name` **apenas quando a regra não é
`pattern_endereco`**.

### 4. Código: banco com 6 dígitos, nome sem zeros (D7)

A coluna `codigo` continua `000001`; o formatter emite `1=`. É apresentação, não
identidade — nenhuma migração de dados.

### 5. Idempotência pelo prefixo `^\d+\s*=\s*`

Aplicar o formatter a um contato cujo `nome` **já é** um nome de rota devolve o
mesmo texto:

1. se `nome` casa `^\d+\s*=\s*`, o nome humano é recuperado do sufixo
   `(...)` do fim da linha;
2. sem sufixo, `nome_da_pessoa` devolve `""` — o endereço **não** é reciclado
   como se fosse nome de pessoa (repetir o endereço seria pior que omitir).

Isso torna `preview → apply → apply` estável: o segundo apply devolve
`unchanged`, e o audit não registra uma “mudança” que não houve.

### 6. Integração: `pattern_endereco` na regra existente

`build_rename_rule(..., pattern_endereco=True)` liga o modo. Um único ponto de
decisão (`organizer.build_new_name`) escolhe entre o formatter e
`apply_rename_rule`; preview, seleção por filtro e apply continuam os mesmos
(ADR-0002), com a mesma trava anti-corrida (`stale`) e o mesmo audit
`contact.rename`. `pattern_endereco` **tem precedência** sobre `pattern_bairro`
quando ambos vêm ligados — o endereço já contém o bairro.

O par “entre ruas” pode ser injetado por parâmetro
(`formatar_nome_rota(cliente, entre_ruas=...)`) para a etapa 8 usar o par
derivado das interseções (`GeocodingService.entre_ruas_do_contato`) sem
depender da coluna `clients.entre_ruas`.

## Consequências

- O formato-alvo deixa de ser código morto e passa a ter **teste próprio**
  (`tests/test_contacts_formatter.py`, 15 casos) + integração no organizer
  (`TestRenamePatternEndereco`).
- Aditivo: `pattern_endereco` é `False` por default; nenhuma regra existente
  (`trim`/`case`/`pattern_bairro`) muda de comportamento.
- Contatos sem endereço saem com o código (e o nome, se houver) — a triagem é
  a mesma da D3, não um novo critério.

## Limites do que está provado (não ler como medido)

- O formatter está provado **em unidade e no organizer**. **Não** existe job em
  lote chamando-o com 10.000 contatos (etapa 8) — a medição de tempo/escala
  continua pendente da etapa 9.
- O par “entre ruas” da coluna só é populado pelo passe Overpass (etapa 8);
  até lá, `entre_ruas` é vazio e o trecho é omitido (D2) — comportamento
  correto, mas não medido em volume.
- Placeholders (`A definir`/`S/N`) sendo renderizados literalmente é decisão
  **consciente** (item 2); se o produto quiser outra coisa, é uma mudança de
  regra com seu próprio ADR.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Reusar `Client.crm_name` no domínio | Não tem CEP/entre-ruas, formata `Nº{numero}` sem espaço, e acopla o domínio ao texto de apresentação |
| Pôr o formatter em `infrastructure/` | Ele não fala com provedor nenhum; é composição de campos do contato |
| Omitir trechos quando o valor é `A definir`/`S/N` | Cria um segundo critério de triagem fora da D3 e some com dado real da coluna |
| Promover `has_name` no modo endereço | Quebra a idempotência (o placeholder omitido no 1º apply apareceria no 2º) |
| Detectar “já é rota” por heurística ampla (contém `Nº`) | Nome de pessoa pode conter `Nº`; o prefixo `^\d+\s*=\s*` é o sinal forte e testável |
| Guardar o nome da pessoa numa coluna nova | Aumenta o schema por um dado que o sufixo `({nome})` já carrega (D5) |
