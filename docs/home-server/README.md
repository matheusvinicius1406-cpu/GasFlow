# GasFlow Home Server — documentação operacional

Servidor doméstico que hospeda a pilha GasFlow (backend, frontend, banco,
Redis e WhatsApp) com acesso **apenas pela LAN**, HTTPS com CA interna e
custo de licença R$ 0,00.

Este diretório é a fonte de verdade do que foi construído e verificado em
**04/11/2026** (verificação original em 03/11/2026, reexecutada após a troca
de IP para `192.168.0.211`). Nada aqui depende de internet: a única peça
externa é a imagem `caddy:2-alpine`, já baixada.

## 1. Topologia

| Serviço    | Imagem                     | Porta publicada no host            | Papel |
|------------|----------------------------|------------------------------------|-------|
| postgres   | `postgres:16-alpine`       | nenhuma                            | Dados (volume `postgres_data`) |
| redis      | `redis:7-alpine`           | nenhuma                            | Rate limit HTTP, cache e pub/sub |
| backend    | `gasflow-hs-lab-backend`   | nenhuma (`8000/tcp` interna)       | API FastAPI + Alembic no boot |
| frontend   | `gasflow-hs-lab-frontend`  | `127.0.0.1:8088`                   | SPA (nginx) + proxy de `/api`, `/auth`, `/driver` |
| whatsapp   | `gasflow-hs-lab-whatsapp`  | nenhuma (`3000/tcp` interna)       | Automação em `dry-run` (sem pareamento) |
| caddy      | `caddy:2-alpine`           | `192.168.0.211:443` e `127.0.0.1:443` | **Única borda da LAN**, TLS com CA interna |

Somente o Caddy enxerga a LAN. Se ele cair, o resto continua funcionando
para inspeção local em `http://127.0.0.1:8088`.

**Imagem em execução (04/11/2026):** `gasflow-hs-lab-backend:latest`,
`sha256:ce59318857a6a1e19a16635ed57fac66b069dd67f891781969c3db503664edb2`,
construída às `12:49Z` e recriada às `12:51Z`. Ela contém as correções de
tenant (R-6/R-7) e a falha fechada do login de entregador (R-8). A imagem
anterior (`sha256:0c7373b5…`) **não** tinha R-8; detalhes em
`evidence/IMAGE_IDENTITY.txt`.

## 2. Subir a pilha

Quatro arquivos, nesta ordem (`prod` → `homeserver` → `lab` → `lan`):

```powershell
docker compose `
  -p gasflow-hs-lab `
  -f docker-compose.prod.yml `
  -f docker-compose.homeserver.yml `
  -f docker-compose.homeserver.lab.yml `
  -f docker-compose.homeserver.lan.yml `
  --env-file deploy/home-server/.env.lab up -d
```

No boot o backend roda `alembic upgrade head` e só depois inicia o uvicorn.
Em disco mecânico a primeira subida leva de 1 a 3 minutos.

## 3. Endereços

| Uso | URL |
|---|---|
| SPA / API na LAN | `https://192.168.0.211` |
| SPA / API por nome | `https://gasflow.home` (exige DNS/hosts — ver `HOME_SERVER_NETWORK.md`) |
| Inspeção local | `http://127.0.0.1:8088` |
| Health (borda) | `https://192.168.0.211/api/health` |
| Prontidão | `https://192.168.0.211/ready` |

## 4. Verificação rápida

```powershell
# 1. pilha saudável (6/6)
docker compose -p gasflow-hs-lab -f docker-compose.prod.yml `
  -f docker-compose.homeserver.yml -f docker-compose.homeserver.lab.yml `
  -f docker-compose.homeserver.lan.yml --env-file deploy/home-server/.env.lab ps

# 2. HTTPS de ponta a ponta validando a CA interna (9 checagens)
$env:ADMIN_PASSWORD = "<senha do .env.lab>"
python scripts/home-server/verify_lan_https.py `
  --base https://192.168.0.211 `
  --ca deploy/home-server/certs/gasflow-home-ca.crt `
  --hostname gasflow.home

# 3. capturar evidências (pilha, boot, tenant, WhatsApp, gate, PR)
powershell -ExecutionPolicy Bypass -File scripts/home-server/capture_evidence.ps1
```

## 5. O que este perfil **não** faz

- Não publica porta 80 (ela é de outros serviços desta máquina) e não faz
  redirecionamento HTTP→HTTPS.
- Não sai para a internet: `local_certs` força a CA interna, sem ACME.
- Não pareia WhatsApp: `WA_SEND_MODE=dry-run` e `WA_BROADCAST_ENABLED=false`.
- Não faz backup automático para outro disco (o host tem um só — ver
  `OPERATIONS.md`, seção 5).
- Não configura a confiança da CA dentro do APK: isso é feito no cliente
  Android (ver `../mobile/HOME_SERVER_MOBILE_CONNECTION.md` §4).

## 6. Índice

| Documento | Para quê |
|---|---|
| [HOME_SERVER_NETWORK.md](HOME_SERVER_NETWORK.md) | IP fixo, nome `gasflow.home`, instalar a CA no Android, firewall |
| [AUTH_CONTRACT.md](AUTH_CONTRACT.md) | Contratos de login: web/operador, entregador e legado |
| [OPERATIONS.md](OPERATIONS.md) | Backup/restore, gate de migração, resiliência, continuidade |
| [FINDINGS.md](FINDINGS.md) | Defeitos encontrados, correções e riscos residuais |
| [FINAL_REPORT.md](FINAL_REPORT.md) | Relatório final e critérios de aceite |
| [../mobile/HOME_SERVER_MOBILE_CONNECTION.md](../mobile/HOME_SERVER_MOBILE_CONNECTION.md) | Conectar o app Android (URL, CA, contrato `/driver/*`) |
| `evidence/` | Saídas brutas das verificações (com data UTC) |

## 7. Peças no repositório

| Caminho | O que é |
|---|---|
| `docker-compose.homeserver.yml` | Perfil do servidor (sem portas públicas) |
| `docker-compose.homeserver.lab.yml` | Laboratório em `127.0.0.1:8088` |
| `docker-compose.homeserver.lan.yml` | Borda Caddy + `restart: unless-stopped` |
| `deploy/home-server/Caddyfile` | TLS interno, cabeçalhos, proxy para `frontend:80` |
| `deploy/home-server/.env.lab.example` | Modelo de configuração (o `.env.lab` real não vai ao Git) |
| `deploy/home-server/verify-static.sh` | Validação estática do perfil |
| `scripts/home-server/seed_homeserver_lab.py` | Provisiona o tenant de laboratório via API |
| `scripts/home-server/verify_lan_https.py` | Smoke HTTPS validando a CA |
| `scripts/home-server/verify_backup_restore.sh` | Dump, restore descartável e comparação |
| `scripts/home-server/verify_resilience.py` | Restarts controlados e recuperação |
| `scripts/home-server/capture_evidence.ps1` | Consolida as evidências em `evidence/` |
