@echo off
cd /d "%~dp0"
echo ============================================================
echo  Laqta - developer mode
echo  Edit laqta.py and save: Laqta restarts by itself.
echo  If you save code with a syntax error, it will NOT restart
echo  and the error is shown here and in a notification.
echo  Close this window to stop.
echo ============================================================
python laqta.py --dev
pause
