# Falhas e pendências da execução

## Strict progressivo do desktop

A tentativa de remover `@ts-nocheck` de `desktop/src/main/config.ts` e `updater.ts` com `strict: true` falhou no typecheck. Os arquivos restaurados a partir de `dist/` ainda são JavaScript compilado, com helpers `__importStar`/`__createBinding`, `require` e escopo global; o TypeScript reporta redeclarações e parâmetros implícitos. A configuração validada permanece `strict: false` com `@ts-nocheck` inicial.

Próximo passo: reescrever manualmente `config.ts` e `updater.ts` como módulos TypeScript idiomáticos, tipar as interfaces públicas e então habilitar `strict` arquivo a arquivo.

## Validações externas não executadas

- V.1 auto-update em VM Windows limpa não foi executado.
- V.2 pareamento/desconexão do WhatsApp em celular real não foi executado.
- V.3 consulta à release remota não foi repetida nesta retomada.
- E2E Playwright local não foi repetido nesta retomada.

Os roteiros e o workflow CI permanecem registrados; essas verificações dependem de ambiente externo, credenciais ou publicação.
