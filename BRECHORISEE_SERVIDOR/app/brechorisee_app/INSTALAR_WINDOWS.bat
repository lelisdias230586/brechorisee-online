@echo off
setlocal
cd /d "%~dp0"
echo Instalando o brechorisee...
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 install.py
) else (
  python install.py
)
pause
