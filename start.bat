@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo Fehler beim Installieren der Pakete.
    pause
    exit /b 1
)
py bot.py
pause
