# Evidências — comandos e saídas

Rastreabilidade bruta da auditoria. Comandos executados em `GasFlow/` (repo git com remote `matheusvinicius1406-cpu/GasFlow`).

## 1. Estado do repositório

```
$ git status --porcelain | wc -l
36                                  # 28 modificados + 8 não rastreados — trabalho não commitado

$ git log --oneline -3
83b23ed fix(desktop): restaura build do main process ausente (tsconfig + placeholder)
608c7bf feat(dev): adiciona GASFLOW_BACKEND_URL ao template do start-dev.sh
fa28e28 feat(crm): integração contatos WhatsApp ↔ CRM — sync push, VCF, reativação e auth endurecida

$ git tag
v1.0.0-rc.1 … v1.0.0-rc.4           # nenhuma tag estável v1.x ainda
```

## 2. Segredos

```
$ git ls-files | xargs grep -lE "ghp_…|github_pat_|sk-…|AKIA…|wa-h5gwu"
(nenhuma ocorrência)                 # ✅ sem token commitado
$ ls -la .env backend/.env
ambos 197121B, gitignored            # ✅ fora do índice (não lidos nesta auditoria)
```

## 3. Desktop / auto-update

```
$ git ls-files desktop/dist | wc -l
0                                    # dist/ do desktop NÃO versionado (era ignorado)
$ cat desktop/src/ → apenas placeholder.ts (fontes do main ausentes)
$ ls desktop/tests/ → 0 arquivos (npm test roda 0 testes, exit 0)
$ ls desktop/release/*.yml → builder-debug.yml apenas (sem latest.yml — updater precisa)
$ grep electron-updater desktop/package.json → "electron-updater": "^6.8.9" (dependencies ✅)
$ grep -A6 publish desktop/electron-builder.yml → provider github/owner/repo/releaseType: release ✅
```

## 4. Qualidade estática (estado APÓS as correções desta semana)

```
$ ruff check app --select F401,F841 --output-format concise
app/application/whatsapp/gateway.py:134:9: F841 start_time assigned but never used
app/infrastructure/pdf/daily_report.py:73:52: F401 TA_RIGHT imported but unused
Found 2 errors.                      # 2 resíduos das edições desta semana

$ mypy app --explicit-package-bases → 528 erros / 52 arquivos (baseline ausente) [P3]
$ vulture app --min-confidence 80 → 13 achados (parâmetros de interface) [P3]
```

## 5. Logs do app instalado (diagnóstico 10/09)

```
$ grep -c "logged_out" main.log main.old.log → 10 + 3
$ grep -c "no such column" main.log → 89 (clients.has_name — schema velho)
$ grep -oE "Request failed: (GET|POST) [a-z0-9/_-]+" main.log | sort | uniq -c
  15 GET /api/clients/contacts       (500)
   8 GET /api/clients/               (500 — aba Clientes)
   4 POST /api/clients/contacts/reactivate
   1 GET /api/reorder/summary · 1 GET /api/reorder/opportunities
```

## 6. CI/CD

```
$ ls .github/workflows → build-push.yml, ci.yml (release.yml NÃO existe ainda)
$ grep "contents:" build-push.yml → contents: read (release precisa write)
$ ci.yml cobre: ruff + pytest (backend), npm test (whatsapp, agent, frontend)
```

## 7. Documentação

```
$ grep -rln "wwebjs" docs/ README.md → 6 arquivos citam motor antigo
$ ls desktop/tests → vazio (README de desktop pode sugerir testes inexistentes)
$ grep drop_all backend/tests/conftest.py → linha 40 (pytest apaga gasflow.db dev)
```
