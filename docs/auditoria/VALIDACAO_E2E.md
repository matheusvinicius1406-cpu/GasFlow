# Validação E2E — roteiro manual (V.1 e V.2)

> Estes testes precisam de **VM Windows limpa** e **celular real** — não rodam
> na máquina de desenvolvimento. Execute os passos na ordem e marque os
> critérios de aceite. A V.3 (release check) já foi validada automaticamente
> (assets + `latest.yml` conferidos na release `v1.1.1`).

---

## V.1 — Auto-update (ex.: 1.1.1 → 1.1.2)

**Pré-requisitos:** VM Windows limpa, sem GasFlow instalado (ou com a versão
anterior já instalada), acesso à internet e ao GitHub Releases do repositório.

| # | Passo | Critério de aceite |
|---|-------|--------------------|
| 1 | Instalar a versão anterior (`GasFlow Desktop Setup <anterior>.exe`) e abrir o app | Janela abre, login funciona |
| 2 | Aguardar ~30s (checagem inicial 15s + download) | Toast/notificação de atualização disponível aparece |
| 3 | Abrir o log `%APPDATA%/gasflow-desktop/logs/main.log` | Presentes `updater` "verificando atualizações…" e "nova versão disponível: v<nova>" |
| 4 | Clicar em **"Reiniciar e instalar"** (ou fechar o app) | Instalador roda e o app reabre sozinho |
| 5 | Conferir a versão nova: log de boot ou `release/latest.yml` baixado | `app.version` = versão nova; no log aparece `updater` "v<nova> baixada — pronta para instalar" |
| 6 | Reabrir o app e aguardar nova checagem | Log mostra "sem atualizações (v<nova> é a mais recente)" — sem loop de update |

**Falha esperada se:** sem internet (log `updater erro:` + app segue
funcionando) · release sem `latest.yml` (log `erro:` e nada quebra).

---

## V.2 — WhatsApp: recuperação de sessão

**Pré-requisitos:** app aberto com `waEnabled` ausente ou `true` (default) e
um **celular real** com WhatsApp dedicado ao teste (não use número pessoal).

| # | Passo | Critério de aceite |
|---|-------|--------------------|
| 1 | No app, abrir a tela WhatsApp e parear o **QR Code** com o celular | Status "conectado" no app; log `wa` mostra sessão ativa |
| 2 | Enviar uma mensagem de teste do app para outro número | Entrega OK (confirmações no app) |
| 3 | No **celular**: Desconectar o dispositivo vinculado (Configurações → Aparelhos conectados → sair) | — |
| 4 | Aguardar ~30s no app (o bridge tenta reconectar) | No log aparecem `account.session_invalid` e `account.recovery.new_qr` |
| 5 | Observar a tela WhatsApp no app | **Novo QR Code aparece automaticamente** (sem reiniciar o app) |
| 6 | Parear o novo QR com o celular | Sessão reestabelecida; envio de teste funciona novamente |

**Falha esperada se:** serviço desligado (`waEnabled: false` no
`settings.json` — log mostra `wa.bridge.skipped` e a tela fica sem QR) —
isso valida também o item **D-5** da Onda 3.

---

## Checklist final

- [ ] V.1 completa (6/6)
- [ ] V.2 completa (6/6)
- [ ] `main.log` sem `error` durante os dois roteiros
