@echo off
setlocal
cd /d "%~dp0"
:watch
powershell -NoProfile -ExecutionPolicy Bypass -Command "$spotify=Get-Process -Name Spotify -ErrorAction SilentlyContinue; $lyrics=Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*music player*' }; if ($spotify -and -not $lyrics) { Start-Process -FilePath '%~dp0run_music.cmd' -WorkingDirectory '%~dp0' -WindowStyle Minimized }"
timeout /t 2 /nobreak >nul
goto watch
