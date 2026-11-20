@echo off
cd /d "%~dp0"
echo ===== Python version =====
python --version
where python
where pythonw
echo.
echo ===== PySide6 check =====
python -c "import PySide6; print('PySide6', PySide6.__version__)"
echo.
echo ===== Running Laqta (errors will show below) =====
python laqta.py
echo.
echo ===== Laqta stopped. Take a screenshot of this window =====
pause
