# Dependabot — fechamento na v1.1.7

As **22 atualizações** abertas pelo dependabot foram consolidadas em **4
commits**, uma área por commit, em vez de mergear as 22 branches soltas.

O motivo não é estético: as branches se conflitavam entre si porque três
delas mexiam no **mesmo bloco** de dependências do `react` (as três bumpam
`react`/`react-dom`/`@types/react*`, variando só o subgrupo secundário), e as
duas de `ruff` propunham versões diferentes do mesmo pacote. Mergear em ordem
produzia conflito a cada merge; consolidar resolve uma vez.

Havia ainda uma **inconsistência entre branches**: a de `@vitest/coverage-v8`
sobe o coverage para `^5.0.0` mantendo `vitest` em `^4.1.11`, combinação
impossível (o coverage 5 exige vitest 5). Só a consolidação das branches de
`vitest`/`vite` resolve as duas de uma vez.

Verificação: cada commit passou pela suíte completa da área afetada **antes**
de ser commitado.

| # | Área | Pacote | De → Para | Status |
|---|---|---|---|---|
| 1 | actions | `actions/checkout` | v4 → **v7** | ✅ aplicado |
| 2 | actions | `actions/setup-node` | v4 → **v7** | ✅ aplicado |
| 3 | actions | `actions/setup-python` | v5 → **v7** | ✅ aplicado |
| 4 | actions | `docker/setup-qemu-action` | v3 → **v4** | ✅ aplicado |
| 5 | pip | `pyinstaller` | 6.22.2 → **6.22.3** | ✅ aplicado |
| 6 | pip | `python-multipart` | ≥0.0.31 → **≥0.0.32** | ✅ aplicado |
| 7 | pip | `ruff` | ≥0.16.5 → **≥0.16.8** | ✅ aplicado (PR 0.16.6) |
| 8 | pip | `ruff` | ≥0.16.5 → **≥0.16.8** | ✅ aplicado (PR 0.16.8 — mesma versão, dois PRs) |
| 9 | frontend | `eslint` | ^9.39.5 → **^10.10.0** | ✅ aplicado |
| 10 | frontend | `lucide-react` | ^1.40.0 → **^1.45.0** | ✅ aplicado |
| 11 | frontend | `react` + `react-dom` | ^19.2.8 → **^19.3.0** | ✅ aplicado |
| 12 | frontend | `@types/react` + `@types/react-dom` | ^19.2.x → **^19.3.0** | ✅ aplicado |
| 13 | frontend | `react-hook-form` + `react-router-dom` | ^7.87/^7.18.3 → **^7.88/^7.18.4** | ✅ aplicado |
| 14 | frontend | `vite` | ^8.2.2 → **^8.3.0** | ✅ aplicado |
| 15 | frontend | `vitest` | ^4.1.11 → **^5.0.1** | ✅ aplicado |
| 16 | frontend | `@vitest/coverage-v8` | ^4.1.11 → **^5.0.0** | ✅ aplicado |
| 17 | whatsapp | `dotenv` | ^16.4.7 → **^17.4.2** | ✅ aplicado |
| 18 | whatsapp | `eslint` | ^8.57.1 → **^10.10.0** | ✅ aplicado |
| 19 | whatsapp | `@hapi/boom` | ^9.1.3 → **^10.0.1** | ✅ aplicado |
| 20 | whatsapp | `@types/node` | ^26.5.0 → **^26.6.1** | ✅ aplicado |
| 21 | whatsapp | `typescript` | ^6.0.3 → ^7.0.2 | ⛔ **bloqueado (upstream)** |
| 22 | e2e | `@playwright/test` | ^1.55.0 → **^1.63.0** | ✅ aplicado |

## Os 3 casos que não eram "só trocar a versão"

Bump major de dependência de build não é atualização de número: três exigiram
mudança de código, e em nenhum caso a saída foi voltar a versão.

### 1. ESLint 10 no frontend — `@eslint/js` e `preserve-caught-error`

- O ESLint 10 deixou de trazer **`@eslint/js`** como dependência transitiva.
  O `eslint.config.js` importava o pacote e passou a falhar com
  `ERR_MODULE_NOT_FOUND`. Virou dependência explícita.
- A config recomendada nova liga **`preserve-caught-error`**, que recusa
  `throw new Error(msg)` dentro de um `catch` sem anexar o erro original. Duas
  ocorrências no `AuthProvider` (login e troca de senha) — o erro agora vai em
  `{ cause: err }`, o que aliás é o comportamento correto: a mensagem é
  traduzida para o usuário, mas a causa original deixa de ser perdida no log.

### 2. Vitest 5 no frontend — o shim do `jest-dom`

O Vitest 5 declara `interface Assertion<R extends void | Promise<void>, T>`
(dois parâmetros de tipo). O `@testing-library/jest-dom` 7.0.1 — versão mais
recente publicada — ainda declara `interface Assertion<T = any>` (um).
Mesclagem de interface em TypeScript exige **parâmetros de tipo idênticos**;
como não são, o `skipLibCheck` esconde o erro e a augmentation simplesmente
para de valer: `toBeInTheDocument`, `toHaveFocus`, `toBeEnabled` e o resto
desaparecem do `expect` (29 erros de `tsc`).

`src/test/jest-dom-vitest.d.ts` redeclara a augmentation com a assinatura do
Vitest 5, reaproveitando os tipos de matcher do próprio jest-dom. É um shim
de compatibilidade, comentado como tal, e deve ser removido quando o jest-dom
publicar suporte ao Vitest 5.

### 3. ESLint 10 no serviço WhatsApp — fim do `.eslintrc`

O ESLint 10 **removeu** o suporte ao formato `.eslintrc`; o `.eslintrc.cjs`
do serviço virou `eslint.config.js` (flat):

- as duas dependências avulsas (`@typescript-eslint/eslint-plugin` +
  `/parser`) deram lugar ao pacote meta `typescript-eslint` — a mesma
  convenção que o frontend já usava;
- `--ext .ts` saiu do script de lint: no flat config os `.ts` entram pelo
  `files` do preset, e a flag não existe mais nesse mundo;
- as regras próprias do serviço foram preservadas: `no-console: error` e
  `@typescript-eslint/no-unused-vars` com `argsIgnorePattern: '^_'`;
- o `parserOptions.project` não foi portado porque o preset usado é o
  `recommended` (**sem** type information) — a opção não tinha efeito, já que
  nenhuma regra type-aware estava ligada. Se o serviço adotar
  `recommendedTypeChecked` no futuro, aí sim entra `projectService`.

## O bump bloqueado: TypeScript 7 no WhatsApp

`typescript-eslint` **8.70.0** é a última versão publicada e declara:

```
peerDependencies: { eslint: "^8.57.0 || ^9.0.0 || ^10.0.0",
                    typescript: ">=4.8.4 <6.1.0" }
```

TypeScript 7.0.2 está **fora** dessa faixa — nenhuma versão lançada do lint
entende o TS 7. Subir seria trocar um typecheck que funciona por um lint que
não roda, inversão de prioridade. O bump fica suspenso até o lint acompanhar.

## Dívida herdada, declarada

`npm audit` no serviço WhatsApp acusa **5 alertas HIGH** em `extract-zip`,
chegando por `whatsapp-web.js` → puppeteer → `@puppeteer/browsers`.

- Não foi introduzido por estes bumps: as versões de `extract-zip`,
  `puppeteer` e `whatsapp-web.js` **não mudaram** nos lockfiles.
- A **2.0.1 é a última versão publicada** do `extract-zip` e é exatamente a
  que o `overrides` do projeto já fixa — não existe correção upstream para
  aplicar hoje.
- Nenhum workflow roda `npm audit`, então não bloqueia CI. Fica registrado
  como risco conhecido, a ser revisitado quando houver release corrigida.
