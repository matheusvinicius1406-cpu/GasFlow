# 02 · Plano de Correção — P0 → P3

Ordem de execução recomendada. Cada fase é comitável e verificável isoladamente.

## Onda 1 — P0: salvar o trabalho e viabilizar CI de release (~1 h)

1. **B-1** · Limpar os 2 resíduos de lint (5 min)
   ```bash
   cd backend
   # gateway.py:134 — remover `start_time = ...` (métrica já não existe)
   # daily_report.py:73 — remover TA_RIGHT do import
   ruff check app --select F401,F841   # → All checks passed!
   ```
2. **P-2** · Validar exceção do `.gitignore` e versionar o dist (10 min)
   ```bash
   git check-ignore desktop/dist/main/index.js   # deve falhar (não ignorado)
   git add desktop/dist/
   ```
3. **P-1** · Commitar em blocos lógicos + push (30 min)
   ```bash
   git add backend/ whatsapp/ frontend/ requirements
   git commit -m "fix: schema migration, WA auto-recovery, IA graceful degradation, segurança"
   git add desktop/
   git commit -m "feat(desktop): auto-update (electron-updater) + preload/IPC conectados"
   git add docs/ .gitignore CHANGELOG.md
   git commit -m "docs: auditoria completa + diagnóstico + changelog"
   git push
   ```
4. **Critério de aceite:** `git status --porcelain` vazio; job `Backend (ruff + pytest)` verde no GitHub Actions.

## Onda 2 — P1: pipeline de release e validação do auto-update (~2 h)

5. **P-3** · Criar `.github/workflows/release.yml` (on: push tags `v*`), `permissions: contents: write`, steps: checkout → setup-node 20 → `npm ci` (desktop) → `npm run build:win -- --publish always` com `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` → upload de `release/*.exe` + `release/latest.yml` como artifact. *(Requer P-2: dist versionado.)*
6. **D-3** · Gerar build local completo e conferir `latest.yml`:
   ```bash
   cd desktop && npm run build:win
   ls release/latest.yml && cat release/latest.yml   # version deve bater com package.json
   ```
   Adicionar script `"build:win": "npm run build && npm run build --prefix ../agent && npm run build --prefix ../whatsapp && npm run build --prefix ../frontend && electron-builder --win"`.
7. **GitHub** (manual, uma vez): Settings → Actions → General → Workflow permissions → **Read and write permissions**.
8. **Primeiro release de teste:** `npm version patch` (1.1.0 → 1.1.1) → `git push --tags` → aguardar Actions → conferir em Releases que o `.exe` + `latest.yml` foram publicados.
9. **W-1** · E2E do WhatsApp com o app novo instalado: parear → desconectar a conta pelo celular → conferir no log que o serviço **limpa credenciais e gera QR novo** (em vez de morrer).
10. **Critério de aceite:** release v1.1.1 publicada pelo Actions; app v1.1.0 instalado detecta, baixa e instala ao clicar.

## Onda 3 — P2: higiene (~3 h)

11. **B-4** · `conftest.py`: fixture de engine apontando para sqlite temporário (padrão já usado em `test_schema_migration.py`).
12. **D-5** · `if (settings.waEnabled === false) skip ensureWaBridge().start()` (e expor o flag na UI de configurações).
13. **D-4** · Extrair `loadSettings/generateKey` de `config.js` para módulo puro e cobrir com testes node:test.
14. **DOC-1/DOC-2** · Banner "histórico" nos docs de fase com wwebjs; README do desktop ganha seção "Auto-update + Troubleshooting" (log `updater.*`, portas 8000/3101, QR, migration automática).
15. **E2E-1** · Garantir job Playwright no CI (login + aba Clientes + WhatsApp UI).

## Onda 4 — P3: dívida mapeada (sem prazo)

16. **D-1** · Reescrever fontes do main (`desktop/src/main/*.ts`) a partir do comportamento; trocar include do tsconfig; aposentar o placeholder. *Pré-requisito para qualquer evolução séria do Electron.*
17. **B-2** · mypy baseline congelado + gate em erros novos.
18. **B-3** · Renomear parâmetros de interface para `_nome` conforme tocado.
19. Refatorar as 19 funções C90>10 (começar por `import_service.test_connection`).
20. Triar os 25 `except: pass` adicionando `logger.debug/warning` contextual.

## Regras de execução

- Uma onda por vez; nunca misturar correção com feature nova.
- Cada onda termina com: testes verdes → commit → push.
- Rollback de release: nunca reusar tag; publicar v1.1.2 com o código anterior (`allowDowngrade: false` no updater).
