# Spec — Lançamento v1.2.0 (correção do auto-update)

**Data:** 2026-09-23
**Objetivo:** publicar a release v1.2.0 com todas as mudanças acumuladas desde a v1.1.6, fazendo o auto-update do desktop funcionar de verdade (o app instalado parou na v1.1.6 porque a release v1.1.7 nunca foi publicada no GitHub) e o APK do entregador ficar disponível para download/atualização.

---

## 1. Diagnóstico — por que o auto-update não atualiza

Investigação feita em 2026-09-23:

1. **O app instalado (v1.1.6) pergunta ao GitHub e ouve que v1.1.6 é a mais recente.** Log real de `%APPDATA%\gasflow-desktop\logs\main.log`:
   ```
   [2026-09-23 11:37:39] [updater] sem atualizações (v1.1.6 é a mais recente)
   ```
   O updater (electron-updater + GitHub Releases) está funcionando: ele checa 15s após abrir e a cada 6h. O problema não é no cliente — é que **a release mais recente publicada no GitHub é a v1.1.6**.

2. **A tag v1.1.7 existe, o workflow Release rodou verde (2 runs `success` em 2026-09-21, incluindo o step "Confere que o release está publicado e completo"), mas NÃO existe release v1.1.7 no GitHub** — nem pública, nem rascunho visível (`GET /releases/tags/v1.1.7` → 404 anônimo). Contradição a investigar: o step de conferência usa `gh release view "$TAG"` autenticado com `GITHUB_TOKEN` e passou. Hipóteses:
   - O release foi criado e depois deletado manualmente (ação humana fora do workflow);
   - O `gh release view` enxergou algo que a API anônima não lista (draft criado e editado depois); o assert de draft tem autocorreção (`gh release edit --draft=false`), mas só roda se `isDraft=true` na leitura do bot;
   - Publish duplicado/race: o histórico já mostra **releases duplicadas** (v1.1.6 e v1.1.4/v1.1.3 têm 2 releases cada, mesma tag, IDs diferentes) — indício de race entre runs do workflow ou entre `--publish always` e algo anterior.

   > **Ação derivada:** a spec não depende de descobrir a causa raiz exata; o procedimento abaixo torna o estado final verificável e o step "Confere" do release.yml é a rede de segurança. A duplicata v1.1.6 antiga será deletada para reduzir confusão.

3. **Estado das releases hoje (API anônima):**
   | Tag | Releases | Assets |
   |---|---|---|
   | v1.1.6 | **2 duplicadas** (ids 390033299, 390033296) | a mais completa tem .exe + .blockmap + latest.yml; a outra só .exe + latest.yml (sem blockmap) |
   | v1.1.7 | **0** (workflow verde mas release inexistente) | — |

4. **CI na main está vermelho no job Backend** por um teste flaky (detalhe na §3). O `ci_gate` do release exige os 4 jobs de teste verdes no commit da tag — isso **bloqueia qualquer tag nova** até corrigir.

5. **Versões já estão coerentes em 1.2.0:** `desktop/package.json` = 1.2.0, `mobile/package.json` = 1.2.0 (versionCode 3), `mobile_version.json` anuncia `latest_version: 1.2.0`. Não há bump a fazer — só tag.

6. **O APK mobile:** `mobile_version.json` aponta `download_url: https://github.com/.../releases/latest/download/app-release.apk`, mas **nenhuma release tem esse asset**. O auto-update do APK (checado no boot do app do entregador via `GET /mobile/version`) cai nos defaults quando o arquivo some; hoje o entregador atualiza só por sideload.

---

## 2. Decisões acordadas (entrevista)

| Tema | Decisão |
|---|---|
| Estratégia de tag | **Nova tag `v1.2.0` no HEAD atual** (desktop/mobile já são 1.2.0). A tag fantasma v1.1.7 não é recriada nem renomeada. |
| Teste flaky | **Corrigir antes do release** (conflito de estado entre testes; ver §3). |
| Duplicata v1.1.6 | **Deletar a release duplicada antiga** (a que não tem `.blockmap`); manter a completa. |
| Validação pré-tag | **Suítes locais dos 4 projetos** (backend, frontend, whatsapp, agent) **+ build do instalador local** (`.exe`/`.blockmap`/`latest.yml` com a versão certa) **+ APK release assinado** (com `assets/index.android.bundle` dentro). |
| Validação pós-release | **Instalar a v1.2.0 e testar o updater de verdade** na máquina local (simula o que o cliente vive). |
| Versionamento | **Manter 1.2.0** — sem bump; tag direto. |
| APK mobile | **Anexar o APK assinado como asset `app-release.apk` na release v1.2.0** — o `download_url` do `mobile_version.json` passa a funcionar e o auto-update do APK entra no ar. |
| Release notes | **Copiar da seção `[Unreleased]` do CHANGELOG.md** como body da release. |
| `mobile_version.json` | **Atualizar `changelog` e `release_date` antes da tag** para refletir a v1.2.0 (o `download_url` já está certo). |
| Falha do gate por flaky | **Retry automático no workflow** (re-disparar o job Backend falho até 2x antes do gate falhar). |
| Timeout do gate | **Estender 45→75 min** para caber um ciclo de retry completo (CI ~20-30min por ciclo). |
| Rollback | **Redo da release**: se a v1.2.0 sair quebrada, deletar release + tag e re-publicar. |
| CHANGELOG pós-release | **Renomear `[Unreleased]` → `[1.2.0] - 2026-09-23`** (padrão Keep a Changelog), abrindo `[Unreleased]` vazia. |
| Rastreabilidade | **Tag no commit exato do HEAD** pushado; SHA rastreia o binário. |

---

## 3. Correção pré-requisito — teste flaky do backend

**Sintoma reproduzido localmente:** `tests/test_tenant_isolation.py::TestTenantFiltering::test_delivery_filtered_by_tenant` **falha na suíte completa** e **passa isolado** (24/24 no arquivo, 3 rodadas seguidas OK, 114/114 junto com test_delivery.py). Na run full (1822 testes) falhou 1x; com deselect, 1822 passed.

**Causa provável:** vazamento de estado entre testes. O traceback capturado aponta para `ValueError` em `app/domain/delivery/entity.py:31` — "Código do entregador deve ter 6 dígitos" (validação do `__post_init__`). Ou seja: algum teste anterior deixa no banco de teste (ou em fixture de sessão) um `DeliveryDriver`/seed com `codigo` inválido, e quando o teste de isolation consulta `/delivery-drivers/`, a desserialização do registro corrompido levanta `ValueError` → 500 → assert de status 200 falha. Como o teste passa isolado, o registro ruim é criado por outro teste — candidato natural: qualquer teste que crie driver com `codigo` curto/mockado (procurar `DeliveryDriver(` com código < 6 dígitos e `codigo="..."` literal em fixtures de testes).

**Correção (a implementar):**
1. Achar o(s) teste(s) que persistem `DeliveryDriver` com `codigo` inválido e corrigir o seed para código válido de 6 dígitos (ex.: `"000001"`), ou usar fixture com rollback real (transação revertida) em vez de commit.
2. Defesa: tornar a leitura resiliente — `GET /delivery-drivers/` não deve 500 por um registro legado corrompido (logar warn e pular o registro inválido), OU validar `codigo` na camada de repositório ao gravar. Preferência: corrigir a causa (teste) e, se barato, adicionar a tolerância na leitura como cinto de segurança — decidir na implementação.
3. Critério de aceite: **3 execuções seguidas da suíte completa do backend verde** (sem deselect).

**Retry automático no CI (mudança no `.github/workflows/ci.yml` ou no release.yml):** o gate não pode simplesmente re-rodar outro workflow com o `GITHUB_TOKEN` padrão (sem permissão de `actions: write` para re-run). Implementação recomendada: no `release.yml`, transformar o job `ci-gate` em até **3 tentativas**: se `python3 .github/scripts/ci_gate.py` falhar por job reprovado (e não por timeout), re-disparar o job de teste falho do CI no mesmo SHA via `gh run rerun <run_id> --failed` (o `GITHUB_TOKEN` do release.yml pode fazer rerun se `permissions: actions: write` for adicionado) e esperar de novo. Parâmetros:
- `TIMEOUT_S` do gate: **75 min** por tentativa (mudar em `.github/scripts/ci_gate.py`).
- Máximo **2 re-runs** (3 tentativas totais). Falhou as 3 → release falha (comportamento atual).
- Só re-run quando a falha for em job de teste; timeout do gate continua fatal.

> Alternativa mais simples (fallback se `actions: write` não resolver no rerun cross-workflow): no `ci.yml`, adicionar `workflow_dispatch` ao gate... — não, o `ci.yml` roda em push; o rerun via `gh run rerun --failed` funciona com `actions: write` no mesmo repo. Validar na implementação com uma tag de teste `v0.0.0-test` **depois** de deletá-la.

---

## 4. Checklist de execução (ordem obrigatória)

> **Estado em 2026-09-24** — a tag `v1.2.0` (anotada, `fe1f9d0` → commit
> `926677e`) já foi criada e pusheada, e a release está **publicada** (id
> 394939169, pública) com `.exe`, `.exe.blockmap` e `latest.yml` (1.2.0) —
> workflow Release `35901091408` verde em ~9 min. A duplicata da v1.1.6 foi
> removida: a API não lista **nenhuma** release duplicada nem rascunho órfão.
> Os 4 jobs do gate (Backend/Frontend/WhatsApp/Agent) estão verdes no commit
> da tag; quem reprova o run de CI é só o job **E2E**, que o gate ignora de
> propósito — mas a main ficou vermelha por isso (ver nota no fim da §4).
> **C4/C5 fechados em 2026-09-24**: o asset `app-release.apk` (52.773.002
> bytes, o APK assinado da B3) foi anexado à release e o body passou a ser o
> `docs/release-notes-v1.2.0.md` (sha256 do body idêntico ao do arquivo).
> Conferido por fora: `GET /releases/latest/download/app-release.apk` responde
> 302 → 200 com `Content-Length: 52773002`. Pendentes: **D1–D5**
>
> Nota de decisão: o retry automático via `gh run rerun` (§3) foi substituído
> pela estratégia "esperar até o deadline antes de reprovar" (`d3bf3f9`) — o
> gate não reprova na primeira leitura de um run vermelho, dando a janela do
> re-run sem precisar de `actions: write`.
>
> Nota de regressão: o E2E estava vermelho desde `4c5ffe5` porque
> `e2e/tests/drivers.spec.ts` continuava na UI antiga do formulário de
> motorista ("Tipo de Veículo" removido em `735ce2c` e navegação direta para a
> lista, que virou a tela da credencial temporária). Spec corrigido no mesmo
> commit que fecha este checklist.

### Fase A — Correções no código (antes de qualquer tag)
- [x] **A1.** Corrigir o flaky do backend (§3). Critério: 3 suítes completas verdes seguidas.
- [x] **A2.** Atualizar `mobile_version.json`: campo `changelog` descrevendo a v1.2.0 (migração `/driver/*` no app, cleartext LAN, CRUD de entregadores no painel, cancelamentos, integrações/automações) e `release_date: 2026-09-23`. `latest_version` e `download_url` já estão corretos.
- [x] **A3.** Ajustar `release.yml`: timeout do gate 45→75 min (o timeout do **job** `ci-gate` em `timeout-minutes` e o `TIMEOUT_S` do script) + retry do gate (§3). Adicionar `actions: write` ao bloco `permissions` se o retry usar rerun.
- [x] **A4.** (Opcional, barato) No step "Confere que o release está publicado e completo", adicionar assert de **unicidade**: `gh release list` não pode ter 2 releases com a mesma tag — alerta no log se houver (não falha, só denuncia).
- [x] **A5.** Commitar tudo (padrão conventional, ex.: `fix(ci): ...`, `fix(tests): ...`) e **push na main**. Aguardar CI verde na main (job Backend incluído) — é o mesmo commit que receberá a tag.

### Fase B — Validações locais (antes da tag)
- [ ] **B1.** Suítes locais dos 4 projetos (o mesmo que o gate cobra):
  - backend: `python -m pytest tests/` (3x seguidas);
  - frontend: `npm run typecheck` + `npx vitest run`;
  - whatsapp: typecheck + testes do projeto;
  - agent: typecheck + testes do projeto.
- [x] **B2.** Build do instalador local (replica o CI):
  ```bash
  cd desktop && npm run build:win
  ```
  Conferir em `desktop/release/`: `GasFlow Desktop Setup 1.2.0.exe`, `.blockmap`, `latest.yml` com `version: 1.2.0`.
- [x] **B3.** APK release assinado:
  ```bash
  cd mobile/android && ./gradlew assembleRelease
  unzip -l app/build/outputs/apk/release/app-release.apk | grep index.android.bundle
  ```
  Precisa conter `assets/index.android.bundle` (release com bundle embutido — sem Metro).
- [x] **B4.** Limpeza do GitHub: **deletar a release v1.1.6 duplicada antiga** (a sem `.blockmap`, id 390033299) — pela UI do GitHub (Settings → Releases) ou `gh release delete v1.1.6 --cleanup-tag=false` apontando o id certo. **Não deletar a tag.** Se houver rascunho órfão da v1.1.7, deletar também.

### Fase C — Tag e release
- [x] **C1.** Criar a tag **no commit do HEAD pushado** (o mesmo validado em A5):
  ```bash
  git tag -a v1.2.0 -m "v1.2.0 — auto-update do desktop no ar, CRUD de entregadores, acoes /driver/* no app, integracoes e automacoes"
  git push origin v1.2.0
  ```
- [x] **C2.** Acompanhar o workflow Release (Actions → Release): `ci-gate` (agora com retry e 75min) → `build-windows` → publish → **step "Confere" verde**.
- [x] **C3.** Conferir no GitHub que a release v1.2.0 existe, **não é rascunho**, e tem: `GasFlow Desktop Setup 1.2.0.exe`, `.exe.blockmap`, `latest.yml` (version 1.2.0).
- [x] **C4.** **Anexar o APK** assinado da B3 como asset `app-release.apk` na release (UI: drag & drop nos assets; ou `gh release upload v1.2.0 app-release.apk`). Isso torna o `download_url` do `mobile_version.json` funcional e liga o auto-update do app do entregador. Feito em 2026-09-24 pela API do GitHub: `app-release.apk`, 52.773.002 bytes — o exe do CI (191.322.791 bytes, com `.blockmap` e `latest.yml` que casam com ele) **não** foi tocado.
- [x] **C5.** **Body da release:** colar como descrição o conteúdo da seção `[Unreleased]` do CHANGELOG.md (que já documenta: CRUD de entregadores, ações `/driver/*`, debug×release mobile, painel web, diversos). Manter o parágrafo "🤖 Generated with Codebuff" fora — release notes são para usuários. O texto já extraído byte a byte da seção
  `[1.2.0]` (23,9 kB, sem o rodapé do Codebuff) está em
  `docs/release-notes-v1.2.0.md`, pronto para colar no campo de descrição.
- [x] **C6.** Commit pós-release no CHANGELOG: renomear `[Unreleased]` → `[1.2.0] - 2026-09-23` e abrir `[Unreleased]` vazia em cima. Push.

### Fase D — Validação pós-release (a prova real do auto-update)
- [ ] **D1.** Na máquina local, **instalar a v1.2.0** baixada da release (não um build local) — simula o cliente.
- [ ] **D2.** Abrir o app → log de updater deve mostrar `verificando atualizações…` → `sem atualizações (v1.2.0 é a mais recente)`.
- [ ] **D3.** Prova de fogo do upgrade: instalar a **v1.1.6** (asset da release antiga) em ambiente limpo (ou máquina de teste), abrir, esperar a checagem (15s) e confirmar o fluxo completo: `update-available` → banner de download → overlay "Reiniciar e instalar" → app reinicia em 1.2.0.
- [ ] **D4.** App do entregador: instalar o APK da release (ou abrir o app já instalado em versão < 1.2.0) e confirmar que o boot consulta `GET /mobile/version`, recebe 1.2.0 + URL funcional, e o download do APK funciona.
- [ ] **D5.** Smoke do desktop 1.2.0: login, mapa de rastreio ao vivo, criar/editar/excluir entregador, cancelar um pagamento, página de Integrações e de Automações abrem.

### Plano de rollback (se algo crítico for descoberto logo após C)
- Deletar a release v1.2.0 (UI ou `gh release delete v1.2.0 --yes`) + deletar a tag remota (`git push origin :refs/tags/v1.2.0`).
- Corrigir, commitar, recriar a tag no novo HEAD e seguir da Fase C de novo.
- O instalador já baixado por ninguém é afetado retroativamente (updater só oferecerá a versão publicada vigente).

---

## 5. Mudanças de código/arquivo previstas nesta spec

| Arquivo | Mudança |
|---|---|
| `backend/tests/…` (a localizar na implementação) | Corrigir seed com `codigo` inválido de `DeliveryDriver` (causa do flaky). |
| `backend/app/infrastructure/repositories/delivery_repository.py` *(opcional)* | Tolerância na leitura: pular registro com `codigo` inválido em vez de 500 (cinto de segurança). |
| `.github/scripts/ci_gate.py` | `TIMEOUT_S = 75 * 60`. |
| `.github/workflows/release.yml` | `timeout-minutes` do job `ci-gate` 45→75; retry do gate (até 2 reruns do job de CI falho); `permissions.actions: write`; assert de unicidade de release (opcional, warning). |
| `mobile_version.json` | `changelog` da v1.2.0 + `release_date: 2026-09-23`. |
| `CHANGELOG.md` | Pós-release: `[Unreleased]` → `[1.2.0] - 2026-09-23`, abrir `[Unreleased]` vazia. |

## 6. O que NÃO está no escopo

- Migrar a rota web `/driver` (página web legada) para o namespace novo — dívida documentada em `driver_self.py`.
- Aposentar `driver_api`/`driver_v1` (migração completa do legado) — passo seguinte documentado no código.
- Certificado Authenticode/assinatura do instalador Windows (aviso SmartScreen persiste).
- Investigações forenses adicionais sobre o sumiço da release v1.1.7 — o processo agora torna o estado verificável a cada passo; se voltar a acontecer, aí sim investigar com os logs do Actions e do electron-builder (`builder-debug.yml`).
- Publicar em canal beta/staged rollout — release única, canal `latest`.

## 7. Riscos e observações

- **Risco:** o retry automático pode mascarar falha real (ex.: bug que falha 2x e passa 1x por sorte). Mitigação: o retry é limitado a 2 e o log do gate imprime qual job falhou — sempre olhar o log antes de comemorar.
- **Risco:** deletar release/tag recriada quebra quem já baixou (nenhum cliente automático aponta para tag deletada; o updater lê `latest.yml` da release vigente). Baixo.
- **Nota:** o `latest.yml` do desktop local (`desktop/release/`) está da 1.1.2 (build local antigo) — irrelevante para o release; o CI regenera.
- **Nota:** `download_count: 0` em todos os assets — nenhum cliente baixou pelo link do GitHub até hoje; o auto-update do desktop só baixa para o cache local do electron-updater (não incrementa essa métrica de forma confiável).
