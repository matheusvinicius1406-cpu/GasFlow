@echo off
REM ═══════════════════════════════════════════════════════════
REM GasFlow Relay — Cloudflare Tunnel (quick tunnel, sem conta)
REM
REM Exponhe o relay local (http://127.0.0.1:8080) numa URL HTTPS pública.
REM Requer: relay rodando (start-relay.bat) e cloudflared instalado
REM (winget install Cloudflare.cloudflared).
REM
REM QUICK TUNNEL: a URL muda A CADA EXECUCAO — use para testar/validar.
REM Produção (URL fixa): tunnel nomeado + domínio próprio — ver DEPLOY.md.
REM
REM WebSocket: suportado nativamente pelo cloudflared (desktop conecta).
REM ═══════════════════════════════════════════════════════════
echo [tunnel] expondo http://127.0.0.1:8080 via Cloudflare...
echo [tunnel] COPIE a URL https://xxxx.trycloudflare.com que aparecer abaixo
echo [tunnel] e configure no desktop (settings.relayUrl) e no mobile (config.ts).
echo.
cloudflared tunnel --url http://127.0.0.1:8080
