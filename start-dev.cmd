@echo off
rem GasFlow — iniciar tudo (atalho de duplo clique para o start-dev.sh)
where bash >nul 2>nul
if %errorlevel%==0 (
  bash "%~dp0start-dev.sh"
  goto :eof
)
if exist "C:\Program Files\Git\bin\bash.exe" (
  "C:\Program Files\Git\bin\bash.exe" "%~dp0start-dev.sh"
  goto :eof
)
echo Git Bash nao encontrado. Instale o Git for Windows ou rode start-dev.sh no Git Bash.
pause
