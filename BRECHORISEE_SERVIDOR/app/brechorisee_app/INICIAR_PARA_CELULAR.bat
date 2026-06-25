@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primeira abertura: instalando dependencias...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 install.py
  ) else (
    python install.py
  )
)
".venv\Scripts\python.exe" mostrar_endereco.py
start "" "http://127.0.0.1:8000/celular"
".venv\Scripts\python.exe" app.py
pause
