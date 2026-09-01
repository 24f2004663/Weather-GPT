@echo off
setlocal
title WeatherGPT WhatsApp Bot

set "BOT_DIR=C:\Users\Kmano\Dropbox\Projects\CurrentProject\whatsapp"
set "SUPERVISOR=%BOT_DIR%\start_whatsapp_supervisor.ps1"

if not exist "%BOT_DIR%\index.js" (
    echo [ERROR] WhatsApp adapter not found:
    echo %BOT_DIR%\index.js
    pause
    exit /b 1
)

if not exist "%SUPERVISOR%" (
    echo [ERROR] Supervisor script not found:
    echo %SUPERVISOR%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden ^
  -Command "Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%SUPERVISOR%'"

echo.
echo [OK] WeatherGPT WhatsApp bot started in the background.
echo.
echo The Node process will run without an open terminal.
echo Windows will be kept awake while the bot is running.
echo The screen may still turn off normally.
echo.
echo Logs:
echo   %BOT_DIR%\logs\whatsapp-supervisor.log
echo   %BOT_DIR%\logs\whatsapp-node.out.log
echo   %BOT_DIR%\logs\whatsapp-node.err.log
echo.
echo To stop it:
echo   stop_whatsapp.bat
echo.
timeout /t 3 /nobreak >nul
exit /b 0
