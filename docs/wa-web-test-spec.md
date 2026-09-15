# Spec — Sessão de Teste Manual: Painel WhatsApp Web (F0–F2)

**Data:** 2026-09-15
**Status:** planejado (aguardando execução)
**Pedido do usuário:** "se for possível, abra na minha tela o QR code de conexão e vamos testar… claro, assim que finalizarmos."
**Doc técnico de referência:** `docs/whatsapp-web-panel.md` (arquitetura, flag, riscos, plano F0–F5)
**Resultado esperado:** QR de conexão do WhatsApp Web visível **na tela do usuário** dentro do painel Electron, com pareamento completo da conta principal e de uma conta secundária, e resultados registrados no doc principal.

---

## 1. Escopo

### Incluído (esta sessão)

| Fase | O que valida |
|---|---|
| **F0** | WA Web carrega dentro da `WebContentsView` e o **QR aparece no placeholder** da tela `/whatsapp/web` |
| **F1** | Moldura React (abas "Principal"/"Secundária", badges de estado, botões) desenha em volta da view; a view só ocupa a área do placeholder |
| **F2** | **Duas contas pareadas simultaneamente** (principal + 2º número do usuário), sem interferência entre elas; validação de recebimento duplo (Baileys + view) com mensagem real |

### Fora do escopo (ficam para depois)

- **F3** (status bridge na desconexão), **F4** (persistência pós-restart), **F5** (flag off) — fases seguintes do plano.
- Qualquer mudança de código. Esta sessão é **apenas execução de teste + registro**. O módulo `whatsapp/src/` (Baileys + anti-ban) não deve ser tocado.
- Deploy do relay e integração end-to-end do app do entregador (pendências separadas).

---

## 2. Pré-condições e estado atual verificado (15/09)

| Item | Estado |
|---|---|
| Suíte desktop | **41/41 pass** (`npm test` em `GasFlow/desktop`, executado 15/09 antes da sessão) |
| Suíte frontend | **194/194 pass** (`npx vitest run` em `GasFlow/frontend`, executado 15/09) |
| `frontend/dist` | Existe (`GasFlow/frontend/dist/index.html` presente) — Electron serve o frontend empacotado |
| `settings.json` | `%APPDATA%\Roaming\gasflow-desktop\settings.json` — **sem a chave `waWebPanel`** (usa default `enabled: false` de `config.ts`) |
| Sessão Baileys | Diretório `baileys_auth/` presente no userData — conta principal provavelmente pareada (device #1) |
| App | Não estava rodando no início da sessão |
| Backend/WA ports | Backend `127.0.0.1:8000`, WhatsApp bridge `127.0.0.1:3101` (defaults de `config.ts`) |

### Ação obrigatória antes de abrir o app

1. Editar `%APPDATA%\Roaming\gasflow-desktop\settings.json` **preservando todas as chaves existentes** (`waApiKey`, `backendAdminPassword`, modelos ollama `qwen3:0.6b`, `waAutoReply: true`, `whisper*`, `waEnabled`) e adicionar:
   ```json
   "waWebPanel": { "enabled": true }
   ```
2. **Não regenerar** o arquivo inteiro — merge cirúrgico apenas desta chave.

---

## 3. Como abrir o app (decisão do usuário)

- **Modo dev:** `npm start` em `GasFlow/desktop` (roda `electron .` com o código atual + `frontend/dist`), em **background**, com o Electron aparecendo na tela do usuário.
- Se o app não subir ou o painel não existir, diagnosticar por `electron-log` em `%APPDATA%\Roaming\gasflow-desktop\logs\` antes de qualquer outra ação.

---

## 4. Condutas acordadas (decisões de entrevista)

| Situação | Conduta |
|---|---|
| **Verificação por fase** | Olhos do usuário confirmam o visual (QR, moldura, badges); o agente cruza com evidências de log (`electron-log`) e push de status IPC |
| **QR não aparece (F0)** | **Parar e reportar** — seguir o doc §3 à risca: registrar o resultado, nenhuma tentativa de contorno, discutir o bloqueio antes de prosseguir. Janela de espera pelo QR: **até 90s** antes de declarar falha (sem auto-reload da view) |
| **Falha em fase intermediária** | **Parar na 1ª falha** — nenhuma fase subsequente é executada; registrar veredito + evidências e encerrar a coleta |
| **Diálogos inesperados do WA Web** (ex.: "atualize seu navegador") | **O usuário opera a página** (é uma sessão WA Web normal); se o diálogo sugerir problema de UA pinado, registrar como observação |
| **Validação de recebimento duplo** | Durante a F2, **enviar mensagem real** de outro telefone para o número pareado e confirmar que **ambos** os devices (Baileys + view) recebem — valida a seção 5 do doc |
| **Estado final da view secundária** | **Fechar a view E limpar a sessão** (`Partitions/wa-web-secondary`) — menos rastro do 2º número na máquina; um novo pareamento exigirá novo QR |
| **Feature flag no fim** | Usuário decide no chat após a F2. **Se não se manifestar: deixar `enabled: true`** e registrar a decisão como **pendente** na seção 8 do doc |

### Expectativa já aprovada pelo usuário (doc §5)

Ao parear o QR da view, o número principal passa a ter **dois dispositivos conectados** (Baileys = device #1, view = device #2). Ambos recebem mensagens — **não é bug**. O envio pelo Baileys continua 100% intacto.

---

## 5. Passo a passo por fase (com critérios e evidências)

### F0 — WA Web carrega e QR aparece

1. Habilitar flag (§2), rodar `npm start`, aguardar boot (backend + wa bridge).
2. Usuário abre a tela **WhatsApp Web** (`/whatsapp/web`, guard `whatsapp.read`) e clica **"Abrir painel"** na aba "Principal".
3. **Critério:** QR do WA Web visível na área do placeholder em até 90s.
4. **Evidências a coletar:**
   - Log `wa-web-panel`: criação da view, partição `persist:wa-web-primary`, UA Chrome/128.
   - Push de status IPC (`gasflow:wa-web-status`) → badge na aba muda (ex.: `qr` → aguardando scan).
   - Log de permissões negadas (câmera/mic/geo/notificações) na primeira carga.
5. Usuário escaneia o QR com o celular (WhatsApp → Dispositivos conectados).
6. **Critério pós-scan:** badge → "Conectado"; WA Web mostra a conversa; log registra `did-finish-load` + healthcheck de presença OK.

### F1 — Moldura React

1. **Critério:** abas, badges e botões ("Abrir painel" / "Re-parear" / "Fechar") desenhados em volta da view; a view cobre **apenas** o placeholder (sem sobrepor sidebar/topbar).
2. Redimensionar levemente a janela → a view segue o placeholder (ResizeObserver → bounds).
3. **Evidências:** log de bounds aplicados (IPC `wa-web:bounds`), ausência de erros no console do main.

### F2 — Duas contas simultâneas

1. Aba "Secundária" → **"Abrir painel"** → aparece segundo QR (partição `persist:wa-web-secondary`).
2. Usuário pareia com o **2º número**.
3. **Critério:** ambas as abas "Conectado" ao mesmo tempo, sem interferência (trocar de aba não derruba a outra).
4. **Teste de recebimento duplo:** de um terceiro telefone, enviar mensagem para o número principal → confirmar que **Baileys E view** recebem (esperado por design).
5. **Encerramento da fase:** fechar a view secundária e limpar `Partitions/wa-web-secondary` (conduta §4).

---

## 6. Registro dos resultados

- **Onde:** nova seção **"8. Log de testes manuais"** no `docs/whatsapp-web-panel.md` (o doc principal permanece a referência técnica fixa).
- **Formato por fase:** veredito (**OK / FALHA / NÃO EXECUTADO**) + observação + **trechos de log/IPC relevantes** com timestamp.
- **Fim da sessão:** re-executar as suítes (desktop `npm test`, frontend `npx vitest run`) e registrar os números de regressão no log (esperado: 41 e 194, já que nenhuma linha de código deve mudar).
- **Decisão da flag:** registrada na mesma seção (escolha do usuário ou "pendente — flag mantida ON por default acordado").
- **Spec:** este arquivo (`docs/wa-web-test-spec.md`) é o plano; o log de execução mora no doc principal.

### Correções de documentação a validar durante a sessão

- O doc diz que a sessão fica em `%APPDATA%/gasflow/Partitions/...` — o userData real observado é **`%APPDATA%\Roaming\gasflow-desktop`** (nome do `package.json`, sem `setName` no main). Se confirmado em disco (`Partitions/wa-web-primary` existe após a F0), **corrigir o doc §4** como parte do registro.

---

## 7. Riscos conhecidos (herdados do doc §6, aplicáveis à sessão)

| Risco | Mitigação nesta sessão |
|---|---|
| Bloqueio server-side do WA ao UA pinado (QR nunca aparece) | Conduta "parar e reportar"; 90s de espera; sem retry automático |
| DOM do WA Web mudou (healthcheck falha) | Healthcheck lê só presença de elementos; registrar qualquer falso-negativo como observação |
| Diálogos inesperados na página | Usuário opera a página; registrar sintoma |
| Parear a view pode disparar rate limit do WA | Uma view por conta, zero automação, sem multi-login da mesma conta |

---

## 8. Critérios de aceite da sessão

1. QR visível na tela do usuário (F0) e pareamento da conta principal concluído.
2. Moldura React correta em volta da view (F1).
3. Duas contas conectadas simultaneamente + mensagem real recebida pelos dois devices (F2).
4. View secundária fechada com sessão limpa ao final.
5. Seção "8. Log de testes manuais" preenchida com vereditos + evidências + números das suítes.
6. Decisão da flag registrada (explícita ou "pendente, mantida ON").
7. **Zero mudanças de código** neste fluxo (somente `settings.json` + docs).
