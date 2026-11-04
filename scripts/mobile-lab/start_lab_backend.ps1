# MOBILE USB LAB 01 - backend de laboratorio isolado.
#
# Sobe uma instancia DESCARTAVEL do FastAPI em 127.0.0.1:<porta> com:
#   - banco SQLite proprio (nunca o operacional, nunca Postgres alheio)
#   - segredos gerados na primeira execucao e guardados FORA do repositorio
#   - WhatsApp/IA/ViaCEP desligados (sem integracao de envio real)
#   - rate limit em memoria (sem Redis)
#
# Idempotente: se ja estiver de pé e respondendo /health, nao faz nada.
# Nao destrutivo: aborta se a porta estiver ocupada por outro processo.
#
# ASCII only (o .ps1 do Windows le sem BOM como ANSI; acentos quebram literais).
[CmdletBinding()]
param(
    [int]$Port = 8010,
    [string]$LabDir = (Join-Path $env:LOCALAPPDATA "Temp\opencode\gasflow-lab"),
    [int]$StartupTimeoutSec = 240
)

$ErrorActionPreference = 'Stop'

$RepoRoot   = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$Secrets    = Join-Path $LabDir "secrets.env"
$PidFile    = Join-Path $LabDir "uvicorn.pid"
$DbPath     = Join-Path $LabDir "gasflow_lab.db"
$HealthUrl  = "http://127.0.0.1:$Port/health"

function Test-LabHealth {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function New-Base62 {
    param([int]$Length)
    $rng  = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $alph = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] $Length
    $rng.GetBytes($bytes)
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $bytes) { [void]$sb.Append($alph[$b % $alph.Length]) }
    # garante a politica do backend: 8+ chars, 1 maiuscula, 1 minuscula, 1 digito
    $s = $sb.ToString()
    return ("Q" + "x" + "7" + $s)
}

function New-HexSecret {
    param([int]$Size = 48)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buffer = New-Object byte[] $Size
    $rng.GetBytes($buffer)
    return (($buffer | ForEach-Object { $_.ToString("x2") }) -join "")
}

# ---------------------------------------------------------------- ja rodando?
if (Test-LabHealth) {
    Write-Host "[lab] Ja em execucao e respondendo $HealthUrl - nada a fazer (idempotente)."
    exit 0
}

# ---------------------------------------------------------------- porta livre?
$busy = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($busy) {
    Write-Error "[lab] Porta $Port ocupada por outro processo (PID $($busy.OwningProcess)). Abortando - nada foi tocado."
    exit 2
}

New-Item -ItemType Directory -Path $LabDir -Force | Out-Null

# ---------------------------------------------------------------- segredos
# NUNCA usar $secrets aqui: o PowerShell e case-insensitive e $secrets
# sobrescreveria $Secrets (o caminho), jogando os segredos num arquivo
# chamado "System.Collections.Hashtable" no cwd.
if (-not (Test-Path $Secrets)) {
    $generated = @{
        ADMIN_PASSWORD       = New-Base62 -Length 20
        MOBILE_JWT_SECRET    = New-HexSecret
        OPERATOR_JWT_SECRET  = New-HexSecret
        LAB_TENANT_ADMIN_PW  = New-Base62 -Length 20
        LAB_DRIVER_USERNAME  = "motorista-lab-001"
        LAB_DRIVER_PASSWORD  = New-Base62 -Length 20
    }
    $lines = $generated.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }
    if (-not ($Secrets -is [string])) { throw "Variavel de caminho corrompida: $Secrets" }
    Set-Content -Path $Secrets -Value $lines -Encoding Ascii
    Write-Host "[lab] Segredos gerados em $Secrets (FORA do repositorio - nao versionar)."
} else {
    Write-Host "[lab] Reaproveitando segredos existentes: $Secrets"
}

$secretMap = @{}
Get-Content $Secrets | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$') { $secretMap[$Matches[1]] = $Matches[2] }
}

# ---------------------------------------------------------------- ambiente
$env:DATABASE_URL              = "sqlite:///" + ($DbPath -replace '\\', '/')
$env:ADMIN_PASSWORD            = $secretMap["ADMIN_PASSWORD"]
$env:MOBILE_JWT_SECRET         = $secretMap["MOBILE_JWT_SECRET"]
$env:OPERATOR_JWT_SECRET       = $secretMap["OPERATOR_JWT_SECRET"]
$env:ENVIRONMENT               = "lab"
$env:RATE_LIMIT_MODE           = "memory"
$env:WHATSAPP_SERVICE_URL      = "http://127.0.0.1:39999"   # porta sem servico: nada e enviado
$env:WHATSAPP_SERVICE_KEY      = ""                          # service-to-service desabilitado
$env:MARCOS_GAS_API_KEY        = ""
$env:AI_PROVIDER               = "mock"
$env:VIACEP_ENABLED            = "false"
$env:DOCS_ENABLED              = "false"
$env:GASFLOW_INIT_DB_ALEMBIC   = "1"
$env:GASFLOW_LAB               = "1"

Write-Host "[lab] Repo   : $RepoRoot"
Write-Host "[lab] Banco  : $DbPath"
Write-Host "[lab] Porta  : 127.0.0.1:$Port (somente loopback)"

# ---------------------------------------------------------------- subir
$proc = Start-Process -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port", "--log-level", "info") `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput (Join-Path $LabDir "uvicorn.out.log") `
    -RedirectStandardError  (Join-Path $LabDir "uvicorn.err.log") `
    -WindowStyle Hidden -PassThru

Set-Content -Path $PidFile -Value $proc.Id
Write-Host "[lab] uvicorn iniciado (PID $($proc.Id)) - aguardando /health..."

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-LabHealth) {
        Write-Host "[lab] PRONTO: $HealthUrl"
        Write-Host "[lab] Parar somente esta instancia: .\stop_lab_backend.ps1 -Port $Port"
        exit 0
    }
    Start-Sleep -Seconds 2
}

Write-Error "[lab] Tempo esgotado sem /health. Veja $LabDir\uvicorn.err.log"
exit 3
