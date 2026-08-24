@echo off
cd /d "%~dp0"
set MUSIC_TEST_MODE=0
set PYTHONPATH=%~dp0src
if exist ".venv\Scripts\python.exe" (
	".venv\Scripts\python.exe" -m music_player
) else (
	python -m music_player
)