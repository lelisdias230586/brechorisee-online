@echo off
setlocal
title BRECHORISEE - Windows
cd /d "%~dp0"
echo ==============================================
echo  BRECHORISEE - PROGRAMA WINDOWS
echo ==============================================
echo.
echo Este atalho abre o programa da BRECHORISEE para instalar e iniciar o servidor no notebook.
echo.

where py >nul 2>nul
if not errorlevel 1 (
  py "%~dp0brechorisee_windows_launcher.py"
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if not errorlevel 1 (
  python "%~dp0brechorisee_windows_launcher.py"
  exit /b %ERRORLEVEL%
)

echo ERRO: Python nao encontrado no Windows.
echo Instale Python 3.11 ou superior em https://www.python.org/downloads/
echo Marque a opcao "Add python.exe to PATH".
pause
exit /b 1
