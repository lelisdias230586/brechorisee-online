@echo off
setlocal EnableExtensions
title BRECHORISEE - Servidor Windows
cd /d "%~dp0..\BRECHORISEE_SERVIDOR\app"

if not exist ".env" (
  echo ERRO: arquivo .env nao encontrado.
  echo O arquivo unico deve ficar em:
  echo BRECHORISEE_SERVIDOR\app\.env
  pause
  exit /b 1
)

if not exist "%~dp0..\BRECHORISEE_SERVIDOR\dados" mkdir "%~dp0..\BRECHORISEE_SERVIDOR\dados"

if not exist "%~dp0..\.venv_windows_brechorisee\Scripts\python.exe" (
  echo Criando ambiente Python...
  py -m venv "%~dp0..\.venv_windows_brechorisee"
)

echo Instalando dependencias...
"%~dp0..\.venv_windows_brechorisee\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0..\.venv_windows_brechorisee\Scripts\pip.exe" install -r requirements.txt

echo.
echo Abrindo BRECHORISEE em http://127.0.0.1:8000
echo Para mudar IP, Telegram, banco ou backup, edite somente:
echo BRECHORISEE_SERVIDOR\app\.env
echo.
start "" "http://127.0.0.1:8000"
"%~dp0..\.venv_windows_brechorisee\Scripts\python.exe" -m uvicorn brechorisee_app.app:app --host 0.0.0.0 --port 8000
pause
