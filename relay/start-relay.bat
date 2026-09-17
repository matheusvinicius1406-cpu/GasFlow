@echo off
REM ═══════════════════════════════════════════════════════════
REM GasFlow Relay — start local no notebook (Windows)
REM
REM Sobe o relay (FastAPI/uvicorn) na porta 8080. Na primeira vez gera o
REM RELAY_TOKEN e salva em relay\.env (FORA do git — nunca commitar).
REM O MESMO token vai no desktop (settings.relayToken) e no mobile
REM (config.ts relayToken).
REM ═══════════════════════════════════════════════════════════
setlocal enabledelayedexpansion
cd /d "%~dp0"

if exist .env (
  for /f "usebackq tokens=1,* delims==" %%a in (.env) do (
    if "%%a"=="RELAY_TOKEN" set "RELAY_TOKEN=%%b"
  )
)

if "%RELAY_TOKEN%"=="" (
  for /f %%i in ('python -c "import secrets;print(secrets.token_urlsafe(32))"') do set "RELAY_TOKEN=%%i"
  echo RELAY_TOKEN=!RELAY_TOKEN!>.env
  echo.
  echo  ============================================================
  echo   NOVO RELAY_TOKEN gerado e salvo em relay\.env
  echo   !RELAY_TOKEN!
  echo   Guarde-o: o MESMO valor vai no desktop e no mobile.
  echo  ============================================================
  echo.
)

echo [relay] subindo em http://127.0.0.1:8080  (Ctrl+C para parar)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
