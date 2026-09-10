# Falhas e pendências da execução

## Strict progressivo do desktop

Resolvido na branch `refactor/desktop-sources`: `config.ts`, `updater.ts` e `logger.ts` foram reescritos como módulos TypeScript tipados, sem `@ts-nocheck`. O `typecheck`, build e os 11 testes do desktop passaram.

## Validações externas não executadas

- V.1 auto-update em VM Windows limpa não foi executado.
- V.2 pareamento/desconexão do WhatsApp em celular real não foi executado.
- V.3 consulta à release remota não foi repetida nesta retomada.
- E2E Playwright local não foi repetido nesta retomada.

Os roteiros e o workflow CI permanecem registrados; essas verificações dependem de ambiente externo, credenciais ou publicação.
