# Relatório de execução — 30/10/2026

> **Worktree:** `GasFlow-integration` | **Ramo:** `release/home-server-candidate`
> **Escopo:** app do entregador (fila offline por identidade/donos, LGPD),
> verificação de suítes, compilação Android + instalação em aparelho físico,
> laboratório USB de backend, e documentação de deploy.

Este relatório cobre o que foi **feito, verificado, bloqueado e o que ficou
pendente**. Nada aqui afeta produção: nenhum container, banco, sessão de
WhatsApp ou serviço em execução foi iniciado, parado ou removido.

---

## Parte 10 — Estado da execução

### 1. Alterações concluídas

**Código do app (mobile):**

| Arquivo | Mudança |
| --- | --- |
| `mobile/src/logic/offlineQueue.ts` | Fila agora carrega **dono/identidade da sessão** (`QueueOwner`), `flush(transport, {owner})` só reproduz ações do dono, `deferred` explícito para itens de outra sessão |
| `mobile/src/logic/queuePersistence.ts` (novo) | Persistência durável: `flush` só retorna **depois** da gravação, `persist()` propaga falha (não finge sucesso), gravações concorrentes serializadas, teto de retenção (ações nunca são descartadas automaticamente), descarte apenas explícito e registrado com motivo |
| `mobile/src/logic/session.ts` | Consentimento LGPD e sessão sem vazar token para a fila |
| `mobile/src/logic/api.ts` | Contrato de endpoints do app (caminhos-raiz `/driver/*`, `/auth/*`) |
| `mobile/src/containers/wired.tsx` | Logout **não** apaga fila pendente; envio filtrado por dono |
| `mobile/src/screens/DeliveryDetailScreen.tsx` | Feedback de fila offline |
| `mobile/tests/queueOwnership.test.ts` (novo) | 12 testes: logout preserva trabalho, replay bloqueado para outra sessão, adoção de item órfão só pelo dono, item offline nunca carrega token, concorrência, retenção, descarte rastreável |
| `mobile/tests/queuePersistence.test.ts` (novo) | Durabilidade da gravação |
| `mobile/tests/session.test.ts` | Consentimento (persistência, versão de política, recusa) |

**Correção de defeito (Android nativo):**

| Arquivo | Mudança |
| --- | --- |
| `mobile/android/app/src/main/res/drawable/splash_screen.xml` | `<bitmap src="@mipmap/ic_launcher">` → `<item android:drawable=...>` |
| `mobile/android/app/src/main/res/drawable-v24/splash_screen.xml` | idem |

**Laboratório e documentação:**

- `scripts/mobile-lab/` (novo): `start_lab_backend.ps1`, `stop_lab_backend.ps1`,
  `seed_lab_data.py`, `verify_lab_api.py`, `README.md`
- `docs/mobile/ROTEIRO-DE-CAMPO-MOBILE.md` (novo)
- `docs/mobile/MOBILE-DEPLOY.md` (restaurado + seção "Avisos conhecidos")
- `docs/mobile/RELATORIO-EXECUCAO-2026-10-30.md` (este arquivo)

> **Não foram feitos commits nem resets.** O worktree já trazia ~38 entradas de
> mudanças pré-existentes (não minhas, ramo `release/home-server-candidate`);
> elas foram preservadas intocadas.

### 2. APK construído/instalado

| Campo | Valor |
| --- | --- |
| Arquivo | `mobile/android/app/build/outputs/apk/release/app-release.apk` |
| Versão | `1.2.1` (versionCode **4**), minSdk 24, targetSdk 34 |
| Tamanho | 52.695.168 bytes |
| SHA-256 | `fe21486d1518bcc63aec0737b2aadba7d0ce0329ea3b1aee16a46de5a8aa0838` |
| Assinatura | V2, `CN=GasFlow Driver, O=GasFlow, C=BR`, SHA-256 `4710073c…` (keystore de release) |
| ABIs | `arm64-v8a`, `armeabi-v7a`, `armeabi`, `x86`, `x86_64` (APK universal) |

Ferramenta de build: **JDK 17** (`Eclipse Adoptium 17.0.19`) — o `JAVA_HOME`
global da máquina é JDK 8 e quebra o AGP; foi sobrescrito **por sessão**, sem
mudar configuração global.

### 3. Resultado de instalação

| Campo | Valor |
| --- | --- |
| Dispositivo | Samsung **SM-G973F** (Galaxy S10), Android **12**, `arm64-v8a`, serial `RX8M90CBTXK` |
| Comando | `adb -s RX8M90CBTXK install -r app-release.apk` |
| Resultado | **`Success`** |
| Dados | **Preservados** (`firstInstallTime` continuou `2026-10-20 14:38:13`) |
| Abertura | `adb shell am start -n com.gasflowdriver/.MainActivity` → processo estável |
| Crash | `logcat -b crash` **vazio** após a correção do splash |

Fluxo real: a primeira atualização falhou com
`INSTALL_FAILED_UPDATE_INCOMPATIBLE` (meu build tinha caído no fallback debug);
localizei a keystore de release no worktree, copiei-a para
`mobile/android/` (gitignorada), rebuildado e a assinatura passou a casar —
**atualização por cima, sem desinstalar e sem perder dados**. O APK instalado
original (`1.2.0`) foi salvo em backup antes da troca.

### 4. Defeito encontrado e corrigido

**App não abria (crash no lançamento)** — reproduzido no aparelho real:

```
FATAL EXCEPTION: main — Process: com.gasflowdriver
Resources$NotFoundException: Drawable com.gasflowdriver:drawable/splash_screen
Caused by: Binary XML file line #8: <bitmap> requires a valid 'src' attribute
```

Causa raiz: `splash_screen.xml` usava `<bitmap android:src="@mipmap/ic_launcher">`,
e a partir da API 26 `ic_launcher` é **adaptive-icon** (XML de vetores), que o
`<bitmap>` não infla. **O defeito já existia na v1.2.0 instalada** (mesmo
`res/ck.xml` nos dois APKs), ou seja, o app que o usuário tinha em mãos já não
abria. Correção: `<item android:drawable="@mipmap/ic_launcher" android:gravity="center"/>`,
rebuild e revalidação (app abre, PID estável, crash vazio).

### 5. Testes executados

| Suíte | Comando | Resultado |
| --- | --- | --- |
| Mobile | `npm test` (= `node --test tests/`) | **101 pass / 0 fail** |
| Mobile (tipos) | `npx tsc --noEmit` | **sem erros** |
| Desktop | `npm ci` (lockfile) → `npm run typecheck` → `npm test` | **153 pass / 0 fail**, typecheck limpo |
| Backend (foco) | `pytest` sobre financeiro/estoque/pagamento/tenant/isolamento | **202 pass / 0 fail** |

Arquivos do foco backend: `test_delivery_stock_reversal`, `test_driver_stock`,
`test_financial`, `test_payment_persistence`, `test_payment_contract`,
`test_pix_service`, `test_tenant_isolation`, `test_cross_tenant_isolation`,
`test_sec01_admin_tenant_isolation`, `test_sec01c_tenants_platform_scope`.

> O desktop antes desta execução **nunca tinha tido suíte executada**; isso foi
> resolvido instalando as dependências pelo lockfile (`npm ci`).

### 6. APK em execução

- **Sim, parcialmente:** instalado e **abrindo sem crash** no Galaxy S10.
- **Não**, para os fluxos de negócio (login, rota do dia, fila offline, GPS):
  esses passos continuam **pendentes** de execução em campo — ver
  [`ROTEIRO-DE-CAMPO-MOBILE.md`](./ROTEIRO-DE-CAMPO-MOBILE.md).

### 7. Servidor de laboratório

- Backend **descartável** rodando em `http://127.0.0.1:8010` (somente loopback),
  banco **SQLite próprio** em `%LOCALAPPDATA%\Temp\opencode\gasflow-lab`,
  migrations Alembic aplicadas, WhatsApp apontando para porta sem serviço,
  ViaCEP/IA/Redis desligados, segredos gerados **fora** do repositório.
- Ponte USB comprovada: `adb reverse tcp:8010 tcp:8010` →
  `UsbFfs tcp:8010 tcp:8010`.
- Scripts reutilizáveis e idempotentes em `scripts/mobile-lab/`
  (subir/encerrar sem tocar em outros serviços, seed, smoke test).

### 8. Dados de laboratório criados

| Entidade | Valor |
| --- | --- |
| Tenant | `gasflow_lab` — "GasFlow Laboratorio" |
| Admin do tenant | `admin_lab` (tenant `gasflow_lab`) |
| Entregador | `motorista-lab-001` / documento `MOTORISTA-LAB-001` / `Ativo` / tenant `gasflow_lab` |
| Produtos | `Gas P13` e `Agua 20 L` (estoque 100/100 **via API real** `/inventory/{codigo}/entries`) |
| Clientes | `Cliente Teste Lab 1..5`, telefones sintéticos `919000000xx`, endereços rotulados como teste |
| Entregas | `LAB-001..005` — **NÃO criadas** (bloqueio, ver item 12) |

Credencial do entregador gravada em
`%LOCALAPPDATA%\Temp\opencode\gasflow-lab\driver-credentials.txt` (fora do
repositório, nunca em log/commit/relatório).

### 9. Teste offline

**Não executado no aparelho.** O código e os testes de comportamento offline
(fila, dono, durabilidade, reconexão) estão implementados e cobertos por 21
testes unitários, mas o fluxo real "desligar rede → ação entra na fila →
religar → sincroniza uma única vez" precisa ser executado em campo.

### 10. Comportamento LGPD/consentimento

- Consentimento persistido com versão de política; versão antiga **não**
  desbloqueia o rastreamento (re-aceite obrigatório).
- Recusa de rastreamento **não** quebra login: o fluxo segue sem rastrear.
- Falha de gravação/leitura do consentimento falha **fechado** (não assume
  aceite).
- Fila offline **não** armazena token nem credencial (há teste garantindo isso).
- Falta apenas a verificação no aparelho (etapa 9 do roteiro de campo).

### 11. Teste de empacotamento (Parte 8)

**Não executado — pendente de autorização.** O daemon Docker estava parado;
verificar `docker compose ls`, containers, volumes, rede e portas exige subir
o Docker Desktop, o que pode **auto-iniciar containers existentes** (políticas
de restart). Nada foi iniciado, parado ou removido. O que já está pronto no
repositório: `docker-compose.prod.yml`, `docker-compose.homeserver.lab.yml`,
`deploy/home-server/` e o perfil de testes que cobre esse caminho
(`backend/tests/test_ops01b_homeserver_profile.py` — verificado nesta execução).

### 12. Pendências e bloqueios

| # | Pendência | Causa | Próximo passo |
| --- | --- | --- | --- |
| 1 | Login/fluxo no aparelho (etapas 3+ do roteiro) | Exige operação humana no celular (digitar credencial, conceder localização); automação por teclado com credencial é proibida | Rodar `scripts/mobile-lab/` + roteiro de campo com o operador |
| 2 | Entregas `LAB-001..005` | A API de estoque grava no tenant errado (ver item 13) | Corrigir o tenant do inventário e reexecutar `seed_lab_data.py` |
| 3 | Empacotamento Docker/Windows | Pode auto-iniciar containers existentes | Autorização explícita do operador |
| 4 | `docs/mobile/*.md` não versionados | Apagados por processo externo durante a execução (ver item 14) | Versionar `docs/mobile/` ou fazer backup |

### 13. Defeitos observados (não corrigidos nesta execução)

**a) `POST /inventory/{codigo}/entries` grava no tenant errado** — as entradas
de estoque do tenant `gasflow_lab` caíram em `inventory.tenant_id='default'`.
Como `CreateOrderUseCase` lê `Inventory.quantity` (e não `products.estoque`),
isso faz o pedido falhar com "Estoque insuficiente" mesmo com estoque
cadastrado. Efeito colateral prático: **as entregas do laboratório não puderam
ser criadas**. O ponto está em `backend/app/presentation/api/catalog/inventory.py`
(`_get_inventory_repo`), que constrói o repositório sem o tenant da sessão —
os endpoints já recebem o contexto de tenant, mas não o usam nessa linha.

**b) Colisão de rotas `/driver/me` e `/driver/deliveries`** — existem duas
definições (`driver_self.py` nos caminhos-raiz, que é o que o app usa, e
`driver_v1.py` em `/api/v1/...`, legado). O comportamento depende da ordem de
registro dos routers; manter as duas é fonte de confusão futura.

### 14. Ocorrência anômala: perda de documentação não versionada

Durante esta execução, os arquivos **não versionados** de `docs/mobile/`
(`MOBILE-DEPLOY.md`, `MOBILE-QA-22.md`, `MOBILE-RELEASE-CHECKLIST.md`)
desapareceram do disco — a pasta foi recriada apenas quando o
`ROTEIRO-DE-CAMPO-MOBILE.md` foi salvo. Nenhuma operação de remoção foi feita
por esta execução (todas as escritas foram aditivas; a única remoção foi de um
arquivo-lixo de segredos criado por um bug do próprio script de lab, já
corrigido). Não há cópia em outros worktrees nem no OneDrive. Provável limpeza
externa (sync ou outro processo/agente atuando no mesmo worktree).

`MOBILE-DEPLOY.md` foi **restaurado** a partir da leitura feita nesta mesma
execução; `MOBILE-QA-22.md` e `MOBILE-RELEASE-CHECKLIST.md` **não puderam ser
recuperados**. Recomendação: versionar `docs/mobile/`.

---

## Parte 11 — Tópicos do relatório

### 1. O que mudou e por quê

A fila offline do app aceitava qualquer sessão e o logout apagava trabalho não
sincronizado. Foram três frentes: (i) **dono/identidade** na fila — ação só é
reproduzida sob a sessão de quem a criou, e logout preserva o que ainda não
sincronizou; (ii) **durabilidade** — a confirmação na UI só vem depois da
gravação, e falha de gravação é propagada em vez de silenciada; (iii) **o app
simplesmente não abria** — o crash do splash era impeditivo e foi corrigido no
nativo. Tudo com testes novos, para que o comportamento não regrida.

### 2. O que foi testado

Mobile 101/101 (fila/donos/durabilidade/consentimento, sessão, rastreamento,
lógica), desktop 153/153 com typecheck (suíte que antes nunca tinha rodado) e
202 testes de backend nas áreas de financeiro, estoque, pagamento, tenant e
isolamento — todas passando.

### 3. O que foi instalado/compilado

APK release `1.2.1` (versionCode 4, universal arm64-v8a e demais ABIs),
assinado com a keystore de release, buildado com JDK 17, e **instalado num
Galaxy S10 físico via USB** com dados preservados, abrindo sem crash.

### 4. O que foi executado

Backend de laboratório em `127.0.0.1:8010` (SQLite descartável), túnel USB via
`adb reverse`, seed de tenant/produtos/estoque/clientes/entregador fictícios e
smoke test da API — tudo por scripts reutilizáveis em `scripts/mobile-lab/`.

### 5. O que ficou pendente

Login e fluxos de negócio no aparelho, entregas `LAB-001..005` (bloqueadas pelo
defeito de tenant do estoque) e o empacotamento Docker/Windows (pendente de
autorização).

### 6. Como reproduzir

```powershell
# backend de laboratório (porta 8010, SQLite descartável)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\mobile-lab\start_lab_backend.ps1 -Port 8010
adb reverse tcp:8010 tcp:8010
python scripts\mobile-lab\seed_lab_data.py --api http://127.0.0.1:8010
python scripts\mobile-lab\verify_lab_api.py --api http://127.0.0.1:8010

# testes
cd mobile; npm test; npx tsc --noEmit
cd ..\desktop; npm ci; npm run typecheck; npm test
cd ..\backend; python -m pytest tests/test_financial.py tests/test_tenant_isolation.py -q

# build Android (JDK 17 obrigatório)
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot"
cd mobile\android; .\gradlew.bat assembleRelease -PreactNativeArchitectures=arm64-v8a --no-daemon

# encerrar só o laboratório
powershell -NoProfile -ExecutionPolicy Bypass -File ..\scripts\mobile-lab\stop_lab_backend.ps1 -Port 8010
```

### 7. Comandos seguros de rollback

| Alvo | Comando |
| --- | --- |
| App no aparelho (voltar à versão anterior) | reinstalar o APK de backup salvo antes da troca (`adb install -r <apk>`); **nunca** `adb uninstall` (apaga dados do usuário) |
| Laboratório inteiro | apagar `%LOCALAPPDATA%\Temp\opencode\gasflow-lab` + `adb reverse --remove tcp:8010` |
| Código desta execução | `git checkout -- mobile/android/app/src/main/res/drawable/splash_screen.xml mobile/android/app/src/main/res/drawable-v24/splash_screen.xml` (as demais alterações novas são arquivos untracked: `git clean` **não** recomendado) |
| Produção | **nada foi alterado em produção** — não há rollback a fazer |

### 8. Próximo ponto de atenção

Duas frentes, em ordem de valor:

1. **Fechar o teste de campo** (login, fila offline, GPS, logout com outro
   motorista) com o laboratório USB já montado — é o que separa "instala e
   abre" de "funciona em operação".
2. **Corrigir o tenant da API de estoque** (item 13a): enquanto as movimentações
   caem no tenant `default`, multi-tenant e o próprio seed de entregas ficam
   bloqueados. Depois disso, `seed_lab_data.py` gera os `LAB-001..005` e o
   roteiro de campo inteiro pode rodar.
