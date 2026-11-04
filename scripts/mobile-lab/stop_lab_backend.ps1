# MOBILE USB LAB 01 - encerra SOMENTE a instancia de laboratorio.
#
# So mata o PID gravado por start_lab_backend.ps1 se a linha de comando
# dele continuar sendo o uvicorn da porta de laboratorio. Nunca mexe em
# outro processo, container, banco ou servico operacional.
#
# ASCII only.
[CmdletBinding()]
param(
    [int]$Port = 8010,
    [string]$LabDir = (Join-Path $env:LOCALAPPDATA "Temp\opencode\gasflow-lab")
)

$ErrorActionPreference = 'Stop'
$PidFile = Join-Path $LabDir "uvicorn.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "[lab] Sem arquivo de PID ($PidFile) - nada para encerrar."
    exit 0
}

$pidValue = (Get-Content $PidFile -Raw).Trim()
$proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "[lab] Processo $pidValue ja nao existe - apenas limpando PID file."
    Remove-Item $PidFile -Force
    exit 0
}

$cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $pidValue" -ErrorAction SilentlyContinue).CommandLine
$expected = "app.main:app"
$isOurs = ($cmdline -and $cmdline -like "*$expected*" -and $cmdline -like "*--port*$Port*")

if (-not $isOurs) {
    Write-Error "[lab] PID $pidValue NAO parece ser o uvicorn de laboratorio (porta $Port). Abortando sem matar nada."
    exit 2
}

Stop-Process -Id $pidValue -Force
Remove-Item $PidFile -Force
Write-Host "[lab] uvicorn de laboratorio (PID $pidValue) encerrado. Nenhum outro servico foi afetado."

# remove o tunel USB do ADB desta porta, se existir
try {
    $serial = (adb devices | Select-String -Pattern "^\S+\s+device$" | ForEach-Object { ($_.Line -split "\s+")[0] } | Select-Object -First 1)
    if ($serial) {
        adb -s $serial reverse --remove "tcp:$Port" 2>$null | Out-Null
        Write-Host "[lab] adb reverse tcp:$Port removido do dispositivo $serial."
    }
} catch { }
