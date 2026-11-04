# Operação: backup, gate de migração, resiliência e continuidade

Nada aqui é teórico: os números vêm das execuções de 04/11/2026 registradas em
`evidence/`.

## 1. Backup do banco

```powershell
bash scripts/home-server/verify_backup_restore.sh
```

O script:

1. roda `pg_dump -Fc` **dentro** do container (nada de cliente no host);
2. copia o dump para um diretório com timestamp e grava
   `*.manifest.json` com tamanho, `sha256`, formato, `magic_ok` e `off_host`;
3. cria um banco descartável `gasflow_hs_restore`;
4. restaura com `pg_restore --exit-on-error`;
5. compara origem e destino: tabelas, índices, constraints, `alembic_version`
   e contagem por tabela;
6. apaga o banco descartável.

Resultado medido (execução `20261104T125554Z`, após a reconstrução do backend):

| Item | Valor |
|---|---|
| Tamanho do dump | 240.467 bytes |
| SHA-256 | `a990eeedde0629f53a2a11b14c08f9bd16d4de83817e85b8c9d679cec4305f4b` |
| Tabelas | 69 em ambos |
| Índices | 299 em ambos |
| Constraints | 113 em ambos |
| `alembic_version` | `a4b5c6d7e8f9` em ambos |
| Divergências por tabela | **0** (69 tabelas comparadas) |
| Destino independente | `"off_host": false` (um disco só) |

### Limitação registrada: destino no mesmo disco

O host tem **um único disco**. Não existe "off-host" real, então o manifest
sai com `"off_host": false` e a nota correspondente. Isso protege contra
erro de operação e corrupção lógica, **não** contra perda do disco.

Para fechar essa lacuna (pendência P1):

- copiar o dump para um HD externo, pendrive ou NAS após cada backup;
- ou habilitar um segundo volume (`docker volume create` em outro disco);
- e só então rodar o gate com `--confirm-off-host`.

## 2. Gate de migração (`pg_deploy_gate.py`)

O gate recusa migrar sem backup verificado e sem confirmação de destino
independente. Códigos observados:

| Cenário | Exit | Esperado |
|---|---|---|
| dry-run (sem `--execute`) | 0 | 0 |
| `--execute` com `--backup-dir` **dentro do repositório** | 2 | 2 (`EXIT_SAFETY`) |
| `--execute` sem `--confirm-off-host` | 2 | 2 |
| `--execute` com diretório de backup inexistente | 2 | 2 |

Uso pretendido (quando houver destino independente de verdade):

```powershell
python scripts/home-server/data/pg_deploy_gate.py `
  --project gasflow-hs-lab --env-file deploy/home-server/.env.lab `
  --database-name gasflow_lab `
  --backup-dir E:\backups\gasflow `
  --execute --confirm-off-host
```

O `--backup-dir` **não pode** ficar dentro do repositório — o gate compara o
`st_dev` e recusa. É proteção contra "backup" que mora no mesmo volume dos
dados.

## 3. Resiliência (restarts controlados)

```powershell
python scripts/home-server/verify_resilience.py
```

Cada serviço é reiniciado e a pilha precisa voltar sozinha. Medições:

| Serviço reiniciado | Recuperação | Dados/sessão |
|---|---|---|
| redis | 8 s | rate limit volta a contar; API responde |
| frontend | 10 s | SPA volta; `/api` continua |
| caddy | 17 s | TLS/handshake volta |
| postgres | 23 s | 5 clientes, 4 pedidos, 1 entregador e 6 usuários intactos |

**Comportamento observado e aceito:** a primeira requisição que toca o banco
logo após o restart do Postgres pode devolver **500** uma vez; as seguintes
voltam a `200` (na execução de 04/11 a recuperação levou 3 s). A causa é
conexão morta no pool durante a janela de recuperação — `pool_pre_ping=True`
está ativo e a API se recupera sozinha em segundos. Para o operador: **se
aparecer um 500 isolado após reiniciar o banco, recarregue antes de
investigar**.

Sessões sobrevivem ao restart porque são persistidas em `auth_sessions` (não
em memória).

## 4. Procedimento de restauração (desastre real)

```powershell
# 1. parar quem escreve
docker stop gasflow-hs-lab-backend gasflow-hs-lab-whatsapp

# 2. (se o volume morreu) recriar o banco vazio
docker exec gasflow-hs-lab-postgres psql -U gasflow_lab -d postgres `
  -c "DROP DATABASE IF EXISTS gasflow_lab" `
  -c "CREATE DATABASE gasflow_lab"

# 3. restaurar o dump (o arquivo já está dentro do container ou copie com docker cp)
docker cp "C:\caminho\database-XXXX.dump" gasflow-hs-lab-postgres:/tmp/restore.dump
docker exec gasflow-hs-lab-postgres pg_restore -U gasflow_lab -d gasflow_lab `
  --exit-on-error /tmp/restore.dump

# 4. conferir versão do schema e subir de novo
docker exec gasflow-hs-lab-backend alembic current
docker start gasflow-hs-lab-backend gasflow-hs-lab-whatsapp
```

Depois: `python scripts/home-server/verify_lan_https.py ...` (9/9) e um login
real. Se o dump for de uma versão anterior, rode `alembic upgrade head` antes
de liberar o acesso.

## 5. Continuidade: cenários e resposta

| Cenário | Impacto | Resposta |
|---|---|---|
| Queda de energia / reboot do PC | tudo para | Docker sobe sozinho (`restart: unless-stopped`); conferir `/ready` |
| Postgres reinicia | 500 pontual + ~35 s | aguardar; recarregar; dados persistem |
| Redis reinicia | rate limit zera, cache frio | nenhuma ação |
| Caddy cai | LAN sem HTTPS; loopback segue | `docker start` no caddy; certificados persistem no volume |
| Volume `caddy_data` perdido | aviso de certificado em todos os aparelhos | reinstalar a CA (ver `HOME_SERVER_NETWORK.md`) |
| Disco cheio | Postgres/backup falham | liberar espaço; conferir `docker system df`; nunca apagar `postgres_data` |
| Internet cai | **nada** quebra | a pilha é 100% local; só atualizações de imagem dependem de rede |
| Celular sem Wi-Fi | app sem acesso | é esperado: acesso restrito à LAN |
| IP do servidor muda por DHCP | `https://<ip>` deixa de responder | reservar DHCP ou atualizar `GASFLOW_LAN_IP` + recriar o caddy |
| Falha de energia durante escrita | risco de corrupção | restaurar do último dump verificado (seção 4) |

## 6. Rotina sugerida

**Diário:** `docker compose ps` (6/6 healthy) e `https://<ip>/api/health`.

**Semanal:** `bash scripts/home-server/verify_backup_restore.sh` e copiar o
dump para fora do disco do servidor.

**Antes de qualquer migração:** `pg_deploy_gate.py` em dry-run, ler a saída,
só então `--execute` com backup em destino independente.

**Mensal:** `docker system df`; conferir espaço e logs (`max-size` já limita
cada serviço).
