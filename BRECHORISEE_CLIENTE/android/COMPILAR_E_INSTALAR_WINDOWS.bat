@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0COMPILAR_APK_WINDOWS.bat"
if errorlevel 1 (
  echo.
  echo A compilacao falhou. O app nao sera instalado.
  pause
  exit /b 1
)

call "%~dp0INSTALAR_NO_CELULAR_USB.bat"
