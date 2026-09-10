# Achados por área — Processo, CI/CD e repositório

## P-1 · 🔴 36 arquivos de trabalho não commitados

**Severidade:** 🔴 P0 · **Evidência:** `git status --porcelain | wc -l` → 36 (28 M + 8 ??), incluindo: correção de segurança (`python-multipart`), migration de schema, auto-recovery do WhatsApp, auto-update, auditorias e documentação.

**Impacto:** uma semana de correções (incluindo segurança e o fix do app instalado) existe **apenas neste disco**. Qualquer evento perde o trabalho; e o próximo `git push` de outra máquina não levará nada disso.

**Ação:** commitar em blocos lógicos (segurança/limpeza; diagnóstico; desktop/auto-update; docs/auditoria) e fazer push.

## P-2 · 🔴 `desktop/dist/` fora do versionamento

**Severidade:** 🔴 P0 (para CI de release) · **Evidência:** `git ls-files desktop/dist | wc -l` → 0; `.gitignore` linha `dist/` global.

**Impacto:** o workflow de release no GitHub Actions faria `npm ci && npm run build` — que compila **apenas o placeholder** e empacotaria um app sem main process. O instalador real só existe neste disco.

**Ação:** exception no `.gitignore` (`!desktop/dist/` — já aplicada nesta auditoria, validar no commit) e versionar os 12 módulos + preload. Médio prazo, D-1 elimina a necessidade.

## P-3 · 🟠 Workflow de release inexistente; permissões do repo

**Severidade:** 🟠 P1 · **Evidência:** `ls .github/workflows` → build-push.yml (Docker, `contents: read`), ci.yml. Não há release.yml (build Windows + publicar GitHub Releases).

**Impacto:** hoje o instalador é gerado manualmente; auto-update sem CI de release = atualizações só deste PC.

**Ação:** criar `release.yml` (on: push tags v*) com `permissions: contents: write`; no GitHub, Settings → Actions → Workflow permissions → "Read and write permissions".

## P-4 · 🟡 Sem tag estável; semestrado de rc

**Evidência:** `git tag` → v1.0.0-rc.1…rc.4 apenas. package.json desktop = 1.1.0.

**Ação:** definir a tag estável v1.1.0/v1.1.1 no primeiro release de teste do auto-update.

## P-5 · 🟢 Higiene positiva

Sem segredos commitados (varredura de padrões de token), `.env` fora do índice, sem lixo rastreado (db/log/exe/pyc), sem arquivos >1MB, `desktop/release/` e `node_modules/` ignorados, CHANGELOG e docs de diagnóstico/auditoria atualizados. CI cobre backend (ruff+pytest), whatsapp, agent e frontend.
