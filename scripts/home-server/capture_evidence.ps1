#Requires -Version 5.1
<#
.SYNOPSIS
    Captura as evidências operacionais do Home Server (pilha, boot, tenant de
    laboratório, WhatsApp, gate de migração e status do PR).

.DESCRIPTION
    Gera arquivos de texto em docs/home-server/evidence/. NÃO imprime segredos:
    nenhuma senha/token é lida do .env ou do banco.

    As evidências de HTTPS, backup/restore e resiliência são produzidas por
    scripts próprios (Python/shell) porque fazem chamadas HTTP e restarts:
        python scripts/home-server/verify_lan_https.py
        python scripts/home-server/verify_resilience.py
        bash   scripts/home-server/verify_backup_restore.sh

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/home-server/capture_evidence.ps1
#>
[CmdletBinding()]
param(
    [string]$EvidenceDir = "docs/home-server/evidence",
    [string]$EnvFile     = "deploy/home-server/.env.lab",
    [string]$Project     = "gasflow-hs-lab",
    [string]$Backend     = "gasflow-hs-lab-backend",
    [string]$Postgres    = "gasflow-hs-lab-postgres",
    [string]$WhatsApp    = "gasflow-hs-lab-whatsapp",
    [string]$TenantId    = "gasflow_home_server_lab",
    [string]$DbName      = "gasflow_lab",
    [string]$DbUser      = "gasflow_lab"
)

# "Continue": comandos nativos (docker/gh) escrevem progresso em stderr e o
# PowerShell 5.1 transforma isso em ErrorRecord; com "Stop" a captura morreria.
$ErrorActionPreference = "Continue"
# Evita mojibake: a saída dos containers é UTF-8.
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch { }

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $root
try {
    New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $compose = @(
        "-p", $Project,
        "-f", "docker-compose.prod.yml",
        "-f", "docker-compose.homeserver.yml",
        "-f", "docker-compose.homeserver.lab.yml",
        "-f", "docker-compose.homeserver.lan.yml",
        "--env-file", $EnvFile
    )

    function Save-Evidence {
        param([string]$Name, [scriptblock]$Body)
        $path = Join-Path $EvidenceDir $Name
        $lines = & $Body 2>&1 | ForEach-Object { "$_" }
        # UTF-8 SEM BOM: Set-Content -Encoding utf8 no PowerShell 5.1 grava BOM
        # e o repositório não aceita BOM nos arquivos versionados.
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllLines($path, [string[]]$lines, $utf8)
        Write-Host ("  {0,-38} {1} linha(s)" -f $Name, $lines.Count)
    }

    Write-Host "Evidencias -> $EvidenceDir"

    # 1. Pilha em execucao -------------------------------------------------
    Save-Evidence "00_STACK.txt" {
        "# capturado em $stamp (UTC)"
        "## docker compose ps"
        & docker compose @compose ps
        "## imagens em uso"
        & docker ps --filter "name=gasflow-hs-lab" --format "{{.Names}}`t{{.Image}}`t{{.Status}}"
    }

    # 2. Boot do backend ---------------------------------------------------
    Save-Evidence "01_BOOT.txt" {
        "# capturado em $stamp (UTC)"
        "## alembic current"
        & docker exec $Backend alembic current
        "## tabelas em public"
        & docker exec $Postgres psql -U $DbUser -d $DbName -tAc "select count(*) from information_schema.tables where table_schema='public'"
        "## ocorrencias de 'schema migration leve falhou' no log (esperado: 0)"
        $hits = & docker logs $Backend 2>&1 | Select-String -Pattern "schema migration leve falhou" -SimpleMatch
        if ($hits) { $hits } else { "0" }
    }

    # 3. Tenant de laboratorio (contagens, sem segredos) -------------------
    Save-Evidence "02_LAB_TENANT.txt" {
        "# capturado em $stamp (UTC)"
        "# tenant: $TenantId"
        foreach ($t in @("auth_memberships","auth_tenants","clients","orders","order_items","products","inventory","delivery_drivers")) {
            $n = & docker exec $Postgres psql -U $DbUser -d $DbName -tAc "select count(*) from $t where tenant_id='$TenantId'" 2>&1
            "{0,-18} {1}" -f $t, $n
        }
        "## usuarios do tenant (username/role, sem hash)"
        & docker exec $Postgres psql -U $DbUser -d $DbName -c "select u.username, r.name as role from auth_users u join auth_memberships m on m.user_id=u.id join auth_roles r on r.id=m.role_id where m.tenant_id='$TenantId' order by u.username"
    }

    # 4. WhatsApp em modo seco --------------------------------------------
    Save-Evidence "03_WHATSAPP.txt" {
        "# capturado em $stamp (UTC)"
        "## env relevante (somente chaves de seguranca, sem valores sensiveis)"
        & docker inspect $WhatsApp --format "{{range .Config.Env}}{{println .}}{{end}}" |
            Select-String -Pattern "^WA_SEND_MODE=|^WA_BROADCAST_ENABLED=|^WA_ENGINE=|^WHATSAPP_SEND_MODE=|^ALLOW_INSECURE_AUTH="
        "## portas publicadas (esperado: nenhuma)"
        $ports = & docker inspect $WhatsApp --format "{{json .NetworkSettings.Ports}}"
        if ($ports -match 'null|\{\}') { "nenhuma porta publicada" } else { $ports }
        "## arquivos de sessao (esperado: 0 - sem pareamento)"
        & docker exec $WhatsApp sh -c "find /app/.wwebjs_auth /app/auth_info_baileys -type f 2>/dev/null | wc -l"
        "## health (rota real: /api/health na porta interna)"
        & docker exec $WhatsApp node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>r.text()).then(t=>console.log(t)).catch(e=>console.log('ERR',e.message))"
        "## /metrics sem token (esperado: 401 - SEC-02)"
        & docker exec $WhatsApp node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/metrics').then(async r=>console.log(r.status, (await r.text()).slice(0,80))).catch(e=>console.log('ERR',e.message))"
    }

    # 5. Gate de migracao (recusas) ----------------------------------------
    Save-Evidence "04_DEPLOY_GATE.txt" {
        "# capturado em $stamp (UTC)"
        "# o gate precisa recusar: sem --execute, dentro do repo, sem backup off-host"
        $gate = "scripts/home-server/data/pg_deploy_gate.py"
        $common = @("--project", $Project, "--env-file", $EnvFile, "--database-name", $DbName, "--backup-dir", (Join-Path $env:TEMP "gasflow-hs-backup"))
        & python $gate @common *> $null
        "sem --execute                     exit=$LASTEXITCODE (esperado 0, dry-run)"
        & python $gate @common --execute --confirm-off-host --backup-dir "deploy/home-server" *> $null
        "backup-dir dentro do repo         exit=$LASTEXITCODE (esperado 2)"
        & python $gate @common --execute --backup-dir (Join-Path $env:TEMP "gasflow-hs-backup") *> $null
        "execute sem --confirm-off-host    exit=$LASTEXITCODE (esperado 2)"
        & python $gate @common --execute --confirm-off-host --backup-dir (Join-Path $env:TEMP "nao-existe-xyz") *> $null
        "backup-dir inexistente            exit=$LASTEXITCODE (esperado 2)"
    }

    # 6. Status do PR -------------------------------------------------------
    Save-Evidence "05_PR.txt" {
        "# capturado em $stamp (UTC)"
        & gh pr view 79 --json number,title,state,isDraft,mergeable,mergeStateStatus,headRefName,baseRefName,updatedAt,url
        "## checks"
        & gh pr checks 79
    }

    Write-Host "Concluido."
}
finally {
    Pop-Location
}
