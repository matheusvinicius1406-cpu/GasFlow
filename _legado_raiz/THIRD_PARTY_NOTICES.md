# Third-Party Notices

Componentes de terceiros efetivamente incorporados por este projeto.

## Matriz de Auditoria

| Componente | Implementação Atual | whatsapp-web.js | WPPConnect | WA-JS | Evolution API | Baileys | WAHA | Melhor Opção | Reutilizar? | Licença | Justificativa |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SessionManager | whatsapp-web.js LocalAuth | ✅ Madura | ✅ | — | ✅ | ✅ | ✅ | whatsapp-web.js | ✅ | Apache-2.0 | Já integrado, maduro |
| QR/Auth | whatsapp-web.js | ✅ Oficial | ✅ | ✅ | ✅ | ✅ Nativo | ✅ | whatsapp-web.js | ✅ | Apache-2.0 | QR oficial do WhatsApp Web |
| SessionPersistence | LocalAuth (SQLite) | ✅ LocalAuth | ✅ | — | ✅ | ✅ | ✅ | whatsapp-web.js | ✅ | Apache-2.0 | Persistência local automática |
| Reconnect | Backoff + Jitter | Básico | ✅ | — | ✅ | ✅ Excelente | ✅ | Baileys (padrão) | Adaptado | MIT | Padrão reimplementado, não copiado |
| ContactSync | Uparter idempotente | ✅ getContacts | ✅ | ✅ | ✅ | ✅ | — | whatsapp-web.js | ✅ | Apache-2.0 | API nativa da lib |
| PhoneNormalization | E.164 digits-only | — | — | — | — | — | — | Próprio | — | — | Regra simples e conservadora |
| Deduplication | JID + Phone + Name | — | — | — | — | — | — | Próprio | — | — | Lógica específica do projeto |
| MessageSender | Provider sendMessage | ✅ sendMessage | ✅ | ✅ | ✅ | ✅ | ✅ | whatsapp-web.js | ✅ | Apache-2.0 | sendMessage nativo |
| Queue | Fila em memória | — | — | — | ✅ Fila | — | ✅ | Próprio (memória) | — | — | Escopo pequeno, sem Redis |
| Retry | Controlado por worker | — | — | — | ✅ | ✅ | ✅ | Próprio | — | — | Lógica de broadcast específica |
| Events | Client events | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | whatsapp-web.js | ✅ | Apache-2.0 | Eventos nativos da lib |
| HealthCheck | getState() | — | ✅ /session-state | — | — | — | ✅ /health | WAHA (padrão) | Adaptado | Apache-2.0 | Padrão reimplementado |
| Logging | console.log/warn/error | — | — | — | ✅ | — | ✅ | Próprio | — | — | Logs simples, sem framework |
| ErrorHandling | try/catch + JSON | — | — | — | ✅ | ✅ | ✅ | Próprio | — | — | Tratamento básico da API |

## Dependências (npm)

### whatsapp-web.js
- **Versão:** ^1.26.0
- **Origem:** https://github.com/wwebjs/whatsapp-web.js
- **Licença:** Apache License 2.0 (confirmada em `node_modules/whatsapp-web.js/package.json`)
- **Uso:** cliente WhatsApp Web — sessão, autenticação QR via `LocalAuth`, eventos de ciclo de vida (`qr`, `authenticated`, `ready`, `auth_failure`, `disconnected`) e `getContacts`. É a implementação do `WhatsAppProvider` (src/provider/wwebjs-provider.ts).
- **Modo de reutilização:** dependência npm, sem cópia de código-fonte.

### qrcode
- **Versão:** ^1.5.4
- **Origem:** https://github.com/soldair/node-qrcode
- **Licença:** MIT (confirmada em `node_modules/qrcode/package.json`)
- **Uso:** renderização do QR oficial (PNG data URL e SVG) no endpoint `/api/whatsapp/qr` e página `/connect`.
- **Modo de reutilização:** dependência npm.

### express
- **Versão:** ^4.21.2
- **Origem:** https://github.com/expressjs/express
- **Licença:** MIT (confirmada em `node_modules/express/package.json`)
- **Uso:** servidor HTTP da API.
- **Modo de reutilização:** dependência npm.

## Padrões adaptados (sem cópia de código)

Os padrões abaixo foram **inspirados** em projetos maduros, mas reimplementados para nossa arquitetura — nenhum trecho foi copiado verbatim:

| Padrão | Inspiração | Repositório | Licença | Onde aplicamos |
|---|---|---|---|---|
| Reconexão com backoff exponencial + jitter aleatório | Baileys (`socket.ts` usa delay exponencial com variação) | github.com/WhiskeySockets/Baileys | MIT | `withJitter()`/`scheduleReconnect()` em src/provider/wwebjs-provider.ts |
| Health check leve via estado da sessão | WPPConnect Server (`/session-state`) e WAHA (`/health`) | github.com/wppconnect-team/wppconnect-server · github.com/devlikeapro/waha | Apache-2.0 · MIT (core) | `healthCheck()` e endpoints `/api/whatsapp/health`, `/api/health` |
| Interface neutra de provider orientada a eventos | whatsmeow (event handlers tipados) | github.com/tulir/whatsmeow | Apache-2.0 | contrato `WhatsAppProvider` em src/provider/types.ts |
| Estados de conexão nomeados (connecting/qr/open/close) | Evolution API (status de instância) | github.com/EvolutionAPI/evolution-api | Apache-2.0 | `WhatsAppConnectionState` |
| Protection mode com limiar de falhas | Evolution API (segurança de envio) | github.com/EvolutionAPI/evolution-api | Apache-2.0 | `shouldActivateProtection()` em src/broadcast.ts |
| Worker de broadcast com cooldown entre envios | WAHA (rate limiting) | github.com/devlikeapro/waha | Apache-2.0 | `SEND_INTERVAL_MS` em src/broadcast.ts |

## Projetos auditados (referência apenas)

| Projeto | Licença | Usado? | Motivo |
|---|---|---|---|
| whatsapp-web.js | Apache-2.0 | ✅ Sim (engine principal) | Solução madura para WhatsApp Web |
| Baileys | MIT | Padrões apenas | API WebSocket nativa, diferente do nosso caso |
| WPPConnect | LGPL-3.0 | ❌ Não | Licença incompatível com uso proprietário |
| WA-JS | Apache-2.0 | Referência apenas | Biblioteca auxiliar, não necessária |
| Evolution API | Apache-2.0 | Padrões apenas | Plataforma completa, muito além do escopo |
| WAHA | Apache-2.0 | Padrões apenas | Referência arquitetural |

## Decisões de auditoria

- **whatsapp-web.js mantido como engine**: já resolve sessão, QR, persistência (`LocalAuth`) e eventos de forma madura. Trocar por Baileys/WPPConnect traria reescrita sem ganho para o escopo atual.
- **Baileys, WPPConnect, Evolution, WAHA, whatsmeow**: auditados apenas como referência de padrões; nenhum código copiado.
- **WPPConnect descartado**: licença LGPL-3.0 é incompatível com uso proprietário sem compartilhamento de código.
- Projeto sem licença própria definida ainda: ao definir, verificar compatibilidade (Apache-2.0/MIT são compatíveis entre si e com uso proprietário, com retenção de avisos).
