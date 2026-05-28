@echo off
REM Launch the Webull dashboard and expose it via a Cloudflare quick tunnel.
REM Requires: Python on PATH, and cloudflared on PATH
REM   install cloudflared:  winget install --id Cloudflare.cloudflared

where cloudflared >nul 2>nul
if errorlevel 1 goto :nocloudflared

echo Starting the Webull dashboard...
start "Webull Dashboard" python app.py

echo Waiting for the app to start...
timeout /t 5 /nobreak >nul

echo.
echo Opening public tunnel - use the https://*.trycloudflare.com URL below on your phone/iPad:
echo.
cloudflared tunnel --url http://localhost:5000
goto :eof

:nocloudflared
echo cloudflared is not installed.
echo   winget install --id Cloudflare.cloudflared
echo   or download: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
pause
