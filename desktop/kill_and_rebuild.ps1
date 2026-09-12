Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -Verbose
Get-Process -Name "gasflow-backend" -ErrorAction SilentlyContinue | Stop-Process -Force -Verbose
Start-Sleep -Seconds 2

$releaseDir = "GasFlow/desktop/release"
if (Test-Path $releaseDir) {
    Remove-Item -Path $releaseDir -Recurse -Force -Verbose -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

if (Test-Path $releaseDir) {
    Write-Host "FALHOU AO LIMPAR"
    exit 1
}

Write-Host "INICIANDO BUILD..."
Set-Location "GasFlow/desktop"
npx electron-builder --win
