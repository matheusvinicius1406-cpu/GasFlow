$ErrorActionPreference = "Continue"
$releaseDir = "GasFlow/desktop/release"

# 1. Limpar release completamente
if (Test-Path $releaseDir) {
    Write-Host "LIMPANDO release..." -ForegroundColor Yellow
    Get-ChildItem -Path $releaseDir -Recurse | ForEach-Object {
        try {
            if ($_.PSIsContainer) {
                Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction Stop
            } else {
                Remove-Item -Path $_.FullName -Force -ErrorAction Stop
            }
        } catch {
            Write-Host ("ERRO ao remover: " + $_.FullName + " -- " + $_.Exception.Message) -ForegroundColor Red
        }
    }
    Start-Sleep -Seconds 2
}
if (Test-Path $releaseDir) {
    Write-Host "FALHOU AO LIMPAR" -ForegroundColor Red
    exit 1
}
Write-Host "release limpo" -ForegroundColor Green

# 2. Build
Set-Location "GasFlow/desktop"
Write-Host "INICIANDO electron-builder (timeout 600s)..." -ForegroundColor Yellow
$start = Get-Date
try {
    $output = & npx electron-builder --win 2>&1
    $elapsed = (Get-Date) - $start
    Write-Host ("BUILD CONCLUIDO EM " + $elapsed.TotalSeconds + "s") -ForegroundColor Green
    Write-Host $output
} catch {
    $elapsed = (Get-Date) - $start
    Write-Host ("BUILD FALHOU APOS " + $elapsed.TotalSeconds + "s") -ForegroundColor Red
    if ($_.Exception) { Write-Host $_.Exception.Message }
    if ($_.Output) { Write-Host $_.Output }
}

# 3. Relatorio
Write-Host "=== RELATORIO DE SAIDA ===" -ForegroundColor Cyan
if (Test-Path $releaseDir) {
    Get-ChildItem -Path $releaseDir -Recurse -File | ForEach-Object {
        $size = [math]::Round($_.Length / 1MB, 2)
        Write-Host ($_.FullName + " -- " + $size + " MB -- " + $_.LastWriteTime) -ForegroundColor White
    }
} else {
    Write-Host "release/ NAO EXISTE" -ForegroundColor Red
}

if (Test-Path "GasFlow/desktop/release/win-unpacked/GasFlow Desktop.exe") {
    $exe = Get-Item "GasFlow/desktop/release/win-unpacked/GasFlow Desktop.exe"
    Write-Host ("exe pronto: " + $exe.FullName + " -- " + [math]::Round($exe.Length/1MB,2) + " MB -- " + $exe.LastWriteTime) -ForegroundColor Green
}

$exes = Get-ChildItem -Path $releaseDir -Filter "*.exe" -Recurse -File -ErrorAction SilentlyContinue
if ($exes) {
    Write-Host "EXES ENCONTRADOS:" -ForegroundColor Yellow
    $exes | ForEach-Object { Write-Host ("  " + $_.FullName + " -- " + [math]::Round($_.Length/1MB,2) + " MB") }
} else {
    Write-Host "NENHUM .exe encontrado no release/" -ForegroundColor Red
}
