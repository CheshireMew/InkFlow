@echo off
setlocal
cd /d "%~dp0"
python -m inkflow.cli app
endlocal
