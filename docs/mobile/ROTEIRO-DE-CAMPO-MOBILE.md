# Roteiro de campo — app do entregador (pendente)

> **Status: PENDENTE — nenhum teste de campo completo foi executado nesta
> execução (30/10/2026).** O que foi executado de verdade está registrado ao
> final deste documento.

Este roteiro é a versão **reduzida e executável em campo** do roteiro oficial
[`MOBILE-QA-22.md`](./MOBILE-QA-22.md). Ele é o roteiro que precisa rodar com
o aparelho conectado ao laboratório USB para considerar o app validado.

## Pré-condições

| Item | Valor desta execução |
| --- | --- |
| Backend de lab | `http://127.0.0.1:8010` (ver `scripts/mobile-lab/`) |
| Túnel USB | `adb reverse tcp:8010 tcp:8010` (verificado: `UsbFfs tcp:8010 tcp:8010`) |
| Credencial | `%LOCALAPPDATA%\Temp\opencode\gasflow-lab\driver-credentials.txt` |
| Entregas | `LAB-001..005` no tenant `gasflow_lab` |

## Roteiro

| # | Etapa | Ação esperada | Status |
| --- | --- | --- | --- |
| 1 | Instalação/atualização do APK | Atualiza sem perder dados (mesma assinatura) | **OK em 30/10/2026** (v1.2.0 → v1.2.1, `firstInstallTime` preservado) |
| 2 | Abertura do app | Splash e tela de login sem crash | **OK em 30/10/2026** (app vivo em `adb`, buffer de crash vazio) |
| 3 | Configuração da URL (`127.0.0.1:8010`) e login | Entra com `motorista-lab-001` | **PENDENTE** |
| 4 | Rota do dia | Mostra `LAB-001..005` com estados do roteiro | **PENDENTE** |
| 5 | Detalhe da entrega | Cliente, endereço e produto por pedido | **PENDENTE** |
| 6 | Ação offline (fila) | Sem rede: `Iniciar entrega` fica na fila e sincroniza ao religar | **PENDENTE** |
| 7 | Reconexão | Fila esvazia sozinha; servidor aceita **uma** vez | **PENDENTE** |
| 8 | Logout → entra com outro motorista | Entregas do motorista anterior **não** aparecem | **PENDENTE** |
| 9 | Consentimento LGPD | Aceitar/rejeitar; rejeitar não quebra o login | **PENDENTE** |
| 10 | Navegação | Voltar não reseta rota/estoque; troca de aba preserva estado | **PENDENTE** |
| 11 | Permissões | Localização em primeiro plano negada não derruba o app | **PENDENTE** |
| 12 | Desinstalar/baixar app | Remove token e fila do dispositivo | **PENDENTE** (exige apagar o app no aparelho) |

## O que foi executado de verdade (30/10/2026)

Executado no aparelho físico **Samsung SM-G973F (Galaxy S10), Android 12,
arm64-v8a**, serial `RX8M90CBTXK`, com o APK release desta execução:

1. Backup do APK instalado (`1.2.0`, versionCode 3) para fora do repositório.
2. Atualização para `1.2.1` (versionCode 4) via `adb install -r` → `Success`,
   `firstInstallTime` preservado (dados do app intactos).
3. Abertura por `adb shell am start`: processo do app permanece vivo
   (`pidof` retorna PID estável) e `logcat -b crash` vem **vazio**.

**Bloqueio registrado:** antes da correção do splash, o app morria no
lançamento com
`Resources$NotFoundException: Drawable com.gasflowdriver:drawable/splash_screen`
(veja o aviso em [`MOBILE-DEPLOY.md`](./MOBILE-DEPLOY.md)). Corrigido e
revalidado.

**Pendências para executar o restante do roteiro:**

- **Login (etapas 3+)** depende do backend de laboratório rodando **e** de uma
  credencial que o app consiga usar — ver o aviso de assinatura em
  [`MOBILE-DEPLOY.md`](./MOBILE-DEPLOY.md) antes de tentar.
- Localização em primeiro plano depende de usuário conceder a permissão no
  aparelho (não automatizável sem tocar no dispositivo).
- O `MOBILE-QA-22.md` continua sendo o roteiro completo (84 verificações) e é
  o referencial para o aceite de release. ⚠️ **Aviso:** esse arquivo (não
  versionado) foi apagado do disco por um processo externo em 30/10/2026 e não
  foi recuperado — ver aviso 7 em
  [`MOBILE-DEPLOY.md`](./MOBILE-DEPLOY.md) e o relatório da execução.
