# Falhas e pendências da execução

## Strict progressivo do desktop

Resolvido na branch `refactor/desktop-sources`: `config.ts`, `updater.ts` e `logger.ts` foram reescritos como módulos TypeScript tipados, sem `@ts-nocheck`. O `typecheck`, build e os 11 testes do desktop passaram.

## Validações externas não executadas

- V.1 auto-update em VM Windows limpa não foi executado.
- V.2 pareamento/desconexão do WhatsApp em celular real não foi executado.
- V.3 consulta à release remota não foi repetida nesta retomada.
- E2E Playwright local não foi repetido nesta retomada.

Os roteiros e o workflow CI permanecem registrados; essas verificações dependem de ambiente externo, credenciais ou publicação.

## Instalador Windows

O build local `1.1.1` gerou o instalador e `latest.yml` corretamente, com
frontend, agente e WhatsApp presentes. A inspeção também mostrou que esse
artefato local não tinha Python embutido. O workflow de release agora compila
`backend/gasflow-backend.exe` com PyInstaller e o Electron o prefere quando
empacotado; a validação final desse caminho depende de uma execução do GitHub
Actions ou de PyInstaller instalado localmente.

## Dependências legadas do WhatsApp

O provider opcional `whatsapp-web.js` mantém uma cadeia Puppeteer com cinco
alertas HIGH no `npm audit`. `qs` e outras transitivas foram atualizadas por
overrides, mas remover o restante exige retirar o rollback wwebjs ou migrar
definitivamente para Baileys. O engine padrão já é Baileys; o risco permanece
isolado ao modo legado e está registrado para a migração definitiva.
