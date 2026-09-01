@echo off
setlocal
title Stop WeatherGPT WhatsApp Bot

echo Stopping WeatherGPT WhatsApp bot...

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
"$procs=Get-CimInstance Win32_Process -Filter ""Name = 'powershell.exe'"" | Where-Object { $_.CommandLine -like '*start_whatsapp_supervisor.ps1*' }; foreach($p in $procs){ Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }; Get-Process node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*node.exe*' } | ForEach-Object { try { if ((Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $_.Id)).CommandLine -like '*whatsapp*index.js*') { Stop-Process -Id $_.Id -Force } } catch {} }"

echo.
echo [OK] Stop command sent.
echo The Windows keep-awake request will be released when the supervisor exits.
timeout /t 2 /nobreak >nul
exit /b 0
