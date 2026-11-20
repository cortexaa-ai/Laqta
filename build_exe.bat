@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name Laqta --icon assets\logo.ico --add-data "assets;assets" laqta.py
echo.
echo Ready: dist\Laqta.exe
echo Move it to a fixed folder and run it once - it adds itself to Windows startup.
pause
