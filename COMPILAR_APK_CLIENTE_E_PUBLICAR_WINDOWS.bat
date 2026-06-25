@echo off
setlocal
cd /d "%~dp0"
call "%~dp0GERAR_APK_CLIENTE_FINAL_WINDOWS.bat"
exit /b %ERRORLEVEL%
