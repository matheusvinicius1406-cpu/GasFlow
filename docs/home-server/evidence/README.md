# Evidências — Home Server (04/11/2026)

Saídas brutas das verificações. Todas têm data/hora **UTC** na primeira linha
ou no nome do arquivo. Nada aqui contém senha, token ou hash de senha.

| Arquivo | Origem | O que prova |
|---|---|---|
| `00_STACK.txt` | `capture_evidence.ps1` | 6/6 containers saudáveis e o mapa de portas publicado |
| `01_BOOT.txt` | idem | Alembic em `a4b5c6d7e8f9 (head)`, 69 tabelas, 0 erros de schema no boot |
| `02_LAB_TENANT.txt` | idem | Tenant de laboratório com usuários por papel |
| `03_WHATSAPP.txt` | idem | `dry-run`, broadcast off, sem porta publicada, 0 arquivo de sessão, `/metrics` 401 |
| `04_DEPLOY_GATE.txt` | idem | Gate recusa os três cenários inseguros (exit 2) |
| `05_PR.txt` | idem | Estado do PR #79 e checks |
| `06_HTTPS.txt` | `verify_lan_https.py` | 9/9 sobre HTTPS com a CA interna validada |
| `07_TESTS.txt` | `pytest` | Gate + perfil Home Server + config de produção (**54 passed**) |
| `08_TESTS_DRIVER_AUTH.txt` | `pytest` | Login de entregador (falha fechada), isolamento de itens (**16 passed**) |
| `09_RESILIENCE.txt` | `verify_resilience.py` | Recuperação após restart de redis/frontend/caddy/postgres |
| `IMAGE_IDENTITY.txt` | build/inspeção | Identidade da imagem e quais correções ela contém |

Reproduzir:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/home-server/capture_evidence.ps1
python scripts/home-server/verify_lan_https.py --base https://192.168.0.211 `
  --ca deploy/home-server/certs/gasflow-home-ca.crt --hostname gasflow.home
python scripts/home-server/verify_resilience.py --base https://192.168.0.211 `
  --ca deploy/home-server/certs/gasflow-home-ca.crt
& 'C:\Program Files\Git\bin\bash.exe' scripts/home-server/verify_backup_restore.sh
```

Observações de leitura:

- `AVISO` não é falha: `gasflow.home` sem DNS/hosts é esperado.
- O 500 pontual após restart do Postgres aparece em `09_RESILIENCE.txt` e é
  explicado em `../OPERATIONS.md` §3 (na última execução recuperou em 3 s).
- O manifest de backup fica em `%TEMP%\gasflow-hs-backup\<timestamp>\` (fora
  do repositório, por ser dado operacional). A execução de
  `20261104T125554Z` gerou 240.467 bytes e SHA-256 `a990eeed…305f4b`.
- Use o `bash` do Git (`C:\Program Files\Git\bin\bash.exe`): o `bash` do
  WSL não enxerga o Docker Desktop nesta máquina.
