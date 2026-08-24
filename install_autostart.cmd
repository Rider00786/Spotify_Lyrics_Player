@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command "$startup=[Environment]::GetFolderPath('Startup'); $desktop=[Environment]::GetFolderPath('Desktop'); $shell=New-Object -ComObject WScript.Shell; Remove-Item (Join-Path $startup 'Spotify Lyrics.lnk') -Force -ErrorAction SilentlyContinue; $watcher=$shell.CreateShortcut((Join-Path $startup 'Spotify Lyrics Watcher.lnk')); $watcher.TargetPath='%~dp0watch_spotify.cmd'; $watcher.WorkingDirectory='%~dp0'; $watcher.WindowStyle=7; $watcher.Save(); $app=$shell.CreateShortcut((Join-Path $desktop 'Spotify Lyrics Player.lnk')); $app.TargetPath='%~dp0run_music.cmd'; $app.WorkingDirectory='%~dp0'; $app.WindowStyle=1; $app.IconLocation='%SystemRoot%\System32\shell32.dll,137'; $app.Save()"
start "Spotify Lyrics Watcher" /min "%~dp0watch_spotify.cmd"
echo Spotify Lyrics will now start when Spotify is running.
echo Desktop shortcut created: Spotify Lyrics Player
endlocal
pause
