@echo off
cd /d "%~dp0"
echo [1/2] Installing libraries...
python -m pip install -r requirements.txt
echo [2/2] Starting Laqta in the background...
start "" pythonw "%~dp0laqta.py"
echo Done! Look for the purple icon next to the clock.
timeout /t 4 >nul
