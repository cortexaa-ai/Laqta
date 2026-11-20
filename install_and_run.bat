@echo off
cd /d "%~dp0"
echo [1/2] Installing libraries...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo !!! Installing PySide6 failed. Take a screenshot of this window.
  pause
  exit /b 1
)
echo [2/2] Starting Laqta in the background...
where pythonw >nul 2>nul
if errorlevel 1 (
  start "" python "%~dp0laqta.py"
) else (
  start "" pythonw "%~dp0laqta.py"
)
echo Done! Look for the purple icon next to the clock.
timeout /t 4 >nul
